"""跨脚本衔接回归：同一份当前购买清单贯穿份数、口味、核券。

这些用例针对的是"每一步单独看都对、连起来就断"的问题，所以都跨脚本：
session_state → discover.select/plan → basket → coupon_check。
"""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "mcd-hidden-explorer" / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


import numbered_catalog as nc  # noqa: E402
import session_state as ss  # noqa: E402
import discover as dv  # noqa: E402
import basket  # noqa: E402
import coupon_check as cc  # noqa: E402


def product(name, code, parent=None, parent_name=None, **extra):
    item = {"name": name, "code": code, "time": "12:00", "evidence": "e.json", **extra}
    if parent:
        item["parent_code"] = parent
        item["parent_name"] = parent_name
    return item


def row(ident, title, products, category="测试"):
    return {"id": ident, "title": title, "card_title": title, "category": category,
            "products": products, "image_ids": [], "source_ids": [], "tested_by_project": False}


class FlowFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / "numbers.sqlite"
        source, policy = self.root / "source.json", self.root / "roles.json"
        data = {"entries": [
            row("U01", "脆薯饼夹麦旋风", [
                product("脆薯饼", "4825"),
                product("奥利奥麦旋风", "1217", parent="9900008754", parent_name="经典麦旋风"),
            ]),
            row("U04", "双吉四层牛肉堡", [product("双层吉士汉堡", "1120")]),
            row("U06", "派拌麦旋风", [
                product("菠萝派", "4105", parent="9900008752", parent_name="派"),
                product("香芋派", "4106", parent="9900008752", parent_name="派"),
                product("奥利奥麦旋风", "1217", parent="9900008754", parent_name="经典麦旋风"),
                product("草莓麦旋风", "4900", parent="9900008754", parent_name="经典麦旋风"),
            ]),
            row("U08", "薯条摇摇乐", [product("中薯条", "4810"), product("麦乐鸡5块", "1401")]),
            row("U18", "麦香鱼夹菠萝派", [
                product("麦香鱼", "1600"),
                product("菠萝派", "4105", parent="9900008752", parent_name="派"),
            ], category="汉堡重组"),
            row("U23", "鸡翅薯条夹心", [product("麦辣鸡翅2块", "4700"), product("中薯条", "4810")]),
            row("U02", "薯条夹心堡", [product("中薯条", "4810"), product("脆薯饼", "4825")]),
            row("U03", "薯条拌玉米", [product("中薯条", "4810"), product("小杯玉米杯", "4437")]),
        ], "images": [], "sources": []}
        source.write_text(json.dumps(data, ensure_ascii=False), encoding="utf8")
        policy.write_text(json.dumps({"recipes": {
            "U01": {"purchase_quantities": {"4825": {
                "quantity": 2, "status": "source_reported", "basis": "卡片写两片脆薯饼"}}},
            "U04": {"purchase_quantities": {"1120": {
                "quantity": 2, "status": "purchase_suggestion", "basis": "资料建议两个双吉"}}},
            "U06": {"choice_groups": [
                {"name": "派口味二选一", "codes": ["4105", "4106"], "default_code": "4105"},
                {"name": "麦旋风口味二选一", "codes": ["1217", "4900"], "default_code": "1217"},
            ]},
        }}, ensure_ascii=False), encoding="utf8")
        nc.sync_database(source, self.db, policy)
        self.session = self.root / "session.json"
        ss.init_session(self.session)
        self.plan_file = self.root / "plan.json"


class SelectionToPlanTests(FlowFixture):
    def test_select_then_plan_is_not_empty(self):
        # 旧问题：selection 只给餐品名字符串，plan 收到后得到空清单。
        dv.select(self.db, self.session, ["U18"])
        plan = dv.plan_entry(self.db, self.session)
        self.assertEqual([i["nutrition_name"] for i in plan["items"]], ["麦香鱼", "菠萝派"])
        self.assertEqual(plan["items"][1]["parent_code"], "9900008752")

    def test_selection_exposes_structured_products(self):
        view = dv.select(self.db, self.session, ["U18"])
        required = view["methods"][0]["required_products"]
        self.assertIsInstance(required[0], dict)
        self.assertEqual(required[0]["reference_menu"]["code"], "1600")

    def test_default_flavour_survives_select_then_plan(self):
        # 旧问题：U06 直接进 plan 会报"需要先选口味"。
        dv.select(self.db, self.session, ["U06"])
        plan = dv.plan_entry(self.db, self.session)
        self.assertEqual([i["nutrition_name"] for i in plan["items"]], ["菠萝派", "奥利奥麦旋风"])
        self.assertEqual([q["is_default"] for q in plan["questions"]], [True, True])

    def test_plan_keeps_number_and_image_link(self):
        view = dv.select(self.db, self.session, ["U18"])
        self.assertEqual(view["methods"][0]["display_number"], "18号")
        plan = dv.plan_entry(self.db, self.session)
        self.assertIn("麦香鱼", plan["items"][0]["display_name"])


class QuantityTests(FlowFixture):
    def test_source_rule_gives_two_hash_browns(self):
        dv.select(self.db, self.session, ["U01"])
        plan = dv.plan_entry(self.db, self.session)
        hash_brown = plan["items"][0]
        self.assertEqual(hash_brown["quantity"], 2)
        self.assertEqual(hash_brown["quantity_basis"][0]["status"], "source_reported")

    def test_purchase_suggestion_gives_two_sandwiches(self):
        dv.select(self.db, self.session, ["U04"])
        plan = dv.plan_entry(self.db, self.session)
        self.assertEqual(plan["items"][0]["quantity"], 2)
        self.assertEqual(plan["items"][0]["quantity_basis"][0]["status"], "purchase_suggestion")

    def test_shared_fries_default_to_two_then_user_sets_one(self):
        dv.select(self.db, self.session, ["U08", "U23"])
        plan = dv.plan_entry(self.db, self.session, self.plan_file)
        fries = next(i for i in plan["items"] if i["nutrition_name"] == "中薯条")
        self.assertEqual(fries["quantity"], 2)
        self.assertTrue(fries["shared"])

        plan = dv.plan_entry(self.db, self.session, self.plan_file, quantities={"中薯条": 1})
        fries = next(i for i in plan["items"] if i["nutrition_name"] == "中薯条")
        self.assertEqual(fries["quantity"], 1)
        self.assertEqual(fries["quantity_source"], "user_override")

        # 再次重算不能被原配方覆盖回 2
        plan = dv.plan_entry(self.db, self.session, self.plan_file)
        fries = next(i for i in plan["items"] if i["nutrition_name"] == "中薯条")
        self.assertEqual(fries["quantity"], 1)

    def test_flavour_swap_survives_recompute(self):
        dv.select(self.db, self.session, ["U06"])
        dv.plan_entry(self.db, self.session, self.plan_file,
                      choices={"U06": {"派口味二选一": "香芋派"}})
        plan = dv.plan_entry(self.db, self.session, self.plan_file)
        self.assertEqual(plan["items"][0]["nutrition_name"], "香芋派")

    def test_override_rejects_non_positive(self):
        dv.select(self.db, self.session, ["U08"])
        with self.assertRaises(ValueError):
            dv.plan_entry(self.db, self.session, quantities={"中薯条": 0})


class PlanCouponTests(FlowFixture):
    def _plan(self, choices=None):
        dv.select(self.db, self.session, ["U06"])
        return dv.plan_entry(self.db, self.session, self.plan_file, choices=choices)

    def test_coupon_check_reads_changed_flavour(self):
        plan = self._plan({"U06": {"派口味二选一": "香芋派",
                                   "麦旋风口味二选一": "草莓麦旋风"}})
        result = cc.check_plan(plan, [{"title": "香芋派券", "products": [{"productName": "香芋派"}]}])
        covered = [i for i in result["items"] if i["display_name"].startswith("派")]
        self.assertEqual(covered[0]["coupons"][0]["status"], "covers_all")

    def test_coupon_check_does_not_use_old_default(self):
        plan = self._plan({"U06": {"派口味二选一": "香芋派"}})
        result = cc.check_plan(plan, [{"title": "菠萝派券", "products": [{"productName": "菠萝派"}]}])
        pie = [i for i in result["items"] if i["display_name"].startswith("派")][0]
        self.assertEqual(pie["coupons"][0]["status"], "none")
        self.assertNotIn("菠萝派", pie["coupons"][0]["covered"])

    def test_expired_coupon_is_not_best(self):
        plan = self._plan()
        result = cc.check_plan(plan, [{
            "title": "过期奥利奥券", "products": [{"productName": "奥利奥麦旋风"}],
            "validUntil": "2026-10-20 23:59"}], now=cc._parse_time("2026-10-25 13:30"))
        shake = [i for i in result["items"] if "麦旋风" in i["display_name"]][0]
        self.assertFalse(shake["coupons"][0]["valid_now"])
        self.assertFalse(shake["coupons"][0]["is_candidate"])
        self.assertIsNone(shake["best_coupon"])
        self.assertFalse(shake["has_covering_coupon"])

    def test_unknown_validity_stays_candidate(self):
        plan = self._plan()
        result = cc.check_plan(plan, [{
            "title": "无有效期券", "products": [{"productName": "奥利奥麦旋风"}]}])
        shake = [i for i in result["items"] if "麦旋风" in i["display_name"]][0]
        self.assertIsNone(shake["coupons"][0]["valid_now"])
        self.assertTrue(shake["coupons"][0]["is_candidate"])

    def test_coupon_without_products_is_insufficient_info(self):
        plan = self._plan()
        result = cc.check_plan(plan, [{"title": "只有名字的券"}])
        pie = [i for i in result["items"] if i["display_name"].startswith("派")][0]
        self.assertEqual(pie["coupons"][0]["status"], "insufficient_info")
        self.assertFalse(pie["coupons"][0]["is_candidate"])
        self.assertTrue(pie["insufficient_coupon_info"])


class RerollAndReplaceTests(FlowFixture):
    def test_by_product_reroll_gives_different_cards(self):
        first = [m["id"] for m in dv.product_entry(self.db, self.session, "薯条", limit=3)["methods"]]
        second = [m["id"] for m in dv.product_entry(self.db, self.session, "薯条", limit=3)["methods"]]
        self.assertEqual(len(first), 3)
        self.assertTrue(set(first).isdisjoint(second), "换一批不能重复上一批")

    def test_by_product_exhausts_without_duplicating_round(self):
        dv.product_entry(self.db, self.session, "薯条", limit=3)
        dv.product_entry(self.db, self.session, "薯条", limit=3)
        third = dv.product_entry(self.db, self.session, "薯条", limit=3)
        self.assertEqual(third["count"], 0)
        self.assertIsNone(third["round_id"])
        self.assertTrue(third["exhausted"])
        self.assertEqual(len(ss.load_session(self.session)["rounds"]), 2)

    def test_invalid_replace_keeps_existing_selection(self):
        dv.select(self.db, self.session, ["U18"])
        with self.assertRaises(ValueError):
            dv.select(self.db, self.session, ["U99"], replace=True)
        self.assertEqual(ss.load_session(self.session)["current_selection"], ["U18"])

    def test_round_mismatch_replace_keeps_existing_selection(self):
        dv.random_entry(self.db, self.session, limit=3, seed=1)
        dv.select(self.db, self.session, ["U18"])
        shown = ss.load_session(self.session)["rounds"][0]["shown_methods"]
        outsider = next(mid for mid in ["U08", "U23", "U02", "U03", "U04"] if mid not in shown)
        with self.assertRaises(ValueError):
            dv.select(self.db, self.session, [outsider], round_id="RND001", replace=True)
        self.assertEqual(ss.load_session(self.session)["current_selection"], ["U18"])


class PriceItemContractTests(FlowFixture):
    def test_price_items_use_parent_plus_option(self):
        dv.select(self.db, self.session, ["U18"])
        plan = dv.plan_entry(self.db, self.session)
        items = basket.build_price_items(plan)["items"]
        self.assertEqual(items[0], {"productCode": "1600", "quantity": 1})
        self.assertEqual(items[1]["productCode"], "9900008752")
        self.assertEqual(items[1]["roundList"][0]["comboItemList"][0]["code"], "4105")

    def test_price_items_keep_swapped_flavour(self):
        dv.select(self.db, self.session, ["U06"])
        plan = dv.plan_entry(self.db, self.session, choices={"U06": {"派口味二选一": "香芋派"}})
        items = basket.build_price_items(plan)["items"]
        codes = [i["roundList"][0]["comboItemList"][0]["code"] for i in items if "roundList" in i]
        self.assertEqual(codes[0], "4106")

    def test_price_items_carry_user_quantity(self):
        dv.select(self.db, self.session, ["U01"])
        plan = dv.plan_entry(self.db, self.session)
        items = basket.build_price_items(plan)["items"]
        self.assertEqual(items[0]["quantity"], 2)


if __name__ == "__main__":
    unittest.main()
