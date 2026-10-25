"""Purchase-plan, flavour-choice and summary-normalisation checks."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/mcd-hidden-explorer/scripts"))

import basket  # noqa: E402
import explore  # noqa: E402


def method(mid, required=(), choices=()):
    return {
        "id": mid,
        "required_products": [{"name": name, "reference_menu": menu} for name, menu in required],
        "product_choices": list(choices),
    }


def group(name, parent, parent_name, options):
    return {
        "name": name,
        "default_name": next(o[0] for o in options if o[2]),
        "default_code": next(o[1] for o in options if o[2]),
        "options": [{"name": o[0], "is_default_choice": o[2],
                     "reference_menu": {"code": o[1], "parent_code": parent, "parent_name": parent_name}}
                    for o in options],
    }


class PurchasePlanTests(unittest.TestCase):
    def setUp(self):
        self.pie = ("菠萝派", {"code": "4105", "parent_code": "9900008752", "parent_name": "派"})
        self.u18 = method("U18", required=[("麦香鱼", {"code": "1600"}), self.pie])
        self.u06 = method("U06", choices=[
            group("派口味二选一", "9900008752", "派",
                  [("菠萝派", "4105", True), ("香芋派", "4106", False)]),
            group("麦旋风口味二选一", "9900008754", "经典麦旋风",
                  [("奥利奥麦旋风", "1217", True), ("草莓麦旋风", "4900", False)]),
        ])

    def test_default_plan_uses_image_combination(self):
        plan = basket.build_purchase_plan([self.u06])
        self.assertEqual([i["display_name"] for i in plan["items"]],
                         ["派（菠萝派）", "经典麦旋风（奥利奥麦旋风）"])
        self.assertTrue(all(q["is_default"] for q in plan["questions"]))

    def test_shared_product_is_one_line_with_added_quantity(self):
        plan = basket.build_purchase_plan([self.u18, self.u06])
        pie = next(i for i in plan["items"] if i["option_code"] == "4105")
        self.assertEqual(pie["quantity"], 2)
        self.assertTrue(pie["shared"])
        self.assertEqual(pie["methods"], ["U18", "U06"])
        self.assertEqual(len(plan["items"]), 3)

    def test_override_switches_option_and_keeps_parent_code(self):
        plan = basket.build_purchase_plan([self.u06], {"派口味二选一": "香芋派"})
        pie = next(i for i in plan["items"] if i["group"] == "派口味二选一")
        self.assertEqual(pie["option_code"], "4106")
        self.assertEqual(pie["price_code"], "9900008752")
        self.assertFalse(next(q for q in plan["questions"] if q["group"] == "派口味二选一")["is_default"])

    def test_unknown_flavour_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "香芋派"):
            basket.build_purchase_plan([self.u06], {"派口味二选一": "苹果派"})

    def test_calories_mark_missing_rows_as_partial(self):
        table = basket.load_nutrition.__globals__["nutrition_lookup"]
        items = [{"display_name": "麦香鱼", "nutrition_name": "麦香鱼", "quantity": 1},
                 {"display_name": "神秘堡", "nutrition_name": "神秘堡", "quantity": 1}]
        result = basket.compute_calories(items, {"麦香鱼": 325})
        self.assertFalse(result["complete"])
        self.assertEqual(result["label"], "已知部分热量")
        self.assertEqual(result["known_kcal"], 325)
        self.assertIsNone(result["total_kcal"])
        self.assertTrue(table)  # helper stays importable


class PriceItemsTests(unittest.TestCase):
    """The calculate-price payload must never turn an option into a product code."""

    def setUp(self):
        pie = ("菠萝派", {"code": "4105", "parent_code": "9900008752", "parent_name": "派"})
        self.u18 = method("U18", required=[("麦香鱼", {"code": "1600"}), pie])
        self.u06 = method("U06", choices=[
            group("派口味二选一", "9900008752", "派",
                  [("菠萝派", "4105", True), ("香芋派", "4106", False)]),
        ])

    def test_plain_product_is_sent_as_is(self):
        payload = basket.build_price_items(basket.build_purchase_plan([self.u18]))
        fish = next(i for i in payload["items"] if i["productCode"] == "1600")
        self.assertEqual(fish, {"productCode": "1600", "quantity": 1})

    def test_option_uses_parent_code_and_round_list(self):
        payload = basket.build_price_items(basket.build_purchase_plan([self.u18]))
        pie = next(i for i in payload["items"] if i["productCode"] == "9900008752")
        self.assertEqual(pie["roundList"][0]["comboItemList"][0]["code"], "4105")
        self.assertNotIn("4105", [i["productCode"] for i in payload["items"]])

    def test_combo_quantity_stays_per_unit_when_shared(self):
        """Two methods needing 派 must not send comboItemList.quantity = 2 (60006)."""
        payload = basket.build_price_items(basket.build_purchase_plan([self.u18, self.u06]))
        pie = next(i for i in payload["items"] if i["productCode"] == "9900008752")
        self.assertEqual(pie["quantity"], 2)
        self.assertEqual(pie["roundList"][0]["comboItemList"][0]["quantity"], 1)

    def test_missing_code_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "缺少商品编码"):
            basket.build_price_items([{"display_name": "无码商品", "quantity": 1}])


def bound_check(summary):
    import checkout_contract as cc
    prepared = cc.prepare(summary)
    prepared.setdefault("be_type", 1)
    prepared["price_request"] = {"storeCode": prepared["store_code"],
        "orderType": prepared["order_type"], "beType": prepared["be_type"],
        "items": [cc.item_config(i) for i in prepared["items"]]}
    final = basket.build_confirmation(prepared)
    request = {**final["price_request"], "takeWayCode": final["take_way_code"]}
    return final, request


class SummaryNormalisationTests(unittest.TestCase):
    def test_camel_case_summary_passes_checks(self):
        summary = {"storeCode": "1410102", "orderType": 1, "takeWayCode": "take-in-store",
                   "productList": [{"productCode": "1600", "quantity": 1}],
                   "priceCheckedAt": "2026-10-25 12:01", "price": 3100}
        final, request = bound_check(summary)
        self.assertEqual(explore.order_confirmation_blockers(final, confirmed=True,
            confirmation_fingerprint=final["confirmation_fingerprint"], order_request=request), [])

    def test_snake_case_summary_still_passes(self):
        summary = {"store_code": "1410102", "order_type": 1, "take_way_code": "T1",
                   "items": [{"product_code": "1600", "quantity": 1}],
                   "price_checked_at": "2026-10-25 12:01", "total_cents": 3100}
        final, request = bound_check(summary)
        self.assertEqual(explore.order_confirmation_blockers(final, confirmed=True,
            confirmation_fingerprint=final["confirmation_fingerprint"], order_request=request), [])

    def test_inline_json_and_file_are_both_accepted(self):
        payload = {"store_code": "1410102", "order_type": 1, "take_way_code": "T1",
                   "items": [{"product_code": "1600", "quantity": 1}],
                   "price_checked_at": "2026-10-25 12:01", "total_cents": 3100}
        self.assertEqual(explore.load_json_argument(json.dumps(payload)), payload)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "summary.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(explore.load_json_argument(str(path)), payload)

    def test_missing_calories_is_a_warning_not_a_blocker(self):
        summary = {"store_code": "1410102", "order_type": 1, "take_way_code": "T1",
                   "items": [{"product_code": "1600", "quantity": 1}],
                   "price_checked_at": "2026-10-25 12:01", "total_cents": 3100}
        final, request = bound_check(summary)
        self.assertEqual(explore.order_confirmation_blockers(final, confirmed=True,
            confirmation_fingerprint=final["confirmation_fingerprint"], order_request=request), [])
        self.assertTrue(explore.order_confirmation_warnings(summary))


if __name__ == "__main__":
    unittest.main()
