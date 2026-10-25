#!/usr/bin/env python3
"""Check whether live coupons cover the products a purchase list needs.

Direction matters. `coupon_link` answers "this coupon → which methods?", which is
the browsing direction. This module answers the other one, used after the user has
confirmed what to buy: "this purchase list → does any coupon actually cover its
products, and what is still missing?"

Two inputs are supported, and both must read the *current* list rather than the
original recipe:

* `check_selection` — numbered methods straight from the session;
* `check_plan` — a purchase plan, so a swapped flavour (香芋派 instead of
  菠萝派) or a hand-set count is what gets checked, not the catalogue default.

The check is deliberately mechanical:

* a product counts as **covered** only when the coupon's `productCode` equals the
  product's own code (or its parent code), or the names are identical after
  normalisation;
* a shared alias family counts as **family_only** — same family, possibly a
  different spec — and is never reported as covered;
* a coupon that carries no product information at all is **insufficient_info**,
  which is not the same as "no coupon applies";
* a coupon that is explicitly expired or not yet valid is **not a candidate**,
  even if its products would match. Unknown validity stays a candidate, flagged
  for checking.

No network, no price, no usability claim. Only `calculate-price` can confirm.
"""
import argparse
import json
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numbered_catalog as nc

LEVEL_RANK = {"code": 3, "name": 2, "family": 1, "none": 0}
COVERING = ("covers_all", "partial")


def _norm(text):
    return unicodedata.normalize("NFKC", str(text or "")).casefold().strip()


def _coupon_products(coupon):
    raw = coupon.get("products") or coupon.get("eligible_products") or []
    if isinstance(raw, dict):
        raw = [raw]
    names, codes = [], set()
    for item in raw:
        if isinstance(item, dict):
            for key in ("productName", "name"):
                if item.get(key):
                    names.append(str(item[key]).strip())
            if item.get("productCode"):
                codes.add(str(item["productCode"]).strip())
        elif isinstance(item, str) and item.strip():
            names.append(item.strip())
    if coupon.get("productName"):
        names.append(str(coupon["productName"]).strip())
    if coupon.get("productCode"):
        codes.add(str(coupon["productCode"]).strip())
    return names, codes


def _parse_time(value):
    if value in (None, ""):
        return None
    text = str(value).strip().replace("/", "-")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _validity(coupon, now):
    """Return (valid_now, note). `None` means the coupon data was not parseable."""
    start = _parse_time(coupon.get("validFrom") or coupon.get("valid_from"))
    end = _parse_time(coupon.get("validUntil") or coupon.get("valid_until"))
    weekdays = coupon.get("weekdays")
    label = coupon.get("validity") or coupon.get("tradeDateTime")
    if start is None and end is None:
        return None, ("有效期：" + str(label)) if label else "有效期未提供，需按券面核对"
    if start and now < start:
        return False, "尚未生效（" + start.strftime("%Y-%m-%d %H:%M") + " 起）"
    if end and now > end:
        return False, "已过期（" + end.strftime("%Y-%m-%d %H:%M") + " 截止）"
    if isinstance(weekdays, (list, tuple)) and weekdays:
        # 1=Monday … 7=Sunday, matching ISO weekday numbering.
        if now.isoweekday() not in {int(d) for d in weekdays}:
            return False, "今天不在券的适用星期内"
    return True, "有效期内"


def _method_products(method):
    """Required products plus the default choice of each group, with codes."""
    items = []
    for product in method.get("required_products") or []:
        if isinstance(product, dict):
            ref = product.get("reference_menu") or {}
            items.append({
                "name": product.get("name"),
                "code": str(ref.get("code")) if ref.get("code") else None,
                "parent_code": str(ref.get("parent_code")) if ref.get("parent_code") else None,
                "role": "required",
            })
        else:
            items.append({"name": str(product), "code": None, "parent_code": None,
                          "role": "required"})
    for group in method.get("product_choices") or []:
        if group.get("default_name"):
            items.append({"name": group.get("default_name"),
                          "code": str(group["default_code"]) if group.get("default_code") else None,
                          "parent_code": None, "role": "choice_default"})
    return items


def plan_products(plan):
    """Products of a purchase plan, using the swapped flavour and chosen counts.

    This is the whole point of accepting a plan: after the user changes 派口味
    to 香芋派, the coupon check must look for 香芋派, not 菠萝派.
    """
    items = plan.get("items") if isinstance(plan, dict) else plan
    products = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        name = item.get("nutrition_name") or item.get("name")
        if not name:
            continue
        products.append({
            "name": name,
            "code": str(item["option_code"]) if item.get("option_code") else (
                str(item["price_code"]) if item.get("price_code") else None),
            "parent_code": str(item["parent_code"]) if item.get("parent_code") else None,
            "role": "plan_item",
            "quantity": item.get("quantity"),
            "label": item.get("display_name") or name,
        })
    return products


def _match_product(product, names, codes, alias_data):
    if product.get("code") and product["code"] in codes:
        return "code", "商品编码一致（" + product["code"] + "）"
    if product.get("parent_code") and product["parent_code"] in codes:
        return "code", "父商品编码一致（" + product["parent_code"] + "）"
    product_name = _norm(product["name"])
    if any(product_name and product_name == _norm(name) for name in names):
        return "name", "商品名称完全一致"
    fam = nc._family_of_product(product["name"] or "", alias_data)
    if fam and any(nc._family_of_product(name, alias_data) is fam for name in names):
        return "family", "同一商品家族（" + fam["label"] + "），规格可能不同"
    return "none", ""


def _check_one(products, coupon, alias_data, now):
    names, codes = _coupon_products(coupon)
    valid_now, validity_note = _validity(coupon, now)
    covered, family_only, missing, reasons = [], [], [], []
    best = "none"
    for product in products:
        label = product.get("label") or product["name"]
        level, reason = _match_product(product, names, codes, alias_data)
        if LEVEL_RANK[level] > LEVEL_RANK[best]:
            best = level
        if level in ("code", "name"):
            covered.append(label)
            reasons.append(label + "：" + reason)
        elif level == "family":
            family_only.append(label)
            missing.append(label)  # 同家族不等于覆盖，仍算还缺
            reasons.append(label + "：" + reason + "（不算覆盖）")
        else:
            missing.append(label)
    if not names and not codes:
        status = "insufficient_info"
        reasons = reasons + ["券没有返回适用商品信息，无法判断是否覆盖"]
    elif covered and not missing:
        status = "covers_all"
    elif covered:
        status = "partial"
    elif family_only:
        status = "family_only"
    else:
        status = "none"
    candidate = (status in COVERING) and valid_now is not False
    return {
        "title": coupon.get("title") or coupon.get("name"),
        "couponId": coupon.get("couponId"),
        "couponCode": coupon.get("couponCode"),
        "priceYuan": coupon.get("priceYuan"),
        "status": status,
        "match_level": best,
        "covered": covered,
        "family_only": family_only,
        "missing": missing,
        "reasons": reasons,
        "valid_now": valid_now,
        "validity_note": validity_note,
        "is_candidate": candidate,
        "usability": "not_yet_confirmed",
        "usability_note": ("需门店菜单核验与 calculate-price 确认"
                           if candidate else
                           "有效期不满足或信息不足，不进入候选；仅作记录"),
    }


def _order(coupon_result):
    """Candidates first: still-valid, then covers more, then stronger level."""
    return (
        0 if coupon_result["is_candidate"] else 1,
        -len(coupon_result["covered"]),
        -LEVEL_RANK[coupon_result["match_level"]],
        0 if coupon_result["valid_now"] is not False else 1,
    )


def _check_targets(targets, coupons, now, alias_data):
    results = []
    for target in targets:
        checked = [_check_one(target["products"], coupon, alias_data, now)
                   for coupon in coupons]
        checked.sort(key=_order)
        candidates = [r for r in checked if r["is_candidate"]]
        entry = dict(target)
        entry.pop("products", None)
        entry["coupons"] = checked
        entry["best_coupon"] = candidates[0]["title"] if candidates else None
        entry["has_covering_coupon"] = bool(candidates)
        entry["missing_from_best"] = candidates[0]["missing"] if candidates else None
        entry["insufficient_coupon_info"] = any(
            r["status"] == "insufficient_info" for r in checked)
        results.append(entry)
    return results


def _notice():
    return ("只做商品层面的覆盖判断：covered 表示券的适用商品与购买清单对得上，"
            "不代表券一定可用；family_only 只是同家族、规格可能不同；"
            "insufficient_info 表示券没给适用商品信息，不能当成没有优惠；"
            "过期或当天不适用的券不进入候选，有效期未知保留待核。"
            "最终以 calculate-price 结果为准。")


def _normalize_coupons(coupons):
    if isinstance(coupons, dict):
        coupons = coupons.get("coupons") or coupons.get("data") or [coupons]
    return [c for c in (coupons or []) if isinstance(c, dict)]


def check_selection(database, ids, coupons, now=None, alias_path=None):
    """Test every coupon against every selected method. Order is preserved."""
    alias_data = nc.load_aliases(alias_path)
    now = now or datetime.now()
    coupons = _normalize_coupons(coupons)
    targets = []
    if ids:
        payload = nc.resolve(database, " ".join(ids))
        by_id = {m["id"]: m for m in payload["methods"]}
        for ident in ids:
            method = by_id.get(ident)
            if method is None:
                raise ValueError("资料库中不存在：" + ident)
            targets.append({
                "id": method["id"],
                "display_number": method["display_number"],
                "card_title": method["card_title"],
                "required_products": [p["name"] for p in _method_products(method)],
                "products": _method_products(method),
            })
    methods = _check_targets(targets, coupons, now, alias_data)
    with_cover = [m for m in methods if m["has_covering_coupon"]]
    return {
        "result_schema_version": 1,
        "mode": "local_unified_research",
        "entry": "coupon_check",
        "target": "selection",
        "checked_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "coupon_count": len(coupons),
        "method_count": len(methods),
        "methods_with_covering_coupon": len(with_cover),
        "methods": methods,
        "notice": _notice(),
    }


def check_plan(plan, coupons, now=None, alias_path=None):
    """Test every coupon against a purchase plan's current items."""
    alias_data = nc.load_aliases(alias_path)
    now = now or datetime.now()
    coupons = _normalize_coupons(coupons)
    items = plan.get("items") if isinstance(plan, dict) else plan
    targets = []
    for index, item in enumerate(items or []):
        if not isinstance(item, dict):
            continue
        products = plan_products({"items": [item]})
        if not products:
            continue
        targets.append({
            "id": "ITEM{:02d}".format(index + 1),
            "display_name": item.get("display_name") or item.get("nutrition_name"),
            "quantity": item.get("quantity"),
            "products": products,
        })
    checked = _check_targets(targets, coupons, now, alias_data)
    with_cover = [m for m in checked if m["has_covering_coupon"]]
    return {
        "result_schema_version": 1,
        "mode": "local_unified_research",
        "entry": "coupon_check",
        "target": "plan",
        "checked_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "coupon_count": len(coupons),
        "item_count": len(checked),
        "items_with_covering_coupon": len(with_cover),
        "items": checked,
        "notice": _notice(),
    }


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="按编号检查券是否覆盖餐品")
    check.add_argument("--database", type=Path, default=nc.PACKAGED_DATABASE)
    check.add_argument("--ids", nargs="+", required=True)
    check.add_argument("--coupons", type=Path, required=True)
    check.add_argument("--now", default=None, help="覆盖当前时间，便于复现，如 '2026-10-25 12:49'")
    check.add_argument("--alias", type=Path, default=None)

    plan = sub.add_parser("plan", help="按当前购买清单检查券是否覆盖餐品")
    plan.add_argument("--plan", type=Path, required=True,
                      help="购买计划 JSON（basket.py plan 的输出或计划文件）")
    plan.add_argument("--coupons", type=Path, required=True)
    plan.add_argument("--now", default=None)
    plan.add_argument("--alias", type=Path, default=None)

    args = parser.parse_args()
    try:
        now = _parse_time(args.now) if args.now else datetime.now()
        if args.command == "check":
            result = check_selection(args.database, args.ids, _read(args.coupons),
                                     now=now, alias_path=args.alias)
        else:
            payload = _read(args.plan)
            if isinstance(payload, dict) and "methods" in payload and "items" not in payload:
                import basket
                payload = basket.plan_from_state(basket.load_plan_state(args.plan, for_consumption=True))
            result = check_plan(payload, _read(args.coupons), now=now, alias_path=args.alias)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
