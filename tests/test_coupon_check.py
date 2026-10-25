#!/usr/bin/env python3
"""选号确认后的固定核券步骤：券是否覆盖所选吃法的餐品。

判断是机械的，测试也就按机械的边界写：编码一致 > 名称一致 > 同家族（不算覆盖）
> 不覆盖。任何一条都不等于"券可用"，可用性只由 calculate-price 决定。
"""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "mcd-hidden-explorer" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import numbered_catalog as nc  # noqa: E402
import coupon_check as cc  # noqa: E402

NOW = cc._parse_time("2026-10-25 12:49")


def _row(ident, title, products):
    normalized = []
    for item in products:
        if isinstance(item, dict):
            normalized.append({"time": "12:00", "evidence": "historical.json", **item})
        else:
            code, name = item
            normalized.append({"name": name, "code": code,
                               "time": "12:00", "evidence": "historical.json"})
    return {
        "id": ident, "title": title, "products": normalized,
        "image_ids": [], "source_ids": [], "tested_by_project": False,
    }


class CouponCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source.json"
        self.policy = self.root / "roles.json"
        self.db = self.root / "numbers.sqlite"
        data = {"entries": [
            _row("U01", "玉米杯拌薯条", [("4437", "玉米杯"), ("5001", "中薯条")]),
            _row("U02", "鸡翅薯条夹心", [("7001", "麦辣鸡翅2块"), ("5001", "中薯条")]),
            _row("U03", "双吉夹麦旋风", [("8001", "双层吉士汉堡"),
                                        {"name": "奥利奥麦旋风", "code": "1217",
                                         "parent_code": "9900008754"}]),
        ], "images": [], "sources": []}
        self.source.write_text(json.dumps(data, ensure_ascii=False), encoding="utf8")
        self.policy.write_text('{"recipes":{}}', encoding="utf8")
        nc.sync_database(self.source, self.db, self.policy)

    def check(self, ids, coupons, now=NOW):
        return cc.check_selection(self.db, ids, coupons, now=now)

    def one(self, ids, coupons):
        return self.check(ids, coupons)["methods"][0]

    # --- 覆盖判定 -------------------------------------------------------
    def test_product_code_match_counts_as_covered(self):
        method = self.one(["U01"], [{"title": "玉米杯特价",
                                     "products": [{"productCode": "4437",
                                                   "productName": "小杯玉米杯"}]}])
        result = method["coupons"][0]
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["match_level"], "code")
        self.assertIn("玉米杯", result["covered"])
        self.assertEqual(result["missing"], ["中薯条"])

    def test_parent_code_match_counts_as_covered(self):
        method = self.one(["U03"], [{"title": "麦旋风券",
                                     "products": [{"productCode": "9900008754",
                                                   "productName": "经典麦旋风"}]}])
        # 1217 是选项编码，券给的是父商品编码，仍应判为编码命中
        self.assertIn("奥利奥麦旋风", method["coupons"][0]["covered"])

    def test_name_match_counts_as_covered(self):
        method = self.one(["U01"], [{"title": "薯条券", "products": [{"productName": "中薯条"}]}])
        self.assertIn("中薯条", method["coupons"][0]["covered"])
        self.assertEqual(method["coupons"][0]["match_level"], "name")

    def test_family_match_is_not_coverage(self):
        method = self.one(["U02"], [{"title": "麦辣鸡翅买一送一",
                                     "products": [{"productName": "麦辣鸡翅"}]}])
        result = method["coupons"][0]
        self.assertEqual(result["status"], "family_only")
        self.assertEqual(result["covered"], [])
        self.assertIn("麦辣鸡翅2块", result["family_only"])
        self.assertIn("麦辣鸡翅2块", result["missing"])

    def test_unrelated_coupon_covers_nothing(self):
        method = self.one(["U02"], [{"title": "麦辣鸡腿堡三件套",
                                     "products": [{"productCode": "9900004002",
                                                   "productName": "麦辣鸡腿堡3件套"}]}])
        result = method["coupons"][0]
        self.assertEqual(result["status"], "none")
        self.assertEqual(sorted(result["missing"]), ["中薯条", "麦辣鸡翅2块"])

    def test_covers_all_when_every_product_matched(self):
        method = self.one(["U02"], [{"title": "鸡翅+薯条套餐",
                                     "products": [{"productName": "麦辣鸡翅2块"},
                                                  {"productName": "中薯条"}]}])
        self.assertEqual(method["coupons"][0]["status"], "covers_all")
        self.assertTrue(method["has_covering_coupon"])

    # --- 有效期 ---------------------------------------------------------
    def test_future_coupon_is_not_valid_today(self):
        method = self.one(["U01"], [{"title": "明天生效",
                                     "products": [{"productName": "中薯条"}],
                                     "validFrom": "2026-10-26 10:30",
                                     "validUntil": "2026-10-30 23:59"}])
        result = method["coupons"][0]
        self.assertFalse(result["valid_now"])
        self.assertIn("尚未生效", result["validity_note"])

    def test_expired_coupon_is_not_valid(self):
        method = self.one(["U01"], [{"title": "过期券",
                                     "products": [{"productName": "中薯条"}],
                                     "validUntil": "2026-10-24 23:59"}])
        self.assertFalse(method["coupons"][0]["valid_now"])
        self.assertIn("已过期", method["coupons"][0]["validity_note"])

    def test_missing_validity_is_unknown_not_true(self):
        method = self.one(["U01"], [{"title": "无有效期", "products": [{"productName": "中薯条"}]}])
        self.assertIsNone(method["coupons"][0]["valid_now"])

    def test_weekday_window_respected(self):
        # 2026-10-25 是周日；券只写周一至周五
        method = self.one(["U01"], [{"title": "工作日券",
                                     "products": [{"productName": "中薯条"}],
                                     "weekdays": [1, 2, 3, 4, 5]}])
        self.assertFalse(method["coupons"][0]["valid_now"])

    # --- 排序与输出 -----------------------------------------------------
    def test_best_coupon_is_reported_with_remaining_products(self):
        method = self.one(["U01"], [
            {"title": "无关券", "products": [{"productName": "麦辣鸡腿堡3件套"}]},
            {"title": "薯条券", "products": [{"productName": "中薯条"}]},
        ])
        self.assertEqual(method["best_coupon"], "薯条券")
        self.assertEqual(method["missing_from_best"], ["玉米杯"])

    def test_coupons_sorted_by_coverage_then_level(self):
        method = self.one(["U01"], [
            {"title": "无", "products": [{"productName": "麦辣鸡腿堡3件套"}]},
            {"title": "一项", "products": [{"productName": "中薯条"}]},
            {"title": "两项", "products": [{"productName": "中薯条"}, {"productName": "玉米杯"}]},
        ])
        self.assertEqual([c["title"] for c in method["coupons"]], ["两项", "一项", "无"])

    def test_methods_keep_selection_order(self):
        result = self.check(["U03", "U01"], [{"title": "薯条券",
                                              "products": [{"productName": "中薯条"}]}])
        self.assertEqual([m["id"] for m in result["methods"]], ["U03", "U01"])

    def test_repeat_run_is_identical(self):
        coupons = [{"title": "薯条券", "products": [{"productName": "中薯条"}]}]
        first = self.check(["U01"], coupons)
        second = self.check(["U01"], coupons)
        self.assertEqual(json.dumps(first, ensure_ascii=False, sort_keys=True),
                         json.dumps(second, ensure_ascii=False, sort_keys=True))

    def test_unknown_id_rejected(self):
        with self.assertRaisesRegex(ValueError, "U99"):
            self.check(["U99"], [])

    def test_empty_selection_returns_no_methods(self):
        self.assertEqual(self.check([], [{"title": "x"}])["methods"], [])

    def test_usability_never_confirmed(self):
        method = self.one(["U01"], [{"title": "薯条券", "products": [{"productName": "中薯条"}]}])
        self.assertEqual(method["coupons"][0]["usability"], "not_yet_confirmed")

    def test_wrapped_coupon_payload_accepted(self):
        wrapped = {"coupons": [{"title": "薯条券", "products": [{"productName": "中薯条"}]}]}
        self.assertEqual(self.check(["U01"], wrapped)["coupon_count"], 1)


class CouponCheckCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source.json"
        self.policy = self.root / "roles.json"
        self.db = self.root / "numbers.sqlite"
        self.session = self.root / "session.json"
        data = {"entries": [_row("U01", "玉米杯拌薯条", [("4437", "玉米杯"), ("5001", "中薯条")])],
                "images": [], "sources": []}
        self.source.write_text(json.dumps(data, ensure_ascii=False), encoding="utf8")
        self.policy.write_text('{"recipes":{}}', encoding="utf8")
        nc.sync_database(self.source, self.db, self.policy)
        self.coupons = self.root / "coupons.json"
        self.coupons.write_text(json.dumps([{"title": "薯条券",
                                             "products": [{"productName": "中薯条"}]}],
                                            ensure_ascii=False), encoding="utf8")

    def _run(self, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / "discover.py"), *args],
                              capture_output=True, text=True)

    def _init(self):
        return subprocess.run([sys.executable, str(SCRIPTS / "session_state.py"),
                               "init", "--session", str(self.session)],
                              capture_output=True, text=True)

    def test_check_command_works_with_explicit_ids(self):
        result = self._run("coupon-check", "--database", str(self.db),
                           "--session", str(self.session),
                           "--coupons", self.coupons.read_text(encoding="utf8"),
                           "--ids", "U01", "--now", "2026-10-25 12:49")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["entry"], "coupon_check")
        self.assertEqual(payload["methods"][0]["best_coupon"], "薯条券")
        self.assertIsNone(payload["round_id"])

    def test_check_uses_current_selection_and_leaves_it_alone(self):
        self._init()
        self._run("select", "U01", "--database", str(self.db), "--session", str(self.session))
        self._run("purchase", "--database", str(self.db), "--session", str(self.session))
        result = self._run("coupon-check", "--database", str(self.db),
                           "--session", str(self.session),
                           "--coupons", self.coupons.read_text(encoding="utf8"),
                           "--now", "2026-10-25 12:49")
        payload = json.loads(result.stdout)
        self.assertEqual(payload["session"]["current_selection"], ["U01"])
        self.assertIn("玉米杯", payload["checked_items"])

    def test_select_keeps_exploring_without_coupon_queries(self):
        self._init()
        result = self._run("select", "U01", "--database", str(self.db),
                           "--session", str(self.session))
        payload = json.loads(result.stdout)
        step = payload["next_step"]
        self.assertEqual(step["action"], "continue-exploring")
        self.assertEqual(step["network_calls"], [])
        self.assertTrue(step["requires_purchase_request"])

    def test_bad_coupons_json_exits_two(self):
        result = self._run("coupon-check", "--database", str(self.db),
                           "--session", str(self.session),
                           "--coupons", "{not json", "--ids", "U01")
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
