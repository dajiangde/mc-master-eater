#!/usr/bin/env python3
"""父商品 + 选项编码规则的回归测试。

用真实抓取的 query-meal-detail 结构做夹具，确保把选项编码当商品编码的错误
不会重新出现，并且必选组、可选组、多轮次都能正确生成 roundList。
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "mcd-hidden-explorer" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import meal_config  # noqa: E402

# 真实抓取：2026-10-25 12:15:54 门店 1410102 到店自取
MCFLURRY = {
    "code": "9900008754",
    "name": "经典麦旋风",
    "rounds": [{
        "id": 1,
        "name": "选择麦旋风",
        "quantity": 1,
        "maxQuantity": 1,
        "minQuantity": 1,
        "choices": [
            {"code": "1217", "name": "奥利奥麦旋风", "quantity": 1,
             "maxQuantity": -1, "isDefault": 1, "diffPrice": "+ ¥0",
             "supportModify": False},
            {"code": "4900", "name": "草莓麦旋风", "quantity": 0,
             "maxQuantity": -1, "isDefault": 0, "diffPrice": "+ ¥0",
             "supportModify": False},
        ],
    }],
    "image": "https://menu-img.mcd.cn/pcm/prod/menu/ProductPool/product/MS_9900008754_600.png",
    "supportModify": False,
}

# 真实抓取：同一次查询，无选配轮次
CORN_CUP = {
    "code": "4437",
    "name": "小杯玉米杯",
    "rounds": [],
    "image": "https://menu-img.mcd.cn/pcm/prod/menu/20260101/product/MS_4437_600.png",
    "supportModify": False,
}

# 合成：多轮套餐（1 个必选主件 + 1 个必选配菜 + 1 个可选加购）
COMBO = {
    "code": "9900009999",
    "name": "测试套餐",
    "rounds": [
        {"id": 1, "name": "选主件", "quantity": 1, "minQuantity": 1, "maxQuantity": 1,
         "choices": [
             {"code": "A1", "name": "主件甲", "isDefault": 1, "quantity": 1},
             {"code": "A2", "name": "主件乙", "isDefault": 0, "quantity": 0},
         ]},
        {"id": 2, "name": "选配菜", "quantity": 1, "minQuantity": 1, "maxQuantity": 2,
         "choices": [
             {"code": "B1", "name": "配菜甲", "isDefault": 1, "quantity": 1},
             {"code": "B2", "name": "配菜乙", "isDefault": 0, "quantity": 0},
         ]},
        {"id": 3, "name": "加购", "quantity": 0, "minQuantity": 0, "maxQuantity": 2,
         "choices": [
             {"code": "C1", "name": "加购甲", "isDefault": 0, "quantity": 0},
         ]},
    ],
}


class RoleClassificationTests(unittest.TestCase):
    def test_sellable_product_has_no_rounds(self):
        info = meal_config.describe(CORN_CUP)
        self.assertEqual(info["role"], "sellable")
        self.assertTrue(info["sellable_as_product_code"])
        self.assertEqual(info["rounds"], [])

    def test_parent_product_lists_required_round(self):
        info = meal_config.describe(MCFLURRY)
        self.assertEqual(info["role"], "parent")
        self.assertEqual(len(info["rounds"]), 1)
        round_ = info["rounds"][0]
        self.assertEqual(round_["round"], "1")
        self.assertTrue(round_["required"])
        self.assertEqual([c["code"] for c in round_["choices"]], ["1217", "4900"])

    def test_choice_code_is_recognised_under_its_parent(self):
        found = meal_config.find_choice(MCFLURRY, "1217")
        self.assertIsNotNone(found)
        self.assertEqual(found["parent_code"], "9900008754")
        self.assertEqual(found["parent_name"], "经典麦旋风")
        self.assertEqual(found["round"], "1")
        self.assertEqual(found["isDefault"], 1)

    def test_unknown_code_is_not_a_choice(self):
        self.assertIsNone(meal_config.find_choice(MCFLURRY, "4437"))


class BuildItemTests(unittest.TestCase):
    def test_sellable_item_is_plain(self):
        item = meal_config.build_item(CORN_CUP, 2)
        self.assertEqual(item, {"productCode": "4437", "quantity": 2})

    def test_parent_item_uses_default_choice(self):
        item = meal_config.build_item(MCFLURRY, 1)
        self.assertEqual(item, {
            "productCode": "9900008754",
            "quantity": 1,
            "roundList": [{"round": "1", "comboItemList": [{"code": "1217", "quantity": 1}]}],
        })

    def test_parent_item_honours_explicit_choice(self):
        item = meal_config.build_item(MCFLURRY, 1, ["4900"])
        self.assertEqual(item["roundList"][0]["comboItemList"],
                         [{"code": "4900", "quantity": 1}])

    def test_choice_code_is_never_used_as_product_code(self):
        item = meal_config.build_item(MCFLURRY, 1)
        self.assertEqual(item["productCode"], "9900008754")
        self.assertNotEqual(item["productCode"], "1217")
        self.assertEqual(item["roundList"][0]["comboItemList"][0]["code"], "1217")

    def test_required_round_plus_optional_round_skipped(self):
        item = meal_config.build_item(COMBO, 1)
        rounds = [r["round"] for r in item["roundList"]]
        self.assertEqual(rounds, ["1", "2"])

    def test_optional_round_included_when_selected(self):
        item = meal_config.build_item(COMBO, 1, ["C1"])
        rounds = {r["round"]: r["comboItemList"] for r in item["roundList"]}
        self.assertIn("3", rounds)
        self.assertEqual(rounds["3"], [{"code": "C1", "quantity": 1}])
        # 必选组仍然保留默认值
        self.assertEqual(rounds["1"], [{"code": "A1", "quantity": 1}])

    def test_selection_by_round_mapping(self):
        item = meal_config.build_item(COMBO, 1, {"1": "A2", "2": ["B1", "B2"]})
        rounds = {r["round"]: r["comboItemList"] for r in item["roundList"]}
        self.assertEqual(rounds["1"], [{"code": "A2", "quantity": 1}])
        self.assertEqual([c["code"] for c in rounds["2"]], ["B1", "B2"])

    def test_unknown_choice_rejected(self):
        with self.assertRaises(meal_config.MealConfigError) as ctx:
            meal_config.build_item(MCFLURRY, 1, ["9999"])
        message = str(ctx.exception)
        self.assertIn("9999", message)
        self.assertIn("1217", message)

    def test_required_round_without_default_is_rejected(self):
        broken = json.loads(json.dumps(COMBO))
        broken["rounds"][0]["choices"][0]["isDefault"] = 0
        broken["rounds"][0]["choices"][0]["quantity"] = 0
        with self.assertRaises(meal_config.MealConfigError) as ctx:
            meal_config.build_item(broken, 1)
        self.assertIn("必选组", str(ctx.exception))

    def test_unknown_round_label_rejected(self):
        with self.assertRaises(meal_config.MealConfigError) as ctx:
            meal_config.build_item(COMBO, 1, {"9": "A1"})
        self.assertIn("轮次", str(ctx.exception))

    def test_too_many_choices_rejected(self):
        with self.assertRaises(meal_config.MealConfigError) as ctx:
            meal_config.build_item(COMBO, 1, {"1": ["A1", "A2"]})
        self.assertIn("最多", str(ctx.exception))

    def test_missing_code_rejected(self):
        with self.assertRaises(meal_config.MealConfigError):
            meal_config.build_item({"name": "无编码"}, 1)

    def test_bad_quantity_rejected(self):
        with self.assertRaises(meal_config.MealConfigError):
            meal_config.build_item(CORN_CUP, 0)

    def test_round_falls_back_to_position_without_id(self):
        no_id = json.loads(json.dumps(MCFLURRY))
        del no_id["rounds"][0]["id"]
        item = meal_config.build_item(no_id, 1)
        self.assertEqual(item["roundList"][0]["round"], "1")


class FailureHintTests(unittest.TestCase):
    def test_promo_rule_failure_explains_option_code(self):
        hint = meal_config.explain_failure(600012, "促销规则不支持该商品", MCFLURRY)
        self.assertFalse(hint["success"])
        self.assertIn("选项编码", hint["hint"])
        self.assertEqual(hint["product"]["code"], "9900008754")

    def test_other_codes_have_no_guess(self):
        hint = meal_config.explain_failure(500000, "系统繁忙")
        self.assertNotIn("hint", hint)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.detail_path = Path(self.tmp.name) / "detail.json"
        self.detail_path.write_text(json.dumps(MCFLURRY, ensure_ascii=False), encoding="utf-8")

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "meal_config.py"), *args],
            capture_output=True, text=True,
        )

    def test_item_command_outputs_parent_with_round_list(self):
        result = self._run("item", "--detail", str(self.detail_path))
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["productCode"], "9900008754")
        self.assertEqual(payload["roundList"][0]["comboItemList"][0]["code"], "1217")

    def test_item_command_accepts_choose(self):
        result = self._run("item", "--detail", str(self.detail_path), "--choose", "4900")
        payload = json.loads(result.stdout)
        self.assertEqual(payload["roundList"][0]["comboItemList"][0]["code"], "4900")

    def test_roles_command_reports_choice_lookup(self):
        result = self._run("roles", "--detail", str(self.detail_path), "--code", "1217")
        payload = json.loads(result.stdout)
        self.assertEqual(payload["role"], "parent")
        self.assertEqual(payload["lookup"]["parent_code"], "9900008754")

    def test_bad_choice_exits_two(self):
        result = self._run("item", "--detail", str(self.detail_path), "--choose", "0000")
        self.assertEqual(result.returncode, 2)
        self.assertIn("error", json.loads(result.stdout))


if __name__ == "__main__":
    unittest.main()
