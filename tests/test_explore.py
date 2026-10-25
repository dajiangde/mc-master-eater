import copy
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / "skills/mcd-hidden-explorer/scripts/explore.py"
spec = importlib.util.spec_from_file_location("explore", PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.row = dict(id="X01", aliases=["T01"], name="TEST ONLY <script>alert(1)</script>",
                        recipe_status="cover_only", source_url="https://example.com/source",
                        observation="<b>synthetic test fixture</b>", ingredients=[], steps=[])
        self.data = dict(schema_version=1, entries=[self.row])

    def test_empty(self):
        self.assertEqual(m.validate(dict(schema_version=1, entries=[]))["entries"], [])
        self.assertIn("0 条", m.render(dict(schema_version=1, entries=[])))

    def test_lookup(self):
        self.assertEqual(m.lookup(m.validate(self.data), " t01 ")["canonical_id"], "X01")

    def test_unknown(self):
        with self.assertRaises(ValueError):
            m.lookup(self.data, "X99")

    def test_escape(self):
        page = m.render(m.validate(self.data))
        self.assertNotIn("<script>alert", page)
        self.assertIn("&lt;script&gt;", page)

    def test_duplicate(self):
        self.data["entries"].append(copy.deepcopy(self.row))
        with self.assertRaises(ValueError):
            m.validate(self.data)

    def test_cover_recipe(self):
        self.row["steps"] = ["invented"]
        with self.assertRaises(ValueError):
            m.validate(self.data)

    def test_negative_quantity(self):
        self.row.update(recipe_status="reported_recipe", ingredients=[dict(name="test", quantity=-1)])
        with self.assertRaises(ValueError):
            m.validate(self.data)

    def test_unknown_quantity(self):
        self.row.update(recipe_status="reported_recipe", ingredients=[dict(name="test", quantity=None)])
        m.validate(self.data)

    def test_unsafe_url(self):
        self.row["source_url"] = "javascript:alert(1)"
        with self.assertRaises(ValueError):
            m.validate(self.data)

    def test_images_rejected(self):
        self.row["assets"] = ["unlicensed.webp"]
        with self.assertRaises(ValueError):
            m.validate(self.data)

    def test_name_and_latest_batch_ordinal(self):
        self.data["entries"].append(dict(id="HM02", name="薯饼夹冰淇淋", recipe_status="reported_recipe",
                                          source_url="https://example.com/second", observation="reported",
                                          ingredients=[dict(name="薯饼", quantity=2)], steps=["夹入"], images=[]))
        clean = m.validate(self.data)
        self.assertEqual(m.lookup(clean, "薯饼夹冰淇淋")["canonical_id"], "HM02")
        batch = {"ids": ["X01", "HM02"]}
        result = m.lookup(clean, "第 2 个", batch)
        self.assertEqual(result["canonical_id"], "HM02")
        self.assertEqual(result["batch_position"], 2)

    def test_ordinal_without_batch_rejected(self):
        with self.assertRaises(ValueError):
            m.lookup(self.data, "第 1 个")

    def test_coupon_recommendation_keeps_partial_matches(self):
        self.row["associated_meals"] = [{"name": "麦辣鸡腿堡"}]
        self.data["entries"].append(dict(id="HM02", name="薯饼吃法", recipe_status="reported_recipe",
                                          source_url="https://example.com/second", observation="reported",
                                          ingredients=[dict(name="脆薯饼", quantity=1)], steps=["组合"],
                                          associated_meals=[{"name": "脆薯饼"}], tags=[]))
        coupons = [
            {"title": "11.9元麦辣鸡腿堡", "eligible_products": [{"productCode": "P1", "name": "麦辣鸡腿堡"}]},
            {"title": "免费脆薯饼"},
        ]
        results = m.recommend_by_coupons(m.validate(self.data), coupons)
        self.assertEqual(results[0]["entry"]["id"], "X01")
        self.assertEqual(results[0]["score"], 70)
        hm02 = [result for result in results if result["entry"]["id"] == "HM02"]
        self.assertEqual(len(hm02), 1)
        self.assertEqual(hm02[0]["score"], 30)

    def test_coupon_product_code_match_ranks_first(self):
        self.row["associated_meals"] = [{"name": "麦辣鸡腿堡", "productCode": "P1"}]
        coupons = [{"title": "优惠", "eligible_products": [{"productCode": "P1", "name": "麦辣鸡腿堡"}]}]
        results = m.recommend_by_coupons(m.validate(self.data), coupons)
        self.assertEqual(results[0]["score"], 100)
        self.assertIn("商品规则命中", results[0]["reasons"])


class ResearchModeTests(unittest.TestCase):
    """Tests for the local research adapter (schema_version 3, read-only)."""

    def setUp(self):
        self.research_row = dict(
            record_id="R12",
            dish_name="麦辣鸡腿汉堡、牛肉饼和麦乐鸡叠堡",
            dish_name_as_reported="鸡腿堡、牛肉饼和鸡块叠堡",
            evidence_status="reported_recipe",
            needed_products_as_reported=["麦辣鸡腿堡", "双层吉士汉堡中的牛肉与芝士", "麦乐鸡"],
            method_as_reported="将不同肉类夹层重组为叠堡。",
            quantity_evidence="原文未给出完整用量",
            image_ids=["S06"],
            recipe_sources=[dict(id="S08", title="汉堡隐藏吃法文章",
                                 url="https://www.sohu.com/a/474756193_120446403",
                                 published_at="2021-06-30", region="中国大陆", author=None)],
            mainland_display_products=["麦辣鸡腿汉堡", "双层吉士汉堡（取牛肉饼和吉士片）", "麦乐鸡（块数待核）"],
            product_name_mappings=[
                dict(source_name="麦辣鸡腿堡", mainland_display_name="麦辣鸡腿汉堡",
                     mainland_canonical_name="麦辣鸡腿汉堡", mainland_candidates=[],
                     mapping_status="official_name_verified", mapping_note="",
                     evidence_ids=["MCP-NAMES-20261024"], store_menu_status="matched",
                     nonseasonal_status="unknown"),
                dict(source_name="麦乐鸡", mainland_display_name="麦乐鸡（块数待核）",
                     mainland_canonical_name=None, mainland_candidates=["麦乐鸡4块", "麦乐鸡5块"],
                     mapping_status="family_verified_variant_unknown", mapping_note="",
                     evidence_ids=["MCP-NAMES-20261024"], store_menu_status="matched_family",
                     nonseasonal_status="unknown"),
            ],
            source_unknowns="照片含多层面包；各原料准确用量未给出，不照图推算。",
            recipe_pending_items=["三类商品的准确份数及夹层重组次序未给；取肉饼需买整份汉堡"],
            product_name_pending_items=["麦乐鸡：目录存在不同块数；不能把历史一盒自动当作当前5块。"],
            blocking_gaps=["非时令属性尚未独立确认"],
            collection_status="主要商品已找到；仍需核配方与非时令",
            eligible_for_actionable_pool=False,
            current_store_verified=True,
            nonseasonal_status="unknown",
            recipe_completeness_status="needs_evidence",
            image_pending_items=[],
        )
        self.research_image = dict(
            image_id="S06", path="images/S06.jpg",
            sha256="89c6648a4ac8bae26720ac0c0c91bd25d6dfd46bcdd29980ace3281a4b3012a2",
            record_id="R12", image_source_url="https://www.sohu.com/a/474756193_120446403",
            image_kind="组合成品图", rights="未核实", creator=None,
            photo_verification_status="待补",
        )
        self.research_data = dict(schema_version=3, entries=[self.research_row],
                                  images=[self.research_image])

    def test_research_validate_rejects_wrong_schema(self):
        with self.assertRaises(ValueError):
            m.research_validate(dict(schema_version=1, entries=[]))

    def test_research_validate_rejects_duplicate_record_id(self):
        data = dict(schema_version=3, entries=[self.research_row, copy.deepcopy(self.research_row)],
                    images=[self.research_image])
        with self.assertRaises(ValueError):
            m.research_validate(data)

    def test_research_lookup_by_product_name(self):
        clean = m.research_validate(self.research_data)
        result = m.research_lookup(clean, "麦辣鸡腿汉堡")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["methods"][0]["id"], "R12")
        self.assertEqual(result["methods"][0]["name"], "麦辣鸡腿汉堡、牛肉饼和麦乐鸡叠堡")

    def test_research_lookup_preserves_image_path(self):
        clean = m.research_validate(self.research_data)
        result = m.research_lookup(clean, "麦辣鸡腿汉堡")
        img = result["methods"][0]["images"][0]
        self.assertEqual(img["id"], "S06")
        self.assertEqual(img["relative_path"], "images/S06.jpg")
        self.assertEqual(img["sha256"], self.research_image["sha256"])
        self.assertEqual(img["rights"], "未核实")

    def test_research_lookup_preserves_source(self):
        clean = m.research_validate(self.research_data)
        result = m.research_lookup(clean, "麦辣鸡腿汉堡")
        src = result["methods"][0]["sources"][0]
        self.assertEqual(src["url"], "https://www.sohu.com/a/474756193_120446403")
        self.assertEqual(src["title"], "汉堡隐藏吃法文章")

    def test_research_lookup_preserves_unresolved_fields(self):
        clean = m.research_validate(self.research_data)
        result = m.research_lookup(clean, "麦辣鸡腿汉堡")
        unresolved = result["methods"][0]["status"]["unresolved"]
        self.assertTrue(any("nonseasonal_status" in str(item) for item in unresolved))
        self.assertTrue(any("recipe_pending" in str(item) or "三类商品" in str(item) for item in unresolved))
        self.assertTrue(any("product_name_pending" in str(item) or "块数" in str(item) for item in unresolved))

    def test_research_lookup_empty_query_rejected(self):
        clean = m.research_validate(self.research_data)
        with self.assertRaises(ValueError):
            m.research_lookup(clean, "  ")

    def test_research_lookup_no_match_returns_empty(self):
        clean = m.research_validate(self.research_data)
        result = m.research_lookup(clean, "不存在的商品名XYZ")
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["methods"], [])

    def test_research_lookup_returns_unified_schema(self):
        """Verify the unified return schema has all required top-level fields."""
        clean = m.research_validate(self.research_data)
        result = m.research_lookup(clean, "麦辣鸡腿汉堡")
        self.assertEqual(result["result_schema_version"], 1)
        self.assertEqual(result["mode"], "local_research")
        method = result["methods"][0]
        for field in ("id", "name", "evidence_status", "images", "required_products",
                       "sources", "recipe", "status", "mode"):
            self.assertIn(field, method)

    def test_research_lookup_required_products_have_no_quantity(self):
        """Required products must always have quantity=None."""
        clean = m.research_validate(self.research_data)
        result = m.research_lookup(clean, "麦辣鸡腿汉堡")
        for product in result["methods"][0]["required_products"]:
            self.assertIsNone(product["quantity"])

    def test_coupon_match_possible_by_substring(self):
        """Coupon '麦辣鸡腿堡3件套' should match R12 as 'possible' (not exact)."""
        clean = m.research_validate(self.research_data)
        coupon = dict(
            title="麦辣鸡腿堡三件套",
            couponId="OFFLINE_TEST_COUPON_001",
            products=[dict(productCode="9900004002", productName="麦辣鸡腿堡3件套")],
        )
        result = m.coupon_match_research(clean, coupon)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["methods"][0]["id"], "R12")
        self.assertEqual(result["methods"][0]["match"]["type"], "possible")
        self.assertLess(result["methods"][0]["match"]["score"], 100)

    def test_coupon_match_usability_not_yet_confirmed(self):
        """Coupon usability must always be 'not_yet_confirmed'."""
        clean = m.research_validate(self.research_data)
        coupon = dict(
            title="麦辣鸡腿堡三件套",
            products=[dict(productCode="9900004002", productName="麦辣鸡腿堡3件套")],
        )
        result = m.coupon_match_research(clean, coupon)
        self.assertEqual(result["methods"][0]["match"]["usability"], "not_yet_confirmed")

    def test_coupon_match_exact_by_name(self):
        """Exact match when coupon product name equals a row product name."""
        clean = m.research_validate(self.research_data)
        coupon = dict(
            title="优惠",
            products=[dict(productCode="P1", productName="麦辣鸡腿堡")],
        )
        result = m.coupon_match_research(clean, coupon)
        self.assertEqual(result["methods"][0]["match"]["type"], "exact")
        self.assertEqual(result["methods"][0]["match"]["score"], 100)

    def test_coupon_match_no_match(self):
        """No match when coupon has zero overlap with any record."""
        clean = m.research_validate(self.research_data)
        coupon = dict(
            title="完全不相关的优惠券",
            products=[dict(productCode="ZZZ", productName="不存在商品XYZ")],
        )
        result = m.coupon_match_research(clean, coupon)
        self.assertEqual(result["count"], 0)

    def test_coupon_match_returns_unified_method(self):
        """Coupon match results must include unified method fields."""
        clean = m.research_validate(self.research_data)
        coupon = dict(title="麦辣鸡腿堡", products=[dict(productName="麦辣鸡腿堡")])
        result = m.coupon_match_research(clean, coupon)
        method = result["methods"][0]
        for field in ("id", "name", "images", "required_products", "sources", "status", "match"):
            self.assertIn(field, method)

    def test_public_catalog_not_affected_by_research(self):
        """Research data must not validate against the public catalog schema."""
        with self.assertRaises(ValueError):
            m.validate(self.research_data)

    def test_dedup_report_for_b_batch(self):
        """Dedup report should correctly classify all 8 B-batch entries."""
        batch_entries = [
            dict(id="CNB01", name="香芋派拌草莓麦旋风"),
            dict(id="CNB02", name="玉米与冰淇淋组合"),
            dict(id="CNB03", name="麦辣鸡翅去骨吃法"),
            dict(id="CNB04", name="鱼牛双拼"),
            dict(id="CNB05", name="海陆空组合堡"),
            dict(id="CNB06", name="鸡块双吉"),
            dict(id="CNB07", name="Nico薯条组合"),
            dict(id="CNB08", name="薯饼夹麦旋风原帖复核"),
        ]
        report = m.dedup_report([], batch_entries)
        self.assertEqual(len(report), 8)
        cnb04 = [r for r in report if r["batch_id"] == "CNB04"][0]
        self.assertEqual(cnb04["disposition"], "same_method")
        self.assertEqual(cnb04["canonical_id"], "R28")
        self.assertEqual(cnb04["action"], "merge_source")
        cnb01 = [r for r in report if r["batch_id"] == "CNB01"][0]
        self.assertEqual(cnb01["disposition"], "variant")
        self.assertEqual(cnb01["action"], "keep_independent")
        cnb08 = [r for r in report if r["batch_id"] == "CNB08"][0]
        self.assertEqual(cnb08["action"], "merge_image")
        cnb07 = [r for r in report if r["batch_id"] == "CNB07"][0]
        self.assertEqual(cnb07["disposition"], "lead")


class CheckoutFlowTests(unittest.TestCase):
    """Claim and order gates: both are write actions and need explicit consent."""

    def test_claim_plan_is_batch_and_needs_confirmation(self):
        plan = m.coupon_claim_plan([
            {"title": "免费脆薯饼", "status": "可领取"},
            {"title": "11.9元麦辣鸡腿堡", "status": "已领取"},
        ])
        self.assertEqual(plan["mode"], "auto_bind_all")
        self.assertFalse(plan["selective"])
        self.assertTrue(plan["requires_confirmation"])
        self.assertEqual([item["name"] for item in plan["claimable"]], ["免费脆薯饼"])
        self.assertEqual([item["name"] for item in plan["already_claimed"]], ["11.9元麦辣鸡腿堡"])
        self.assertTrue(any("整批领取" in warning for warning in plan["warnings"]))

    def test_claim_plan_without_claimable_coupons(self):
        plan = m.coupon_claim_plan([{"title": "免费脆薯饼", "status": "已领取"}])
        self.assertEqual(plan["claimable"], [])
        self.assertTrue(any("没有可领取" in warning for warning in plan["warnings"]))

    def test_verify_claim_reports_new_coupons(self):
        report = m.verify_claim([{"title": "免费脆薯饼"}],
                                [{"title": "免费脆薯饼"}, {"title": "19.9元王牌炸鸡任选2"}])
        self.assertEqual(report["newly_claimed"], ["19.9元王牌炸鸡任选2"])
        self.assertEqual(report["count_after"], 2)

    def test_order_check_blocks_without_confirmation(self):
        summary = {"store_code": "1410102", "order_type": 1, "take_way_code": "T1",
                   "items": [{"product_code": "P1", "quantity": 1}],
                   "price_checked_at": "2026-10-25T11:40:00+08:00", "total_cents": 2290}
        blockers = m.order_confirmation_blockers(summary, confirmed=False)
        self.assertTrue(any("明确确认" in b for b in blockers))
        # A flag alone must never authorize an unbound historical summary.
        self.assertTrue(any("price_request" in b for b in
                            m.order_confirmation_blockers(summary, confirmed=True)))

    def test_order_check_blocks_missing_price_and_take_way(self):
        summary = {"store_code": "1410102", "order_type": 1, "items": [{"product_code": "P1", "quantity": 1}]}
        blockers = m.order_confirmation_blockers(summary, confirmed=True)
        self.assertTrue(any("取餐方式" in item for item in blockers))
        self.assertTrue(any("价格核实时间" in item for item in blockers))
        self.assertTrue(any("试算总价" in item for item in blockers))

    def test_order_check_blocks_empty_items(self):
        summary = {"store_code": "1410102", "order_type": 1, "take_way_code": "T1",
                   "items": [], "price_checked_at": "2026-10-25T11:40:00+08:00", "total_cents": 0}
        blockers = m.order_confirmation_blockers(summary, confirmed=True)
        self.assertTrue(any("商品清单" in item for item in blockers))

    def test_order_check_blocks_external_delivery_without_be_code(self):
        summary = {"store_code": "1410102", "order_type": 2,
                   "items": [{"product_code": "P1", "quantity": 1}],
                   "price_checked_at": "2026-10-25T11:40:00+08:00", "total_cents": 2290}
        blockers = m.order_confirmation_blockers(summary, confirmed=True)
        self.assertTrue(any("业务编码" in item for item in blockers))


if __name__ == "__main__":
    unittest.main()
