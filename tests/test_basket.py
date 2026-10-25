import importlib.util
import unittest
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "skills/mcd-hidden-explorer/scripts/basket.py"
spec = importlib.util.spec_from_file_location("basket", PATH)
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)

TABLE = {
    b.normalize_name("麦辣鸡腿汉堡"): 485,
    b.normalize_name("双层吉士汉堡"): 429,
    b.normalize_name("麦乐鸡5块"): 213,
    b.normalize_name("中薯条"): 289,
    b.normalize_name("可乐中杯"): 147,
    b.normalize_name("麦辣鸡翅-2块"): 224,
}


class MergeTests(unittest.TestCase):
    def test_shared_product_counted_once(self):
        methods = [
            {"id": "U05", "required_products": [{"name": "麦乐鸡5块", "quantity": None}]},
            {"id": "U14", "required_products": [{"name": "麦乐鸡5块", "quantity": None},
                                                {"name": "中薯条", "quantity": None}]},
        ]
        result = b.merge_requirements(methods)
        names = [item["name"] for item in result["items"]]
        self.assertEqual(names.count("麦乐鸡5块"), 1)
        shared = [item for item in result["items"] if item["name"] == "麦乐鸡5块"][0]
        self.assertTrue(shared["shared"])
        self.assertEqual(sorted(shared["sources"]), ["U05", "U14"])

    def test_unknown_quantity_is_a_suggestion(self):
        result = b.merge_requirements([{"id": "U05", "required_products": [{"name": "双层吉士汉堡"}]}])
        item = result["items"][0]
        self.assertEqual(item["quantity"], 1)
        self.assertTrue(item["needs_confirmation"])
        self.assertIn("待确认", item["note"])

    def test_known_quantity_kept(self):
        result = b.merge_requirements([{"id": "X", "required_products": [{"name": "中薯条", "quantity": 2}]}])
        item = result["items"][0]
        self.assertEqual(item["quantity"], 2)
        self.assertFalse(item["needs_confirmation"])


class CalorieTests(unittest.TestCase):
    def test_complete_sum(self):
        items = [{"name": "麦辣鸡腿汉堡", "quantity": 1},
                 {"name": "双层吉士汉堡", "quantity": 1},
                 {"name": "麦乐鸡5块", "quantity": 1}]
        result = b.compute_calories(items, TABLE)
        self.assertEqual(result["total_kcal"], 1127)
        self.assertTrue(result["complete"])
        self.assertEqual(result["label"], "整份热量")

    def test_set_uses_components(self):
        items = [{"name": "麦辣鸡腿堡3件套", "quantity": 1,
                  "components": [{"name": "麦辣鸡腿汉堡"}, {"name": "中薯条"}, {"name": "可乐中杯"}]}]
        result = b.compute_calories(items, TABLE)
        self.assertEqual(result["total_kcal"], 921)
        self.assertTrue(result["complete"])

    def test_missing_is_partial_not_zero(self):
        items = [{"name": "双层吉士汉堡", "quantity": 1},
                 {"name": "不存在的商品", "quantity": 1}]
        result = b.compute_calories(items, TABLE)
        self.assertIsNone(result["total_kcal"])
        self.assertEqual(result["known_kcal"], 429)
        self.assertEqual(result["label"], "已知部分热量")
        self.assertEqual(len(result["missing"]), 1)

    def test_quantity_multiplies_once(self):
        items = [{"name": "麦乐鸡5块", "quantity": 2}]
        result = b.compute_calories(items, TABLE)
        self.assertEqual(result["total_kcal"], 426)

    def test_name_normalisation(self):
        self.assertEqual(b.nutrition_lookup(TABLE, "麦辣鸡翅2块"), 224)
        self.assertEqual(b.nutrition_lookup(TABLE, " 麦乐鸡5块 "), 213)

    def test_set_with_missing_component_stays_partial(self):
        items = [{"name": "某套餐", "quantity": 1,
                  "components": [{"name": "中薯条"}, {"name": "未收录饮料"}]}]
        result = b.compute_calories(items, TABLE)
        self.assertIsNone(result["total_kcal"])
        self.assertEqual(result["known_kcal"], 289)
        self.assertTrue(result["breakdown"][0]["partial"])


class CompareTests(unittest.TestCase):
    def test_order_and_delta(self):
        result = b.compare_options([
            {"label": "用券", "price_cents": 5990},
            {"label": "单点", "price_cents": 5950},
        ])
        self.assertEqual(result["options"][0]["label"], "单点")
        self.assertEqual(result["options"][0]["delta_cents"], 0)
        self.assertEqual(result["options"][1]["delta_cents"], 40)
        self.assertIn("不代表", result["notice"])

    def test_missing_price_rejected(self):
        with self.assertRaises(ValueError):
            b.compare_options([{"label": "未核价"}])


class ConfirmationTests(unittest.TestCase):
    def test_ready_when_complete(self):
        result = b.build_confirmation({"store_code": "1450713", "take_way": "堂食",
                                       "items": [{"productCode": "nuggets", "name": "麦乐鸡5块", "quantity": 1}],
                                       "order_type": 1, "be_type": 1,
                                       "price_request": {"storeCode": "1450713", "orderType": 1, "beType": 1,
                                           "items": [{"productCode": "nuggets", "quantity": 1}]},
                                       "price_cents": 1400,
                                       "price_checked_at": "2026-10-25 12:30",
                                       "calories": {"label": "整份热量", "total_kcal": 213}})
        self.assertTrue(result["ready_for_confirmation"])
        self.assertFalse(result["ready_for_order"])
        self.assertFalse(result["order_created"])
        self.assertEqual(result["calorie_label"], "整份热量")
        self.assertEqual(result["calorie_total"], 213)

    def test_blocked_without_price_check_time(self):
        result = b.build_confirmation({"store_code": "1450713", "take_way": "堂食",
                                       "items": [{"productCode": "nuggets", "name": "麦乐鸡5块", "quantity": 1}],
                                       "order_type": 1, "be_type": 1,
                                       "price_request": {"storeCode": "1450713", "orderType": 1, "beType": 1,
                                           "items": [{"productCode": "nuggets", "quantity": 1}]},
                                       "price_cents": 1400,
                                       "calories": {"label": "整份热量", "total_kcal": 213}})
        self.assertFalse(result["ready_for_order"])
        self.assertTrue(any("核实时间" in item for item in result["blockers"]))

    def test_blocked_without_price(self):
        result = b.build_confirmation({"store_code": "1450713", "take_way": "堂食",
                                       "items": [{"name": "麦乐鸡5块", "quantity": 1}]})
        self.assertFalse(result["ready_for_order"])
        self.assertTrue(any("核价" in item for item in result["blockers"]))


if __name__ == "__main__":
    unittest.main()
