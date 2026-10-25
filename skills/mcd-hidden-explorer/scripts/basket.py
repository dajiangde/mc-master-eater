#!/usr/bin/env python3
"""Basket helpers: merge shared products, compute calories, compare options.

All functions are pure and offline. Prices always come from an official
`calculate-price` result; this module never invents a total and never claims a
global lowest price. Calories come from the official nutrition table; a missing
row is reported as missing, never counted as zero.
"""
import argparse
import csv
from copy import deepcopy
import json
import re
from copy import deepcopy
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import checkout_contract as checkout


def normalize_name(name):
    """Normalise a product name for nutrition lookup without merging variants."""
    text = str(name or "").strip()
    text = text.replace("（", "(").replace("）", ")").replace("　", " ")
    text = re.sub(r"[\s\-—–_·]+", "", text)
    return text.casefold()


def load_nutrition(path):
    """Load an official nutrition table into {normalised_name: kcal}."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = data
    while isinstance(rows, dict):
        if "entries" in rows:
            rows = rows["entries"]
        elif "data" in rows:
            rows = rows["data"]
        else:
            raise ValueError("营养数据缺少 entries 或 data，无法确认餐品热量")
    if isinstance(rows, str):
        # list-nutrition-foods can return a TOON table inside the JSON data field.
        lines = rows.strip().splitlines()
        header = re.fullmatch(r"\[\d+\]\{([^}]+)\}:\s*", lines[0].strip()) if lines else None
        if not header:
            raise ValueError("无法识别官方营养表格式")
        fields = next(csv.reader([header.group(1)]))
        if "productName" not in fields or "energyKcal" not in fields:
            raise ValueError("官方营养表缺少餐品名或千卡字段")
        values = csv.reader(line.strip() for line in lines[1:] if line.strip())
        rows = [dict(zip(fields, cells)) for cells in values]
    if not isinstance(rows, list):
        raise ValueError("官方营养表必须包含餐品列表")
    table = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        name = row.get("productName") or row.get("name")
        kcal = row.get("energyKcal", row.get("kcal"))
        if name is None or kcal in (None, "null", ""):
            continue
        table[normalize_name(name)] = int(round(float(kcal)))
    return table


def nutrition_lookup(table, name):
    return table.get(normalize_name(name))


def merge_requirements(methods):
    """Merge required products across methods, flagging shared and unknown amounts.

    A product used by several methods is counted once; the suggested quantity is
    the larger per-method need, and it is marked as needing user confirmation
    because the catalogue does not carry verified amounts.
    """
    order, merged = [], {}
    for method in methods or []:
        mid = method.get("id") or method.get("method_id")
        for product in method.get("required_products") or []:
            name = product.get("name") if isinstance(product, dict) else str(product)
            if not name:
                continue
            quantity = product.get("quantity") if isinstance(product, dict) else None
            key = normalize_name(name)
            if key not in merged:
                merged[key] = {"name": name, "quantity": quantity, "sources": [],
                               "shared": False, "needs_confirmation": quantity is None}
                order.append(key)
            item = merged[key]
            if mid and mid not in item["sources"]:
                item["sources"].append(mid)
            if quantity is not None:
                if item["quantity"] is None:
                    item["quantity"] = quantity
                else:
                    item["quantity"] = max(item["quantity"], quantity)
    items = []
    for key in order:
        item = merged[key]
        item["shared"] = len(item["sources"]) > 1
        if item["quantity"] is None:
            item["quantity"] = 1
            item["note"] = "资料未给份数，建议按 1 份购买，待确认"
        elif item["shared"]:
            item["note"] = "多款吃法共用，按较大需求合并计算"
        else:
            item["note"] = ""
        items.append(item)
    return {
        "items": items,
        "shared": [item["name"] for item in items if item["shared"]],
        "needs_confirmation": [item["name"] for item in items if item["needs_confirmation"]],
        "notice": "共用餐品只按购买数量计算一次；份数来自资料还是建议已分别标注。",
    }


def purchase_quantity(product, method_id):
    rule = product.get("purchase_quantity_rule") or {}
    if product.get("quantity") is not None:
        count, status, basis = product["quantity"], "source_reported", product.get("quantity_evidence")
    elif rule:
        count, status, basis = rule.get("quantity"), rule.get("status"), rule.get("basis")
    elif product.get("purchase_quantity_suggestion") is not None:
        count, status, basis = product["purchase_quantity_suggestion"], "purchase_suggestion", "资料中的采购建议，尚非来源用量"
    else:
        count, status, basis = 1, "needs_confirmation", "未提供用量，暂按1个购买单位试算，待用户确认"
    if not checkout.positive_int(count):
        raise ValueError("采购数量必须为正整数：" + str(product.get("name")))
    return {"quantity": count,
            "quantity_needs_confirmation": status != "source_reported",
            "quantity_basis": [{"method_id": method_id, "quantity": count,
                                "status": status, "basis": basis}]}


def _quantity_override(item, quantities):
    """Find a user-set purchase count for this item.

    Keys are tried most specific first: `METHOD:product`, then the product name
    as it appears in the nutrition table, then the display label. A user who
    says "共用的薯条只要一份" must not be overwritten by the source rule on the
    next recompute.
    """
    if not quantities:
        return None
    candidates = []
    candidates.extend(item.get("choice_keys") or [])
    name = item.get("nutrition_name")
    for mid in item.get("methods") or []:
        if name:
            candidates.append("{}:{}".format(mid, name))
    candidates.extend([name, item.get("display_name")])
    for key in candidates:
        if key and key in quantities:
            return quantities[key]
    return None


def apply_quantity_overrides(items, quantities):
    """Apply user-set counts; returns the items and which ones changed."""
    applied = []
    for item in items:
        override = _quantity_override(item, quantities)
        if override is None:
            continue
        if not checkout.positive_int(override):
            raise ValueError("购买份数必须为正整数：{} -> {}".format(
                item.get("display_name"), override))
        if override != item["quantity"]:
            item["quantity_before_override"] = item["quantity"]
        item["quantity"] = override
        item["quantity_needs_confirmation"] = False
        item["quantity_source"] = "user_override"
        item["quantity_basis"].append({"method_id": None, "quantity": override,
                                       "status": "user_override",
                                       "basis": "用户指定购买份数"})
        applied.append({"name": item.get("display_name"), "quantity": override})
    return items, applied


def build_purchase_plan(methods, choices=None, quantities=None, optional=None):
    """Turn chosen methods into a purchase list of real products and flavour options.

    A flavour option is never a standalone product code: the plan keeps the parent
    product code plus the option code, and leaves the final SKU to the live menu.
    """
    choices = choices or {}
    optional = optional or {}
    merged, order, questions = {}, [], []

    def add(key, payload):
        if key not in merged:
            merged[key] = payload
            order.append(key)
            return merged[key]
        item = merged[key]
        for source in payload["methods"]:
            if source not in item["methods"]:
                item["methods"].append(source)
        # Two methods each need their own portion, so the purchase adds up.
        item["quantity"] += payload["quantity"]
        item["quantity_basis"].extend(payload["quantity_basis"])
        item["choice_keys"] = list(dict.fromkeys(
            item.get("choice_keys", []) + payload.get("choice_keys", [])))
        item["quantity_needs_confirmation"] |= payload["quantity_needs_confirmation"]
        item["shared"] = len(item["methods"]) > 1
        if item["shared"]:
            item["note"] = "{} 款吃法共用，合并为一次购买共 {} 份".format(len(item["methods"]), item["quantity"])
        return item

    for method in methods or []:
        mid = method.get("id") or method.get("method_id")
        selected_optional = optional.get(mid, [])
        if not isinstance(selected_optional, list):
            raise ValueError("可选餐品必须用列表指定：" + str(mid))
        extra_products = []
        for selected in selected_optional:
            match = next((p for p in method.get("optional_products") or []
                          if isinstance(p, dict) and selected in
                          (p.get("name"), (p.get("reference_menu") or {}).get("code"))), None)
            if match is None:
                raise ValueError("{} 没有可选餐品：{}".format(mid, selected))
            if match not in extra_products:
                extra_products.append(match)
        for product in list(method.get("required_products") or []) + extra_products:
            if not isinstance(product, dict):
                continue
            menu = product.get("reference_menu") or {}
            parent, code = menu.get("parent_code"), menu.get("code")
            parent_name = menu.get("parent_name")
            item = add(("option" if parent else "product", parent or code, code if parent else None), {
                "kind": "option" if parent else "product",
                "display_name": "{}（{}）".format(parent_name, product["name"]) if parent else product["name"],
                "nutrition_name": product["name"],
                "parent_code": parent,
                "parent_name": parent_name,
                "option_code": code if parent else None,
                "price_code": parent or code,
                "choice_keys": [],
                **purchase_quantity(product, mid), "methods": [mid], "shared": False,
                "note": "资料已指定口味" if parent else "",
            })
        for group in method.get("product_choices") or []:
            gname = group["name"]
            options = group.get("options") or []
            override = (choices.get(mid) or {}).get(gname) or choices.get(gname)
            chosen = None
            if override:
                chosen = next((o for o in options
                               if override in (o.get("name"), (o.get("reference_menu") or {}).get("code"))), None)
                if chosen is None:
                    raise ValueError("{} 的「{}」没有「{}」这个选项，可选：{}".format(
                        mid, gname, override, "、".join(o.get("name", "") for o in options)))
            else:
                chosen = next((o for o in options if o.get("is_default_choice")), None)
            if chosen is None:
                raise ValueError("{} 的「{}」需要先选口味：{}".format(
                    mid, gname, "、".join(o.get("name", "") for o in options)))
            menu = chosen.get("reference_menu") or {}
            parent = menu.get("parent_code") or menu.get("code")
            item = add(("option", parent, menu.get("code")), {
                "kind": "option",
                "display_name": "{}（{}）".format(menu.get("parent_name") or gname, chosen["name"]),
                "nutrition_name": chosen["name"],
                "parent_code": parent,
                "parent_name": menu.get("parent_name"),
                "option_code": menu.get("code"),
                "price_code": parent,
                **purchase_quantity(chosen, mid), "methods": [mid], "shared": False,
                "group": gname,
                "choice_keys": ["{}:{}".format(mid, gname)],
                "note": "默认方案" if not override else "用户改选",
            })
            questions.append({
                "method": mid, "group": gname,
                "chosen": chosen["name"], "chosen_code": menu.get("code"),
                "is_default": not override,
                "options": [{"name": o["name"], "code": (o.get("reference_menu") or {}).get("code")}
                            for o in options],
            })
    items = [merged[key] for key in order]
    items, applied = apply_quantity_overrides(items, quantities)
    return {
        "result_schema_version": 1,
        "items": items,
        "questions": questions,
        "shared": [item["display_name"] for item in items if item["shared"]],
        "quantity_overrides": applied,
        "notes": [
            "口味选项不是独立商品编码：核价用 price_code（父商品）+ option_code。",
            "份数来自资料还是建议已分别标注；未给份数时按 1 份建议，需用户确认。",
            "用户指定份数优先于资料与建议，重新计算不会被原配方覆盖。",
        ],
        "calorie_names": [item["nutrition_name"] for item in items],
    }


PLAN_SCHEMA_VERSION = 1


def _now():
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def new_plan_state(methods, choices=None, quantities=None, session=None, optional=None):
    """Session-scoped purchase plan: methods plus the user's own adjustments.

    Storing the overrides next to the methods is what keeps a recompute from
    resetting a flavour swap or a hand-set count back to the source defaults.
    """
    return {
        "plan_schema_version": PLAN_SCHEMA_VERSION,
        "created_at": _now(),
        "updated_at": _now(),
        "session": str(session) if session else None,
        "methods": deepcopy(list(methods or [])),
        "choices": dict(choices or {}),
        "quantities": dict(quantities or {}),
        "optional": deepcopy(optional or {}),
    }


def load_plan_state(path, for_consumption=False):
    data = _read(path)
    if not isinstance(data, dict) or "methods" not in data:
        raise ValueError("购买计划文件缺少 methods：" + str(path))
    data.setdefault("choices", {})
    data.setdefault("quantities", {})
    data.setdefault("optional", {})
    if for_consumption and data.get("session"):
        import session_state
        context = session_state.load_session(data["session"])
        identity = context.get("session_id", context["created_at"])
        if (data.get("session_id", identity) != identity or
                data.get("plan_generation", 0) != context["plan_generation"] or
                [m.get("id") for m in data["methods"]] != context["current_selection"]):
            raise ValueError("购买计划已过期，请先用 discover.py plan 同步当前会话，再核价或算热量")
        current_file = context.get("purchase_plan_file")
        if current_file and Path(current_file).resolve() != Path(path).resolve():
            raise ValueError("这不是本会话当前购买计划，不能核价或算热量")
    return data


def save_plan_state(path, state):
    # A rejected edit must leave the last valid plan byte-for-byte unchanged.
    plan_from_state(state)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    state = dict(state)
    state["updated_at"] = _now()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return state


def merge_overrides(state, choices=None, quantities=None, optional=None):
    """Merge new adjustments into the stored ones; never drop earlier ones."""
    state = deepcopy(state)
    merged_quantities = dict(state.get("quantities") or {})
    # A flavour changes its name/SKU, but remains the same choice group. Keep a
    # previously requested count attached to that group rather than the old name.
    for item in plan_from_state(state)["items"]:
        keys = item.get("choice_keys") or []
        if (item.get("quantity_source") == "user_override" and len(keys) == 1
                and len(item.get("methods") or []) == 1):
            merged_quantities[keys[0]] = item["quantity"]
            for name in [item.get("nutrition_name"), item.get("display_name")]:
                merged_quantities.pop(name, None)
    merged_choices = {k: dict(v) if isinstance(v, dict) else v
                      for k, v in (state.get("choices") or {}).items()}
    for key, value in (choices or {}).items():
        if isinstance(value, dict) and isinstance(merged_choices.get(key), dict):
            merged_choices[key].update(value)
        else:
            merged_choices[key] = value
    state["choices"] = merged_choices
    merged_optional = deepcopy(state.get("optional") or {})
    merged_optional.update(deepcopy(optional or {}))
    state["optional"] = merged_optional
    state["quantities"] = merged_quantities
    current_items = plan_from_state(state)["items"]
    for key, count in (quantities or {}).items():
        stored_as_choice = False
        for item in current_items:
            keys = item.get("choice_keys") or []
            names = [item.get("nutrition_name"), item.get("display_name"), *keys]
            names.extend("{}:{}".format(mid, item.get("nutrition_name"))
                         for mid in item.get("methods") or [])
            if key in names and len(keys) == 1 and len(item.get("methods") or []) == 1:
                merged_quantities[keys[0]] = count
                stored_as_choice = True
        if not stored_as_choice:
            merged_quantities[key] = count
    state["quantities"] = merged_quantities
    return state


def plan_from_state(state):
    return build_purchase_plan(state.get("methods") or [], state.get("choices") or {},
                               state.get("quantities") or {}, state.get("optional") or {})


def build_price_items(plan):
    """Turn a purchase plan into `calculate-price` items.

    Two rules are easy to get wrong by hand, so they live here:

    - a flavour option never becomes `productCode`; the parent code goes in and the
      option rides inside `roundList[].comboItemList[].code`;
    - `comboItemList[].quantity` is the option count *per parent unit*, so it stays
      at 1 no matter how many parents are bought. Passing the parent quantity here
      returns `60006 商品已售罄或不可售`, which reads like a sold-out product and
      sends you chasing the wrong problem.
    """
    items = plan.get("items") if isinstance(plan, dict) else plan
    if not items:
        raise ValueError("购买清单为空，先选择餐品再核价")
    payload, notes = [], []
    for item in items or []:
        quantity = item.get("quantity")
        if not checkout.positive_int(quantity):
            raise ValueError("采购数量必须为正整数")
        if item.get("live_item") is not None:
            live = deepcopy(item["live_item"])
            if live.get("quantity") != quantity:
                raise ValueError("实时商品配置与购买份数不一致，需重新配置")
            if not live.get("productCode"):
                raise ValueError("实时商品配置缺少商品编码")
            payload.append(live)
            continue
        parent, option = item.get("parent_code"), item.get("option_code")
        if option and parent:
            payload.append({
                "productCode": parent,
                "quantity": quantity,
                "roundList": [{
                    "round": "1",
                    "comboItemList": [{"code": option, "quantity": 1}],
                }],
            })
        else:
            code = item.get("price_code") or item.get("parent_code")
            if not code:
                raise ValueError("{} 缺少商品编码".format(item.get("display_name") or item))
            payload.append({"productCode": code, "quantity": quantity})
        if item.get("shared"):
            notes.append("{} 共 {} 份，已合并为一行".format(item.get("display_name"), quantity))
    return {
        "result_schema_version": 1,
        "items": payload,
        "notes": notes + ["comboItemList 数量按每份父商品记 1，不乘父商品份数。"],
    }


def compute_calories(items, table):
    """Sum calories by purchased quantity. Missing rows make the result partial."""
    breakdown, missing, known = [], [], 0
    for item in items or []:
        # Plan items carry display_name for humans and nutrition_name for the table.
        name = item.get("nutrition_name") or item.get("name")
        label = item.get("display_name") or name
        quantity = item.get("quantity")
        if not isinstance(quantity, int) or quantity < 1:
            missing.append({"name": label, "reason": "数量未确认，未计入"})
            continue
        components = item.get("components") or []
        if components:
            subtotal, gap = 0, []
            for component in components:
                kcal = nutrition_lookup(table, component.get("name"))
                cq = component.get("quantity") or 1
                if kcal is None:
                    gap.append(component.get("name"))
                else:
                    subtotal += kcal * cq
            if gap:
                missing.append({"name": label, "reason": "套餐子项缺少营养数据：" + "、".join(gap)})
                known += subtotal * quantity
                breakdown.append({"name": label, "quantity": quantity,
                                  "kcal_each": None, "kcal": subtotal * quantity,
                                  "partial": True})
            else:
                known += subtotal * quantity
                breakdown.append({"name": label, "quantity": quantity,
                                  "kcal_each": subtotal, "kcal": subtotal * quantity,
                                  "partial": False})
            continue
        kcal = nutrition_lookup(table, name)
        if kcal is None:
            missing.append({"name": label, "reason": "官方营养表未收录该商品"})
            continue
        known += kcal * quantity
        breakdown.append({"name": label, "quantity": quantity,
                          "kcal_each": kcal, "kcal": kcal * quantity, "partial": False})
    return {
        "total_kcal": None if missing else known,
        "known_kcal": known,
        "complete": not missing,
        "label": "整份热量" if not missing else "已知部分热量",
        "breakdown": breakdown,
        "missing": missing,
        "note": "按整份购买餐品全部吃完估算；只吃一部分时实际摄入会不同。",
    }


def compare_options(options):
    """Order basket options by actual total outlay. Never claims a global minimum."""
    prepared = []
    for option in options or []:
        price = option.get("price_cents")
        if price is None:
            raise ValueError("每个方案都需要官方核价结果 price_cents")
        prepared.append(dict(option))
    prepared.sort(key=lambda item: (item["price_cents"], item.get("label", "")))
    cheapest = prepared[0]["price_cents"] if prepared else None
    for rank, option in enumerate(prepared, 1):
        option["rank"] = rank
        option["delta_cents"] = option["price_cents"] - cheapest
        option["is_cheapest_here"] = rank == 1
    return {
        "options": prepared,
        "notice": "只比较本次实际核价的方案；不代表全网或全国最低价。",
    }


def build_confirmation(summary):
    """Keep the full quoted configuration and bind the displayed revision."""
    result = checkout.prepare(summary)
    result["calories"] = result.get("calories") or {}
    result["calorie_label"] = result["calories"].get("label")
    result["calorie_total"] = result["calories"].get("total_kcal")
    result["blockers"] = checkout.configuration_blockers(result)
    result["confirmation_fingerprint"] = checkout.fingerprint(result)
    result["ready_for_confirmation"] = not result["blockers"]
    result["ready_for_order"] = False
    result["order_created"] = False
    result["notice"] = "待用户确认这份最新摘要；校验确认指纹和待提交完整参数后才能创建订单。指纹不代表用户同意。"
    return result


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_optional(value):
    """Inline JSON or a file path; empty means no overrides."""
    if not value:
        return {}
    text = str(value).strip()
    if text.startswith("{"):
        return json.loads(text)
    return _read(text)


def _methods(payload):
    if isinstance(payload, dict):
        return payload.get("methods") or payload.get("cards") or []
    return payload or []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    merge = sub.add_parser("merge")
    merge.add_argument("--methods", type=Path, required=True)

    plan = sub.add_parser("plan")
    plan.add_argument("--methods", type=Path, default=None,
                      help="methods/cards JSON；与 --plan-file 同用时替换其中的 methods")
    plan.add_argument("--choices", default=None, help="内联 JSON 或文件：口味改选，如 {\"派口味二选一\":\"香芋派\"}")
    plan.add_argument("--quantities", default=None,
                      help="内联 JSON 或文件：用户指定份数，如 {\"中薯条\":1}")
    plan.add_argument("--optional", default=None,
                      help='可选餐品，如 {"U11":["中薯条"]}；空列表取消加购')
    plan.add_argument("--plan-file", type=Path, default=None,
                      help="会话内购买计划文件；存在时沿用其中的口味与份数调整")
    plan.add_argument("--session", default=None, help="可选：把计划绑定到会话文件路径")

    calories = sub.add_parser("calories")
    calories.add_argument("--items", type=Path, required=True)
    calories.add_argument("--nutrition", type=Path, required=True)

    price_items = sub.add_parser("price-items")
    price_items.add_argument("--plan", type=Path, required=True)

    compare = sub.add_parser("compare")
    compare.add_argument("--options", type=Path, required=True)

    confirm = sub.add_parser("confirmation")
    confirm.add_argument("--summary", type=Path, required=True)

    args = parser.parse_args()
    try:
        if args.command == "merge":
            result = merge_requirements(_read(args.methods))
        elif args.command == "plan":
            state = None
            if args.plan_file and Path(args.plan_file).is_file():
                state = load_plan_state(args.plan_file)
            if args.methods is not None:
                methods = _methods(_read(args.methods))
                state = new_plan_state(methods, session=args.session) if state is None else {
                    **state, "methods": methods}
            if state is None:
                raise ValueError("需要 --methods 或已存在的 --plan-file")
            state = merge_overrides(state, _read_optional(args.choices),
                                    _read_optional(args.quantities), _read_optional(args.optional))
            result = plan_from_state(state)
            if args.plan_file:
                state = save_plan_state(args.plan_file, state)
            result["plan_state"] = {
                "choices": state.get("choices"),
                "quantities": state.get("quantities"),
                "optional": state.get("optional"),
                "plan_file": str(args.plan_file) if args.plan_file else None,
            }
        elif args.command == "calories":
            payload = _read(args.items)
            if isinstance(payload, dict) and "methods" in payload and "items" not in payload:
                payload = plan_from_state(load_plan_state(args.items, for_consumption=True))
            items = payload.get("items") if isinstance(payload, dict) else payload
            result = compute_calories(items, load_nutrition(args.nutrition))
        elif args.command == "price-items":
            payload = _read(args.plan)
            if isinstance(payload, dict) and "methods" in payload and "items" not in payload:
                payload = plan_from_state(load_plan_state(args.plan, for_consumption=True))
            result = build_price_items(payload)
        elif args.command == "compare":
            result = compare_options(_read(args.options))
        else:
            result = build_confirmation(_read(args.summary))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
