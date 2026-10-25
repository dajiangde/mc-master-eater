"""Intent boundaries and persisted edits across independent command calls."""
import json
import subprocess
import sys
from pathlib import Path

from test_flow_continuity import FlowFixture, ROOT, basket, dv, ss


class PurchaseStageTests(FlowFixture):
    def run_entry(self, *args, success=True):
        result = subprocess.run([sys.executable, "-B",
            str(ROOT / "skills/mcd-hidden-explorer/scripts/discover.py"), *args,
            "--session", str(self.session), "--database", str(self.db)],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0 if success else 2, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_select_is_a_favourite_not_a_purchase_request(self):
        result = self.run_entry("select", "U06")
        self.assertEqual(result["phase"], "exploring")
        self.assertEqual(result["next_step"]["network_calls"], [])
        self.run_entry("coupon-check", "--coupons", "[]", success=False)
        self.assertEqual(ss.load_session(self.session)["phase"], "exploring")

    def test_purchase_prepares_one_basket_and_does_not_order(self):
        self.run_entry("select", "U06", "U18")
        result = self.run_entry("purchase")
        self.assertEqual(result["session"]["phase"], "purchasing")
        self.assertFalse(result["order_created"])
        self.assertEqual(result["next_step"]["order"],
                         ["query-my-coupons", "query-store-coupons", "coupon-check"])
        self.assertEqual(len(ss.load_session(self.session)["rounds"]), 0)
        self.assertTrue(Path(result["plan_state"]["plan_file"]).is_file())

    def test_flavour_and_quantity_survive_without_repeating_plan_path(self):
        self.run_entry("select", "U06")
        # Three processes, no --plan-file: the user changes one thing per turn.
        first = self.run_entry("plan", "--quantities", '{"奥利奥麦旋风":2}')
        self.run_entry("plan", "--choices", '{"U06":{"麦旋风口味二选一":"草莓麦旋风"}}')
        self.run_entry("plan", "--choices", '{"U06":{"派口味二选一":"香芋派"}}')
        result = self.run_entry("purchase")
        self.assertEqual(result["plan_state"]["plan_file"], first["plan_state"]["plan_file"])
        path = Path(result["plan_state"]["plan_file"])
        plan = basket.plan_from_state(basket.load_plan_state(path, for_consumption=True))
        self.assertEqual([(i["nutrition_name"], i["quantity"]) for i in plan["items"]],
                         [("香芋派", 1), ("草莓麦旋风", 2)])
        payload = basket.build_price_items(plan)
        self.assertEqual(payload["items"][1]["quantity"], 2)
        self.assertEqual(payload["items"][1]["roundList"][0]["comboItemList"][0],
                         {"code": "4900", "quantity": 1})
        self.assertEqual(basket.compute_calories(plan["items"],
                         {"香芋派": 10, "草莓麦旋风": 20})["total_kcal"], 50)
        checked = self.run_entry("coupon-check", "--coupons",
            '[{"title":"test only","products":[{"productName":"香芋派"}]}]')
        self.assertEqual(checked["checked_quantities"], [1, 2])
        self.assertEqual(checked["items"][0]["coupons"][0]["status"], "covers_all")
        self.assertEqual(self.run_entry("plan")["items"], plan["items"])

    def test_explicit_first_plan_path_is_remembered(self):
        self.run_entry("select", "U08", "U23")
        self.run_entry("plan", "--plan-file", str(self.plan_file),
                       "--quantities", '{"中薯条":1}')
        result = self.run_entry("purchase")
        self.assertEqual(Path(result["plan_state"]["plan_file"]), self.plan_file.resolve())
        fries = next(i for i in result["items"] if i["nutrition_name"] == "中薯条")
        self.assertEqual(fries["quantity"], 1)

    def test_browse_pauses_purchase_but_keeps_edits(self):
        dv.select(self.db, self.session, ["U06"])
        dv.purchase_entry(self.db, self.session, choices={"U06":{"派口味二选一":"香芋派"}})
        self.run_entry("browse")
        self.run_entry("coupon-check", "--coupons", "[]", success=False)
        result = self.run_entry("purchase")
        self.assertEqual(result["items"][0]["nutrition_name"], "香芋派")

    def test_selection_edit_during_purchase_preserves_surviving_edits(self):
        dv.select(self.db, self.session, ["U06"])
        dv.purchase_entry(self.db, self.session, choices={"U06":{"派口味二选一":"香芋派"}})
        result = self.run_entry("select", "U18")
        self.assertEqual(result["next_step"]["action"], "refresh-plan")
        result = self.run_entry("coupon-check", "--coupons", "[]")
        self.assertIn("派（香芋派）", result["checked_items"])
        self.assertIn("麦香鱼", result["checked_items"])

    def test_lost_plan_does_not_restore_defaults(self):
        self.run_entry("select", "U06")
        result = self.run_entry("purchase", "--choices", '{"U06":{"派口味二选一":"香芋派"}}')
        Path(result["plan_state"]["plan_file"]).unlink()
        self.assertIn("丢失", self.run_entry("plan", success=False)["error"])
        self.run_entry("coupon-check", "--coupons", "[]", success=False)
        ss.clear_selection(self.session)
        self.run_entry("select", "U06")
        self.assertEqual(self.run_entry("purchase")["items"][0]["nutrition_name"], "菠萝派")

    def test_reset_does_not_revive_previous_plan_even_in_same_second(self):
        self.run_entry("select", "U06")
        self.run_entry("plan", "--choices", '{"U06":{"派口味二选一":"香芋派"}}')
        ss.reset_session(self.session)
        self.run_entry("select", "U06")
        self.assertEqual(self.run_entry("purchase")["items"][0]["nutrition_name"], "菠萝派")

    def test_cannot_mix_another_sessions_plan(self):
        self.run_entry("select", "U06")
        result = self.run_entry("plan", "--choices", '{"U06":{"派口味二选一":"香芋派"}}')
        self.session = self.root / "other-session.json"
        ss.init_session(self.session)
        self.run_entry("select", "U06")
        self.run_entry("purchase", "--plan-file", result["plan_state"]["plan_file"], success=False)

    def test_consumers_reject_plan_after_selection_changes(self):
        self.run_entry("select", "U06")
        result = self.run_entry("plan")
        self.run_entry("select", "U18")
        with self.assertRaisesRegex(ValueError, "过期"):
            basket.load_plan_state(result["plan_state"]["plan_file"], for_consumption=True)

    def test_empty_purchase_does_not_change_phase(self):
        self.run_entry("purchase", success=False)
        self.assertEqual(ss.load_session(self.session)["phase"], "exploring")
