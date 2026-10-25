#!/usr/bin/env python3
"""Single recommendation entry for the hidden-eating explorer.

Three entries — random, by product, by coupon — all write to the same session
record, so switching entry keeps the selected list and the shown order.

Read-only over the numbered database; no network calls, no ordering.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numbered_catalog as nc
import session_state as ss
from image_delivery import inline_response

ENTRIES = [
    {"id": "random", "label": "随机看看",
     "examples": ["随便推荐几个", "换一批", "随机看看有什么"]},
    {"id": "by_product", "label": "按餐品找",
     "examples": ["想吃薯条相关的", "有麦香鱼的吗", "帮我找玉米的做法"]},
    {"id": "by_coupon", "label": "按优惠找",
     "examples": ["按优惠推荐", "我今天有什么券能用在这些吃法上"]},
]


def _json_arg(value):
    """Inline JSON or a file path; empty means no override."""
    if not value:
        return {}
    text = str(value).strip()
    if text.startswith("{") or text.startswith("["):
        return json.loads(text)
    return json.loads(Path(text).read_text(encoding="utf-8"))


def _cards_by_id(database, ids):
    if not ids:
        return {}
    payload = nc.cards(database, ids)
    return {card["id"]: card for card in payload["cards"]}


def _attach(methods, cards):
    for method in methods:
        card = cards.get(method["id"], {})
        method["caption"] = card.get("caption")
        method["hero_image_absolute_path"] = card.get("hero_image_absolute_path")
        method["images"] = card.get("images", [])
        method["images_ready"] = card.get("images_ready", False)
        method["image_markdown"] = card.get("image_markdown", "")
    return methods


def _round(database, session, ids, query, source):
    rnd = ss.recommend_round(session, ids, query=query, source=source, database=database)
    return rnd["round_id"]


def _state_summary(session):
    state = ss.load_session(session)
    names = []
    for record in reversed(state["selections"]):
        if record["method_id"] in state["current_selection"] and "deselected_at" not in record:
            label = record.get("name") or record["method_id"]
            number = record.get("number")
            names.append("{}({})".format(label, str(number) + "号" if number else record["method_id"]))
    names.reverse()
    return {"current_selection": list(state["current_selection"]),
            "phase": state["phase"],
            "plan_file": state.get("purchase_plan_file"),
            "current_selection_labels": names,
            "summary": "当前选中：" + ("、".join(names) if names else "还没有选中任何吃法")}


def random_entry(database, session, limit=3, seed=None):
    seen = ss.seen_methods(session)
    result = nc.random_batch(database, limit=limit, seen=seen, seed=seed)
    ids = [m["id"] for m in result["methods"]]
    round_id = _round(database, session, ids, "随机看看", "random") if ids else None
    result["round_id"] = round_id
    result["methods"] = _attach(result["methods"], _cards_by_id(database, ids))
    result["session"] = _state_summary(session)
    return inline_response(result)


def product_entry(database, session, query, limit=3):
    # "换一批" must not repeat the same three cards: the theme stays, the shown
    # IDs are excluded, and an exhausted theme says so instead of looping.
    seen = ss.seen_methods(session)
    result = nc.find_by_product(database, query, limit=limit, exclude=seen)
    ids = [m["id"] for m in result["methods"]]
    if ids:
        result["round_id"] = _round(database, session, ids, query, "by-product")
        result["methods"] = _attach(result["methods"], _cards_by_id(database, ids))
    else:
        result["round_id"] = None  # No match must not create a reviewable round.
    result["session"] = _state_summary(session)
    return inline_response(result)


def coupon_entry(database, session, coupon, limit=3):
    result = nc.coupon_link(database, coupon, limit=limit)
    primary = list(result.get("methods") or [])
    supplementary = list(result.get("supplementary") or [])
    ids = [m["id"] for m in primary] + [m["id"] for m in supplementary]
    if ids:
        result["round_id"] = _round(database, session, ids, "按优惠：" + str(coupon.get("title") or ""),
                                    "by-coupon")
        cards = _cards_by_id(database, ids)
        result["methods"] = _attach(primary, cards)
        result["supplementary"] = _attach(supplementary, cards)
        result["shown_ids"] = ids
        result["has_direct_match"] = bool(primary)
    else:
        result["round_id"] = None
        result["has_direct_match"] = False
    result["session"] = _state_summary(session)
    return inline_response(result)


def coupon_check_entry(database, session, coupons, ids=None, now=None, plan_file=None):
    """Check the persisted purchase plan; never rebuild recipe defaults.

    Explicit IDs without a session remain an offline developer check over the
    supplied coupon data. A normal session must first enter purchasing.
    """
    import coupon_check
    from datetime import datetime
    if isinstance(now, str):
        now = coupon_check._parse_time(now) or datetime.now()
    if Path(session).is_file():
        state = ss.load_session(session)
        if state["current_selection"] and state["phase"] != "purchasing":
            raise ValueError("尚未进入购买阶段；选号仅加入备选，用户要求配置或核价后才调用 purchase")
        if ids and list(ids) != state["current_selection"]:
            raise ValueError("核券必须使用当前完整购买清单，不能用编号子集替代已调整计划")
        plan = plan_entry(database, session, plan_file)
        result = coupon_check.check_plan(plan, coupons, now=now)
        result["round_id"] = None
        result["plan_file"] = plan["plan_state"]["plan_file"]
        result["checked_items"] = [item.get("display_name") for item in plan.get("items", [])]
        result["checked_quantities"] = [item["quantity"] for item in plan.get("items", [])]
        result["session"] = _state_summary(session)
        return inline_response(result)
    if plan_file:
        raise ValueError("缺少计划所属会话，不能确认购买清单版本")
    targets = list(ids or [])
    if not targets:
        targets = list(ss.load_session(session)["current_selection"])
    if not targets:
        return inline_response({"result_schema_version": 1, "entry": "coupon_check",
                                "round_id": None, "method_count": 0, "methods": [],
                                "notice": "当前清单为空，先选编号再核券。"})
    result = coupon_check.check_selection(database, targets, coupons, now=now)
    result["round_id"] = None
    try:
        result["session"] = _state_summary(session)
    except (OSError, ValueError):
        # 显式给了 --ids 时，没有会话文件也要能核券。
        result["session"] = {"current_selection": targets,
                             "current_selection_labels": [],
                             "summary": "当前选中：" + "、".join(targets)}
    return inline_response(result)


def plan_entry(database, session, plan_file=None, choices=None, quantities=None, optional=None):
    """Build the purchase plan straight from the current selection.

    This is the contract between selection and pricing: the session already holds
    full method records, so no caller has to re-query a different entry point or
    hand-edit a temporary file.
    """
    import basket
    context = ss.load_session(session)
    registered = context.get("purchase_plan_file")
    plan_file = Path(plan_file or registered or
                     Path(session).with_name(Path(session).stem + ".plan.json")).resolve()
    if plan_file == Path(session).resolve():
        raise ValueError("购买计划文件不能覆盖会话文件")
    if registered and plan_file != Path(registered).resolve():
        raise ValueError("本会话已有购买计划，后续步骤须复用：" + registered)
    if registered and not plan_file.is_file():
        raise ValueError("当前购买计划文件丢失，停止核券核价；请恢复文件或明确清空后重新配置")
    state = None
    if plan_file.is_file():
        state = basket.load_plan_state(plan_file)
        owner = state.get("session")
        if owner and Path(owner).resolve() != Path(session).resolve():
            raise ValueError("购买计划属于其他会话，不能混用")
        identity = context.get("session_id", context["created_at"])
        if (state.get("session_id", identity) != identity or
                state.get("plan_generation", 0) != context["plan_generation"]):
            state = None  # Explicit clear/reset starts a fresh purchase plan.
    view = selection_view(database, session)
    methods = view["methods"]
    if not methods and state is None and not registered and not plan_file.is_file():
        raise ValueError("当前清单为空，先选编号再生成购买清单")
    state = basket.new_plan_state(methods, session=session) if state is None else {
        **state, "methods": methods}
    state.update(session=str(Path(session).resolve()),
                 session_id=context.get("session_id", context["created_at"]),
                 plan_generation=context["plan_generation"])
    if not methods:
        state.update(choices={}, quantities={}, optional={})
    state = basket.merge_overrides(state, choices or {}, quantities or {}, optional or {})
    plan = basket.plan_from_state(state)
    state = basket.save_plan_state(plan_file, state)
    context["purchase_plan_file"] = str(plan_file)
    ss.save_session(session, context)
    plan["entry"] = "plan"
    plan["session"] = _state_summary(session)
    plan["plan_state"] = {"choices": state.get("choices"),
                          "quantities": state.get("quantities"),
                          "optional": state.get("optional"),
                          "plan_file": str(plan_file) if plan_file else None}
    return inline_response(plan)


def purchase_entry(database, session, plan_file=None, choices=None, quantities=None, optional=None):
    """Enter configuration after an explicit purchase/quote request, not a pick."""
    if not ss.load_session(session)["current_selection"]:
        raise ValueError("当前清单为空，先选编号再开始购买配置")
    result = plan_entry(database, session, plan_file, choices, quantities, optional)
    ss.set_phase(session, "purchasing")
    result["entry"] = "purchase"
    result["session"] = _state_summary(session)
    result["next_step"] = {**COUPON_CHECK_STEP,
                           "plan_file": result["plan_state"]["plan_file"]}
    result["order_created"] = False
    return result


def browse_entry(database, session):
    """Pause purchasing while keeping the selection and all saved edits."""
    ss.set_phase(session, "exploring")
    result = selection_view(database, session)
    result["next_step"] = EXPLORING_STEP
    return result


def _resolved_by_id(database, ids):
    """Full method records (products as objects, choices, quantities) by ID.

    The card payload only carries display strings; `basket.py plan` needs the
    structured record. Resolving here is what makes "select then plan" work
    without the caller switching to a different entry point.
    """
    numeric = [ident for ident in ids if str(ident).startswith("U")]
    if not numeric:
        return {}
    payload = nc.resolve(database, " ".join(numeric))
    return {method["id"]: method for method in payload["methods"]}


def selection_view(database, session):
    state = ss.load_session(session)
    ids = list(state["current_selection"])
    cards = _cards_by_id(database, ids) if ids else {}
    resolved = _resolved_by_id(database, ids) if ids else {}
    methods = []
    for ident in ids:
        card = cards.get(ident, {})
        method = resolved.get(ident, {})
        methods.append({
            "id": ident,
            "number": method.get("number"),
            "display_number": card.get("display_number") or method.get("display_number"),
            "card_title": card.get("card_title") or method.get("card_title"),
            "name": method.get("name"),
            "caption": card.get("caption"),
            "hero_image_absolute_path": card.get("hero_image_absolute_path"),
            "images_ready": card.get("images_ready", False),
            "required_products": method.get("required_products", []),
            "optional_products": method.get("optional_products", []),
            "product_choices": method.get("product_choices", []),
            "default_plan": method.get("default_plan", []),
            "has_choices": method.get("has_choices", False),
        })
    summary = _state_summary(session)
    return inline_response({"result_schema_version": 1, "entry": "selection",
            "count": len(methods), "methods": methods, **summary})


def select(database, session, ids, round_id=None, replace=None):
    """Add (or replace) the current selection, then report what is selected.

    Replacing validates the new list first: a rejected ID must leave the old
    selection exactly as it was, not empty it.
    """
    if replace:
        ss.validate_selection(session, ids, round_id, database)
        current = ss.load_session(session)["current_selection"]
        drops = [mid for mid in current if mid not in ids]
        if drops:
            ss.deselect_methods(session, drops)
    ss.select_methods(session, ids, round_id=round_id, database=database)
    result = selection_view(database, session)
    result["next_step"] = ({"action": "refresh-plan", "network_calls": [],
                            "note": "购买阶段的选号编辑先重算同一计划；不重复发起购买或下单。"}
                           if result["phase"] == "purchasing" else EXPLORING_STEP)
    return result


EXPLORING_STEP = {
    "action": "continue-exploring",
    "network_calls": [],
    "requires_purchase_request": True,
    "note": "选号只加入备选；不查个人券、不问门店。用户要求配置或核价后调用 purchase。",
}


# Only purchase_entry exposes this follow-up; selecting never triggers it.
COUPON_CHECK_STEP = {
    "action": "coupon-check",
    "requires_user_confirmation": False,
    "requires_selection": True,
    "read_only": True,
    "requires_phase": "purchasing",
    "requires_current_plan": True,
    "store_check_requires": ["store", "take_way"],
    "order": ["query-my-coupons", "query-store-coupons", "coupon-check"],
    "command": ("discover.py coupon-check --session <session> --database <db> "
                "--coupons '<MCP 返回的券 JSON>'"),
    "report": ["哪张券覆盖了哪些餐品", "还缺哪些餐品", "券面价与整套支出分开说"],
    "note": ("已明确进入购买配置后统一核券，无须逐款再次询问；先补齐门店和取餐方式。"
             "券的可用性一律先标未确认；只有 calculate-price 返回成功才算可用。"
             "没有覆盖任何餐品就直接说没有适用券，不为凑券加买。"),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("entries")
    sub.add_parser("guide")

    rnd = sub.add_parser("random")
    rnd.add_argument("--database", type=Path, default=nc.PACKAGED_DATABASE)
    rnd.add_argument("--session", type=Path, required=True)
    rnd.add_argument("--limit", type=int, default=3)
    rnd.add_argument("--seed", type=int)

    prod = sub.add_parser("by-product")
    prod.add_argument("query")
    prod.add_argument("--database", type=Path, default=nc.PACKAGED_DATABASE)
    prod.add_argument("--session", type=Path, required=True)
    prod.add_argument("--limit", type=int, default=3)

    coup = sub.add_parser("by-coupon")
    coup.add_argument("--database", type=Path, default=nc.PACKAGED_DATABASE)
    coup.add_argument("--session", type=Path, required=True)
    coup.add_argument("--coupon", type=str, required=True)
    coup.add_argument("--limit", type=int, default=3)

    view = sub.add_parser("selection")
    view.add_argument("--database", type=Path, default=nc.PACKAGED_DATABASE)
    view.add_argument("--session", type=Path, required=True)

    browse = sub.add_parser("browse", help="返回探索，保留备选及已修改配置")
    browse.add_argument("--database", type=Path, default=nc.PACKAGED_DATABASE)
    browse.add_argument("--session", type=Path, required=True)

    check = sub.add_parser("coupon-check")
    check.add_argument("--database", type=Path, default=nc.PACKAGED_DATABASE)
    check.add_argument("--session", type=Path, required=True)
    check.add_argument("--coupons", type=str, required=True,
                       help="MCP 返回的券，JSON 数组或 {\"coupons\":[...]}")
    check.add_argument("--ids", nargs="+", default=None,
                       help="默认用当前清单；指定则只查这几款")
    check.add_argument("--plan", dest="plan_file", type=Path, default=None,
                       help="按购买计划文件核券（含已改口味与已定份数）")
    check.add_argument("--now", default=None, help="覆盖当前时间，便于复现")

    for name in ("plan", "purchase"):
        plan = sub.add_parser(name)
        plan.add_argument("--database", type=Path, default=nc.PACKAGED_DATABASE)
        plan.add_argument("--session", type=Path, required=True)
        plan.add_argument("--plan-file", type=Path, default=None,
                          help="首次可指定；省略时自动复用本会话计划")
        plan.add_argument("--choices", default=None, help="口味改选 JSON，如 {\"U06\":{\"派口味二选一\":\"香芋派\"}}")
        plan.add_argument("--quantities", default=None, help="份数 JSON，如 {\"中薯条\":1}")
        plan.add_argument("--optional", default=None, help='可选餐品 JSON，如 {"U11":["中薯条"]}')

    pick = sub.add_parser("select")
    pick.add_argument("ids", nargs="+")
    pick.add_argument("--database", type=Path, default=nc.PACKAGED_DATABASE)
    pick.add_argument("--session", type=Path, required=True)
    pick.add_argument("--round", default=None)
    pick.add_argument("--replace", action="store_true",
                      help="Drop methods not listed, keeping only these.")

    drop = sub.add_parser("deselect")
    drop.add_argument("ids", nargs="+")
    drop.add_argument("--database", type=Path, default=nc.PACKAGED_DATABASE)
    drop.add_argument("--session", type=Path, required=True)

    args = parser.parse_args()
    try:
        if args.command == "entries":
            result = {"entries": ENTRIES}
        elif args.command == "guide":
            result = {"guide": "可以随机看看、按具体餐品找，也可以按优惠找。",
                      "entries": ENTRIES,
                      "note": "用户已经说清方向时直接推荐，不再询问模式。"}
        elif args.command == "random":
            result = random_entry(args.database, args.session, args.limit, args.seed)
        elif args.command == "by-product":
            result = product_entry(args.database, args.session, args.query, args.limit)
        elif args.command == "by-coupon":
            result = coupon_entry(args.database, args.session, json.loads(args.coupon), args.limit)
        elif args.command == "selection":
            result = selection_view(args.database, args.session)
        elif args.command == "browse":
            result = browse_entry(args.database, args.session)
        elif args.command == "coupon-check":
            result = coupon_check_entry(args.database, args.session,
                                        json.loads(args.coupons), args.ids, args.now,
                                        args.plan_file)
        elif args.command in ("plan", "purchase"):
            entry = purchase_entry if args.command == "purchase" else plan_entry
            result = entry(args.database, args.session, args.plan_file,
                                _json_arg(args.choices), _json_arg(args.quantities),
                                _json_arg(args.optional))
        elif args.command == "select":
            result = select(args.database, args.session, args.ids, args.round, args.replace)
        else:
            ss.deselect_methods(args.session, args.ids)
            result = selection_view(args.database, args.session)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
