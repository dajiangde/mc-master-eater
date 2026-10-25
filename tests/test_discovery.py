import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "skills/mcd-hidden-explorer/scripts/numbered_catalog.py"
spec = importlib.util.spec_from_file_location("numbered_catalog_discovery", SCRIPT)
nc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nc)


def make_row(ident, title, category, products):
    return {"id": ident, "title": title, "card_title": title, "category": category,
            "products": [{"name": name, "code": code, "time": "12:00", "evidence": "e.json"}
                         for name, code in products],
            "image_ids": [], "source_ids": [], "tested_by_project": False}


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source.json"
        self.policy = self.root / "roles.json"
        self.db = self.root / "numbers.sqlite"
        self.data = {"entries": [
            make_row("U01", "脆薯饼夹麦旋风", "甜咸组合", [("脆薯饼", "4825"), ("奥利奥麦旋风", "1217")]),
            make_row("U08", "薯条摇摇乐", "小食混拌", [("中薯条", "4810"), ("麦乐鸡5块", "1401")]),
            make_row("U10", "麦满分夹脆薯饼", "早餐", [("吉士蛋麦满分", "5301"), ("脆薯饼", "4825")]),
            make_row("U11", "玉米冰淇淋", "甜品", [("小杯玉米杯", "4437"), ("奥利奥麦旋风", "1217")]),
            make_row("U17", "麦香鱼加玉米杯", "汉堡重组", [("麦香鱼", "1501"), ("小杯玉米杯", "4437")]),
            make_row("U23", "鸡翅薯条夹心", "小食组合", [("麦辣鸡翅2块", "1601"), ("中薯条", "4810")]),
        ], "images": [], "sources": []}
        self.source.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf8")
        self.policy.write_text(json.dumps({"recipes": {}}), encoding="utf8")
        nc.sync_database(self.source, self.db, self.policy)

    # ── query normalisation ──

    def test_normalize_strips_intent_words(self):
        self.assertEqual(nc.normalize_query("想看薯条相关的"), "薯条")
        self.assertEqual(nc.normalize_query("我想吃麦香鱼"), "麦香鱼")
        self.assertEqual(nc.normalize_query("有没有双吉"), "双吉")
        self.assertEqual(nc.normalize_query("薯条"), "薯条")

    def test_normalize_keeps_product_characters(self):
        for name in ("麦香鱼", "玉米", "鸡块", "菠萝派", "雪碧"):
            self.assertEqual(nc.normalize_query(name), name)

    def test_empty_query_rejected(self):
        with self.assertRaises(ValueError):
            nc.normalize_query("   ")

    # ── by product ──

    def test_fries_excludes_hashbrown(self):
        result = nc.find_by_product(self.db, "薯条", limit=10)
        ids = [m["id"] for m in result["methods"]]
        self.assertIn("U08", ids)
        self.assertIn("U23", ids)
        self.assertNotIn("U01", ids)
        self.assertNotIn("U10", ids)

    def test_hashbrown_excludes_fries(self):
        result = nc.find_by_product(self.db, "薯饼", limit=10)
        ids = [m["id"] for m in result["methods"]]
        self.assertEqual(set(ids), {"U01", "U10"})

    def test_common_alias_matches(self):
        self.assertEqual([m["id"] for m in nc.find_by_product(self.db, "中薯", limit=5)["methods"]],
                         [m["id"] for m in nc.find_by_product(self.db, "薯条", limit=5)["methods"]])
        self.assertEqual(nc.find_by_product(self.db, "鱼堡", limit=5)["methods"][0]["id"], "U17")
        self.assertEqual(nc.find_by_product(self.db, "鸡块", limit=5)["methods"][0]["id"], "U08")

    def test_limit_is_capped_by_caller(self):
        result = nc.find_by_product(self.db, "薯条", limit=1)
        self.assertEqual(result["count"], 1)
        self.assertLessEqual(len(result["methods"]), 1)

    def test_no_match_returns_suggestions_not_results(self):
        result = nc.find_by_product(self.db, "巨无霸", limit=3)
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["methods"], [])
        self.assertIn("no_match_reason", result)
        self.assertTrue(result["suggestions"]["categories"])
        self.assertEqual(result["suggestions"]["families"], [])

    def test_suggestions_use_shared_characters(self):
        result = nc.find_by_product(self.db, "麦香堡", limit=3)
        # 麦香堡 matches no product exactly but shares 麦香 with 麦香鱼.
        self.assertEqual(result["count"], 0)
        self.assertIn("麦香鱼", result["suggestions"]["families"])

    def test_result_shape_has_number_name_products(self):
        result = nc.find_by_product(self.db, "薯条", limit=1)
        method = result["methods"][0]
        for field in ("id", "number", "display_number", "card_title",
                      "required_products", "matched_products"):
            self.assertIn(field, method)

    # ── random ──

    def test_random_limit_three(self):
        result = nc.random_batch(self.db, limit=3, seed=1)
        self.assertEqual(result["count"], 3)
        self.assertEqual(len({m["id"] for m in result["methods"]}), 3)

    def test_random_prefers_unseen(self):
        all_ids = [m["id"] for m in nc.list_numbers(self.db)]
        seen = all_ids[:3]
        result = nc.random_batch(self.db, limit=3, seen=seen, seed=2)
        picked = {m["id"] for m in result["methods"]}
        self.assertTrue(picked.isdisjoint(seen), "should return unseen methods while any remain")

    def test_random_falls_back_when_everything_seen(self):
        all_ids = [m["id"] for m in nc.list_numbers(self.db)]
        result = nc.random_batch(self.db, limit=3, seen=all_ids, seed=3)
        self.assertEqual(result["count"], 3)

    def test_random_varies_categories(self):
        result = nc.random_batch(self.db, limit=3, seed=5)
        categories = [m["category"] for m in result["methods"]]
        self.assertGreater(len(set(categories)), 1, "batch should not be all one category")

    def test_random_batches_differ(self):
        first = [m["id"] for m in nc.random_batch(self.db, limit=2, seed=11)["methods"]]
        second = [m["id"] for m in nc.random_batch(self.db, limit=2,
                                                   seen=first, seed=12)["methods"]]
        self.assertTrue(set(first).isdisjoint(second))

    # ── coupon ──

    def test_coupon_exact_match(self):
        result = nc.coupon_link(self.db, {"title": "薯条优惠",
                                          "products": [{"productName": "中薯条", "productCode": "4810"}]},
                                limit=5)
        self.assertEqual(result["methods"][0]["match"]["type"], "exact")
        self.assertEqual(result["methods"][0]["match"]["score"], 100)

    def test_coupon_possible_match(self):
        result = nc.coupon_link(self.db, {"title": "薯条买一送一"}, limit=5)
        top = result["supplementary"][0]
        self.assertEqual(top["match"]["type"], "possible")
        self.assertEqual(top["match"]["tier"], "supplementary")
        self.assertLess(top["match"]["score"], 100)

    def test_coupon_usability_never_confirmed(self):
        result = nc.coupon_link(self.db, {"title": "薯条优惠",
                                          "products": [{"productName": "中薯条"}]}, limit=5)
        for method in result["methods"] + result["supplementary"]:
            self.assertEqual(method["match"]["usability"], "not_yet_confirmed")

    def test_coupon_no_match_is_empty(self):
        result = nc.coupon_link(self.db, {"title": "完全无关活动",
                                          "products": [{"productName": "外星汉堡"}]}, limit=5)
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["methods"], [])
        self.assertEqual(result["supplementary"], [])
        self.assertFalse(result["has_direct_match"])

    def test_coupon_respects_limit(self):
        result = nc.coupon_link(self.db, {"title": "薯条买一送一"}, limit=2)
        self.assertLessEqual(result["count"], 2)

    def test_coupon_title_names_family_without_sku(self):
        result = nc.coupon_link(self.db, {"title": "薯条买一送一"}, limit=5)
        self.assertGreater(result["count"], 0)
        pool = result["methods"] + result["supplementary"]
        self.assertTrue(any("薯条" in "".join(m["match"]["reasons"]) for m in pool))

    def test_category_term_matches_several_products(self):
        result = nc.find_by_product(self.db, "炸鸡", limit=5)
        self.assertGreater(result["count"], 0)
        self.assertEqual(result["matched_families"], ["炸鸡类"])
        ids = {m["id"] for m in result["methods"]}
        self.assertTrue(ids & {"U17"} or ids, "category match should return methods")

    def test_coupon_category_wording(self):
        result = nc.coupon_link(self.db, {"title": "19.9元王牌炸鸡任选2"}, limit=5)
        self.assertGreater(result["count"], 0)
        pool = result["methods"] + result["supplementary"]
        self.assertTrue(all(m["match"]["type"] == "possible" for m in pool))
        self.assertTrue(any("炸鸡" in "".join(m["match"]["reasons"]) for m in pool))

    # ── contract: primary vs supplementary stay disjoint ──

    def test_primary_and_supplementary_are_disjoint(self):
        result = nc.coupon_link(self.db, {"title": "薯条买一送一",
                                          "products": [{"productName": "中薯条"}]}, limit=5)
        primary_ids = [m["id"] for m in result["methods"]]
        supplementary_ids = [m["id"] for m in result["supplementary"]]
        self.assertFalse(set(primary_ids) & set(supplementary_ids),
                         "an entry must not appear in both lists")

    def test_counts_add_up(self):
        result = nc.coupon_link(self.db, {"title": "薯条买一送一"}, limit=3)
        self.assertEqual(result["count"],
                         result["primary_count"] + result["supplementary_count"])
        self.assertEqual(result["count"],
                         len(result["methods"]) + len(result["supplementary"]))

    def test_has_direct_match_reflects_primary(self):
        direct = nc.coupon_link(self.db, {"title": "优惠",
                                          "products": [{"productName": "中薯条"}]}, limit=3)
        self.assertTrue(direct["has_direct_match"])
        self.assertTrue(direct["methods"])
        self.assertTrue(all(m["match"]["tier"] == "primary" for m in direct["methods"]))

        indirect = nc.coupon_link(self.db, {"title": "薯条买一送一"}, limit=3)
        self.assertFalse(indirect["has_direct_match"])
        self.assertEqual(indirect["methods"], [])
        self.assertTrue(indirect["supplementary"])


if __name__ == "__main__":
    unittest.main()
