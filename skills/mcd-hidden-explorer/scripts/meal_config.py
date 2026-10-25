#!/usr/bin/env python3
"""Turn a `query-meal-detail` payload into a `calculate-price` item.

Why this module exists
----------------------
A code shown in the gallery, in a coupon, or in an old menu record is not
automatically a sellable product. McDonald's China menu has three kinds of
codes, and only the first one may be used as `productCode` on its own:

1. **sellable SKU**   -- `rounds` is empty; use it directly.
2. **parent product** -- `rounds` is not empty; the sellable unit is the parent,
   and the flavour/side is a *choice* inside a round.
3. **choice code**    -- lives inside `rounds[].choices[]`; it is NOT a SKU.

Verified case: `1217` (奥利奥麦旋风) is a choice of the parent `9900008754`
(经典麦旋风). Sending `1217` as `productCode` fails; the working request is

    {"productCode": "9900008754", "quantity": 1,
     "roundList": [{"round": "1", "comboItemList": [{"code": "1217", "quantity": 1}]}]}

Everything here is pure and offline: no network, no pricing, no side effects.
The output is a request body, never a price.
"""
import argparse
import json
from pathlib import Path


class MealConfigError(ValueError):
    """Raised when a detail payload cannot produce a valid price item."""


#: `maxQuantity` value the API uses for "no upper bound".
UNLIMITED = -1


def _rounds(detail):
    return [r for r in (detail.get("rounds") or []) if isinstance(r, dict)]


def _choices(round_):
    return [c for c in (round_.get("choices") or []) if isinstance(c, dict)]


def _round_key(round_, index):
    """Round label used in `roundList[].round`.

    The API accepts the round id as a string; fall back to the 1-based position
    when a payload omits `id`.
    """
    raw = round_.get("id")
    if raw is None or str(raw).strip() == "":
        return str(index + 1)
    return str(raw)


def _is_required(round_):
    return int(round_.get("minQuantity") or 0) >= 1


def _default_choice(round_):
    choices = _choices(round_)
    for choice in choices:
        if choice.get("isDefault") in (1, "1", True):
            return choice
    for choice in choices:
        if int(choice.get("quantity") or 0) >= 1:
            return choice
    return None


def describe(detail):
    """Classify a detail payload: `sellable`, `parent`, or `choice_only`.

    Returns the role plus the round/choice structure so a caller can explain the
    situation instead of silently sending a wrong code.
    """
    rounds = _rounds(detail)
    if not rounds:
        return {
            "code": detail.get("code"),
            "name": detail.get("name"),
            "role": "sellable",
            "sellable_as_product_code": True,
            "rounds": [],
            "notice": "无选配轮次，编码可直接作为 productCode 核价。",
        }
    described = []
    for index, round_ in enumerate(rounds):
        described.append({
            "round": _round_key(round_, index),
            "name": round_.get("name"),
            "minQuantity": int(round_.get("minQuantity") or 0),
            "maxQuantity": int(round_.get("maxQuantity") or 0),
            "required": _is_required(round_),
            "choices": [
                {
                    "code": c.get("code"),
                    "name": c.get("name"),
                    "isDefault": c.get("isDefault"),
                    "diffPrice": c.get("diffPrice"),
                }
                for c in _choices(round_)
            ],
        })
    return {
        "code": detail.get("code"),
        "name": detail.get("name"),
        "role": "parent",
        "sellable_as_product_code": True,
        "rounds": described,
        "notice": "父商品：productCode 用本编码，口味/规格用 roundList 指定。"
                  "轮次里的 choices[].code 不能单独作为 productCode。",
    }


def find_choice(detail, code):
    """Locate `code` as a choice inside the parent product, if it is one."""
    for index, round_ in enumerate(_rounds(detail)):
        for choice in _choices(round_):
            if str(choice.get("code")) == str(code):
                return {
                    "code": str(code),
                    "name": choice.get("name"),
                    "parent_code": str(detail.get("code")),
                    "parent_name": detail.get("name"),
                    "round": _round_key(round_, index),
                    "round_name": round_.get("name"),
                    "isDefault": choice.get("isDefault"),
                    "diffPrice": choice.get("diffPrice"),
                }
    return None


def _all_choice_codes(detail):
    return {str(c.get("code")) for r in _rounds(detail) for c in _choices(r)}


def _validate_selection(detail, selection):
    """Reject selections that cannot apply to this product at all.

    A per-round check is not enough: a list of codes is meant to be spread over
    the rounds, so an unmatched code would otherwise be silently ignored and the
    default would be used instead — exactly the kind of quiet wrong order this
    module exists to prevent.
    """
    if not selection:
        return
    known = _all_choice_codes(detail)
    if isinstance(selection, dict):
        labels = {_round_key(r, i) for i, r in enumerate(_rounds(detail))}
        unknown_rounds = [str(k) for k in selection if str(k) not in labels]
        if unknown_rounds:
            raise MealConfigError(
                "没有这些轮次：%s；可选轮次：%s"
                % ("、".join(unknown_rounds), "、".join(sorted(labels)))
            )
        codes = []
        for value in selection.values():
            codes.extend(value if isinstance(value, (list, tuple)) else [value])
    elif isinstance(selection, (list, tuple, set)):
        codes = list(selection)
    else:
        return
    unknown = [str(code) for code in codes if str(code) not in known]
    if unknown:
        raise MealConfigError(
            "该商品没有这些选项：%s；可选：%s"
            % ("、".join(unknown),
               "、".join("%s(%s)" % (c.get("name"), c.get("code"))
                        for r in _rounds(detail) for c in _choices(r)))
        )


def _selected_codes(round_, round_key, selection):
    """Codes the caller explicitly asked for in this round, if any."""
    if not selection:
        return None
    if isinstance(selection, dict):
        for key in (round_key, str(round_key), int(round_key) if round_key.isdigit() else None):
            if key is not None and key in selection:
                value = selection[key]
                return list(value) if isinstance(value, (list, tuple)) else [value]
        return None
    if isinstance(selection, (list, tuple, set)):
        known = {str(c.get("code")) for c in _choices(round_)}
        picked = [str(item) for item in selection if str(item) in known]
        return picked or None
    return None


def build_item(detail, quantity=1, selection=None, product_code=None):
    """Build one `calculate-price` item from a `query-meal-detail` payload.

    Args:
        detail: the `data` object returned by `query-meal-detail`.
        quantity: how many of this product to buy.
        selection: optional choice codes. A list of codes applies to any round
            that contains them; a dict maps round label -> code(s).
        product_code: override for the parent code (rarely needed).

    Raises:
        MealConfigError: a required round has no usable choice, an unknown
            choice code was requested, or the choice count is out of range.
    """
    if not isinstance(detail, dict) or not detail.get("code"):
        raise MealConfigError("餐品详情缺少 code，无法配置")
    quantity = int(quantity if quantity is not None else 1)
    if quantity < 1:
        raise MealConfigError("数量必须大于等于 1")

    parent = str(product_code or detail.get("code"))
    rounds = _rounds(detail)
    if not rounds:
        return {"productCode": parent, "quantity": quantity}

    _validate_selection(detail, selection)

    round_list = []
    for index, round_ in enumerate(rounds):
        key = _round_key(round_, index)
        choices = _choices(round_)
        if not choices:
            continue
        explicit = _selected_codes(round_, key, selection)
        picked = []
        if explicit:
            by_code = {str(c.get("code")): c for c in choices}
            unknown = [code for code in explicit if code not in by_code]
            if unknown:
                raise MealConfigError(
                    "轮次 %s「%s」没有这些选项：%s；可选：%s"
                    % (key, round_.get("name") or "", "、".join(unknown),
                       "、".join("%s(%s)" % (c.get("name"), c.get("code")) for c in choices))
                )
            for code in explicit:
                picked.append(by_code[code])
        else:
            default = _default_choice(round_)
            if default is not None:
                picked.append(default)
            elif _is_required(round_):
                raise MealConfigError(
                    "轮次 %s「%s」是必选组（minQuantity=%s），但没有默认选项，需要用户先选"
                    % (key, round_.get("name") or "", round_.get("minQuantity"))
                )
            else:
                continue  # optional round, user did not pick anything

        minimum = int(round_.get("minQuantity") or 0)
        maximum = int(round_.get("maxQuantity") or 0)
        if len(picked) < max(minimum, 1):
            raise MealConfigError(
                "轮次 %s「%s」至少需要 %s 项，当前 %s 项"
                % (key, round_.get("name") or "", max(minimum, 1), len(picked))
            )
        if maximum not in (0, UNLIMITED) and len(picked) > maximum:
            raise MealConfigError(
                "轮次 %s「%s」最多 %s 项，当前 %s 项"
                % (key, round_.get("name") or "", maximum, len(picked))
            )

        combo = []
        for choice in picked:
            chosen = int(choice.get("quantity") or 0)
            combo.append({"code": str(choice.get("code")), "quantity": max(chosen, 1)})
        round_list.append({"round": key, "comboItemList": combo})

    item = {"productCode": parent, "quantity": quantity}
    if round_list:
        item["roundList"] = round_list
    return item


def explain_failure(code, message, detail=None):
    """Turn a `calculate-price` failure into an actionable hint.

    `600012 促销规则不支持该商品` is what the API returns when a choice code was
    sent as `productCode`, or when a coupon is attached to a product the coupon
    does not cover. Callers must not guess which one it is.
    """
    hint = ""
    if code == 600012:
        hint = ("促销规则不支持该商品：常见原因是把选项编码当成了商品编码，"
                "或者券与该商品不匹配。先确认 productCode 是否为父商品，再确认券的适用商品。")
    elif code == 600010:
        hint = "商品不存在或不在该门店当前菜单：重新查 query-meals 确认。"
    result = {"success": False, "code": code, "message": message}
    if hint:
        result["hint"] = hint
    if detail:
        result["product"] = {"code": detail.get("code"), "name": detail.get("name")}
    return result


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    item = sub.add_parser("item", help="生成 calculate-price 的商品项")
    item.add_argument("--detail", type=Path, required=True)
    item.add_argument("--quantity", type=int, default=1)
    item.add_argument("--choose", nargs="*", default=None,
                      help="指定选项编码，如 --choose 1217")

    roles = sub.add_parser("roles", help="查看编码角色与轮次结构")
    roles.add_argument("--detail", type=Path, required=True)
    roles.add_argument("--code", default=None, help="判断某个编码是否为该商品的选项")

    args = parser.parse_args()
    try:
        detail = _read(args.detail)
        detail = detail.get("data", detail)
        if args.command == "roles":
            result = describe(detail)
            if args.code:
                result["lookup"] = find_choice(detail, args.code)
        else:
            result = build_item(detail, args.quantity, args.choose)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (MealConfigError, OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
