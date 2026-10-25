"""Cross-step edits must retain the user's current purchasing decisions."""
import json
import subprocess
import sys
from pathlib import Path

from test_flow_continuity import FlowFixture, ROOT, basket, cc, dv, nc, product, row, ss


class PlanEditingTests(FlowFixture):
    def test_raw_official_nutrition_response_can_be_loaded(self):
        path = self.root / "nutrition.json"
        path.write_text(json.dumps({"success": True, "code": 200, "data":
            "[2]{productName,nutritionDescription,energyKj,energyKcal}:\n"
            "  测试餐品甲,null,418,100\n  测试餐品乙,null,836,200"}))
        table = basket.load_nutrition(path)
        result = basket.compute_calories([
            {"name": "测试餐品甲", "quantity": 2},
            {"name": "测试餐品乙", "quantity": 1}], table)
        self.assertEqual(result["total_kcal"], 400)

    def test_malformed_nutrition_response_is_an_explicit_error(self):
        path = self.root / "nutrition.json"
        path.write_text(json.dumps({"data": "服务异常"}))
        with self.assertRaises(ValueError):
            basket.load_nutrition(path)

    def test_flavour_change_keeps_previously_selected_quantity(self):
        dv.select(self.db, self.session, ["U06"])
        dv.plan_entry(self.db, self.session, self.plan_file,
                      quantities={"奥利奥麦旋风": 2})
        plan = dv.plan_entry(self.db, self.session, self.plan_file,
                             choices={"U06": {"麦旋风口味二选一": "草莓麦旋风"}})
        ice = next(i for i in plan["items"] if i["nutrition_name"] == "草莓麦旋风")
        self.assertEqual(ice["quantity"], 2)
        payload = basket.build_price_items(plan)
        self.assertEqual(payload["items"][1]["quantity"], 2)
        nutrition = basket.compute_calories(plan["items"], {"菠萝派": 10, "草莓麦旋风": 20})
        self.assertEqual(nutrition["total_kcal"], 50)
        plan = dv.plan_entry(self.db, self.session, self.plan_file,
                             quantities={"草莓麦旋风": 3})
        self.assertEqual(plan["items"][1]["quantity"], 3)

    def test_flavour_quantity_does_not_leak_to_a_replacement_recipe(self):
        dv.select(self.db, self.session, ["U06"])
        dv.plan_entry(self.db, self.session, self.plan_file,
                      quantities={"奥利奥麦旋风": 2})
        dv.select(self.db, self.session, ["U01"], replace=True)
        plan = dv.plan_entry(self.db, self.session, self.plan_file)
        self.assertEqual(next(i for i in plan["items"] if i["nutrition_name"] == "奥利奥麦旋风")["quantity"], 1)

    def test_invalid_edit_preserves_plan_file_bytes(self):
        dv.select(self.db, self.session, ["U18"])
        dv.plan_entry(self.db, self.session, self.plan_file)
        before = self.plan_file.read_bytes()
        for edits in [{"quantities": {"麦香鱼": 0}},
                      {"quantities": {"麦香鱼": True}}]:
            with self.assertRaises(ValueError):
                dv.plan_entry(self.db, self.session, self.plan_file, **edits)
            self.assertEqual(before, self.plan_file.read_bytes())
        self.assertEqual(len(dv.plan_entry(self.db, self.session, self.plan_file)["items"]), 2)

    def test_invalid_flavour_preserves_plan_file_bytes(self):
        dv.select(self.db, self.session, ["U06"])
        dv.plan_entry(self.db, self.session, self.plan_file)
        before = self.plan_file.read_bytes()
        with self.assertRaises(ValueError):
            dv.plan_entry(self.db, self.session, self.plan_file,
                          choices={"U06": {"派口味二选一": "苹果派"}})
        self.assertEqual(before, self.plan_file.read_bytes())

    def test_basket_cli_rejects_invalid_edit_without_saving(self):
        dv.select(self.db, self.session, ["U18"])
        dv.plan_entry(self.db, self.session, self.plan_file)
        before = self.plan_file.read_bytes()
        result = subprocess.run([sys.executable, "-B", str(ROOT / "skills/mcd-hidden-explorer/scripts/basket.py"),
                                 "plan", "--plan-file", str(self.plan_file),
                                 "--quantities", '{"麦香鱼":0}'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(before, self.plan_file.read_bytes())

    def test_clear_selection_does_not_restore_old_items(self):
        dv.select(self.db, self.session, ["U18"])
        dv.plan_entry(self.db, self.session, self.plan_file)
        ss.clear_selection(self.session)
        result = dv.plan_entry(self.db, self.session, self.plan_file)
        self.assertEqual(result["items"], [])
        coupons = dv.coupon_check_entry(self.db, self.session, [], plan_file=self.plan_file)
        self.assertEqual(coupons["item_count"], 0)
        with self.assertRaises(ValueError):
            basket.build_price_items(result)

    def test_coupon_check_refreshes_selection_without_reverting_edits(self):
        dv.select(self.db, self.session, ["U18"])
        dv.plan_entry(self.db, self.session, self.plan_file)
        dv.select(self.db, self.session, ["U06"], replace=True)
        dv.purchase_entry(self.db, self.session)
        result = dv.coupon_check_entry(self.db, self.session, [])
        self.assertNotIn("麦香鱼", result["checked_items"])
        self.assertIn("派（菠萝派）", result["checked_items"])


class OptionalPurchaseTests(FlowFixture):
    def setUp(self):
        super().setUp()
        source, policy = self.root / "source.json", self.root / "roles.json"
        data = json.loads(source.read_text())
        data["entries"].append(row("U11", "玉米冰淇淋", [
            product("小杯玉米杯", "4437"),
            product("奥利奥麦旋风", "1217", parent="9900008754", parent_name="经典麦旋风"),
            product("中薯条", "4810")]))
        rules = json.loads(policy.read_text())
        rules["recipes"]["U11"] = {"optional_codes": ["4810"]}
        source.write_text(json.dumps(data, ensure_ascii=False))
        policy.write_text(json.dumps(rules, ensure_ascii=False))
        nc.sync_database(source, self.db, policy)

    def test_optional_addition_persists_across_flavour_and_quantity_edits(self):
        dv.select(self.db, self.session, ["U11", "U06"])
        initial = dv.plan_entry(self.db, self.session, self.plan_file)
        self.assertNotIn("中薯条", [i["nutrition_name"] for i in initial["items"]])
        plan = dv.plan_entry(self.db, self.session, self.plan_file,
                             optional={"U11": ["中薯条"]}, quantities={"中薯条": 2})
        plan = dv.plan_entry(self.db, self.session, self.plan_file,
                             choices={"U06": {"派口味二选一": "香芋派"}})
        fries = next(i for i in plan["items"] if i["nutrition_name"] == "中薯条")
        self.assertEqual(fries["quantity"], 2)
        self.assertIn("4810", [i["productCode"] for i in basket.build_price_items(plan)["items"]])
        coupon = cc.check_plan(plan, [{"title": "test only", "products": [{"productName": "中薯条"}]}])
        self.assertEqual(next(i for i in coupon["items"] if i["display_name"] == "中薯条")["quantity"], 2)
        plan = dv.plan_entry(self.db, self.session, self.plan_file, optional={"U11": []})
        self.assertNotIn("中薯条", [i["nutrition_name"] for i in plan["items"]])

    def test_unknown_optional_item_is_not_written_to_plan(self):
        dv.select(self.db, self.session, ["U11"])
        dv.plan_entry(self.db, self.session, self.plan_file)
        before = self.plan_file.read_bytes()
        with self.assertRaises(ValueError):
            dv.plan_entry(self.db, self.session, self.plan_file, optional={"U11": ["不存在的配料"]})
        self.assertEqual(before, self.plan_file.read_bytes())

    def test_optional_cli_reaches_the_purchase_plan(self):
        dv.select(self.db, self.session, ["U11"])
        result = subprocess.run([sys.executable, "-B", str(ROOT / "skills/mcd-hidden-explorer/scripts/discover.py"),
            "plan", "--session", str(self.session), "--database", str(self.db),
            "--plan-file", str(self.plan_file), "--optional", '{"U11":["中薯条"]}'],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("中薯条", [i["nutrition_name"] for i in json.loads(result.stdout)["items"]])
