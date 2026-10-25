import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/mcd-hidden-explorer/scripts"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


import sys
sys.path.insert(0, str(SCRIPTS))
nc = _load("nc_for_discover", SCRIPTS / "numbered_catalog.py")
ss = _load("ss_for_discover", SCRIPTS / "session_state.py")
sys.modules.setdefault("numbered_catalog", nc)
sys.modules.setdefault("session_state", ss)
dv = _load("discover", SCRIPTS / "discover.py")


def make_row(ident, title, category, products):
    return {"id": ident, "title": title, "card_title": title, "category": category,
            "products": [{"name": name, "code": code, "time": "12:00", "evidence": "e.json"}
                         for name, code in products],
            "image_ids": [], "source_ids": [], "tested_by_project": False}


class DiscoverEntryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        source, policy = self.root / "source.json", self.root / "roles.json"
        self.db = self.root / "numbers.sqlite"
        data = {"entries": [
            make_row("U01", "脆薯饼夹麦旋风", "甜咸组合", [("脆薯饼", "4825"), ("奥利奥麦旋风", "1217")]),
            make_row("U08", "薯条摇摇乐", "小食混拌", [("中薯条", "4810"), ("麦乐鸡5块", "1401")]),
            make_row("U10", "麦满分夹脆薯饼", "早餐", [("吉士蛋麦满分", "5301"), ("脆薯饼", "4825")]),
            make_row("U21", "玉米杯拌薯条", "小食混拌", [("小杯玉米杯", "4437"), ("中薯条", "4810")]),
            make_row("U17", "麦香鱼加玉米杯", "汉堡重组", [("麦香鱼", "1501"), ("小杯玉米杯", "4437")]),
        ], "images": [], "sources": []}
        source.write_text(json.dumps(data, ensure_ascii=False), encoding="utf8")
        policy.write_text(json.dumps({"recipes": {}}), encoding="utf8")
        nc.sync_database(source, self.db, policy)
        self.session = self.root / "session.json"
        ss.init_session(self.session)

    def test_entries_lists_three_entries_with_examples(self):
        ids = [entry["id"] for entry in dv.ENTRIES]
        self.assertEqual(ids, ["random", "by_product", "by_coupon"])
        for entry in dv.ENTRIES:
            self.assertTrue(entry["examples"], "each entry needs usable example phrases")

    def test_random_records_round_and_order(self):
        result = dv.random_entry(self.db, self.session, limit=3, seed=4)
        self.assertEqual(result["round_id"], "RND001")
        ids = [m["id"] for m in result["methods"]]
        state = ss.load_session(self.session)
        self.assertEqual(state["rounds"][0]["shown_methods"], ids,
                         "display order must be recorded exactly")

    def test_random_second_batch_avoids_seen(self):
        first = [m["id"] for m in dv.random_entry(self.db, self.session, limit=2, seed=1)["methods"]]
        second = [m["id"] for m in dv.random_entry(self.db, self.session, limit=2, seed=2)["methods"]]
        self.assertTrue(set(first).isdisjoint(second))

    def test_random_limit_is_three_at_most(self):
        result = dv.random_entry(self.db, self.session, limit=3, seed=8)
        self.assertLessEqual(len(result["methods"]), 3)

    def test_by_product_records_round_with_query(self):
        result = dv.product_entry(self.db, self.session, "想看薯条相关的", limit=2)
        self.assertEqual(result["round_id"], "RND001")
        state = ss.load_session(self.session)
        self.assertEqual(state["rounds"][0]["query"], "想看薯条相关的")
        self.assertEqual(state["rounds"][0]["source"], "by-product")

    def test_by_product_excludes_hashbrown(self):
        result = dv.product_entry(self.db, self.session, "薯条", limit=5)
        ids = [m["id"] for m in result["methods"]]
        self.assertIn("U08", ids)
        self.assertNotIn("U01", ids)
        self.assertNotIn("U10", ids)

    def test_no_match_does_not_create_round(self):
        result = dv.product_entry(self.db, self.session, "巨无霸", limit=3)
        self.assertEqual(result["count"], 0)
        self.assertIsNone(result["round_id"])
        self.assertEqual(ss.load_session(self.session)["rounds"], [])
        self.assertTrue(result["suggestions"]["categories"])

    def test_selection_survives_entry_switch(self):
        first = [m["id"] for m in dv.random_entry(self.db, self.session, limit=2, seed=3)["methods"]]
        dv.select(self.db, self.session, [first[0]], round_id="RND001")
        dv.product_entry(self.db, self.session, "薯条", limit=2)
        view = dv.selection_view(self.db, self.session)
        self.assertEqual(view["current_selection"], [first[0]])

    def test_select_reports_current_selection(self):
        first = [m["id"] for m in dv.random_entry(self.db, self.session, limit=2, seed=3)["methods"]]
        view = dv.select(self.db, self.session, [first[0], first[1]], round_id="RND001")
        self.assertEqual(view["current_selection"], [first[0], first[1]])
        self.assertIn("当前选中", view["summary"])
        self.assertEqual(len(view["current_selection_labels"]), 2)

    def test_select_rejects_unknown_id(self):
        dv.random_entry(self.db, self.session, limit=2, seed=3)
        with self.assertRaises(ValueError):
            dv.select(self.db, self.session, ["U99"])
        self.assertEqual(dv.selection_view(self.db, self.session)["count"], 0)

    def test_replace_keeps_only_listed(self):
        first = [m["id"] for m in dv.random_entry(self.db, self.session, limit=3, seed=3)["methods"]]
        dv.select(self.db, self.session, first[:2], round_id="RND001")
        view = dv.select(self.db, self.session, [first[0]], replace=True)
        self.assertEqual(view["current_selection"], [first[0]])

    def test_deselect_removes_and_keeps_history(self):
        first = [m["id"] for m in dv.random_entry(self.db, self.session, limit=2, seed=3)["methods"]]
        dv.select(self.db, self.session, first, round_id="RND001")
        ss.deselect_methods(self.session, [first[0]])
        view = dv.selection_view(self.db, self.session)
        self.assertEqual(view["current_selection"], [first[1]])
        self.assertEqual(len(ss.load_session(self.session)["selections"]), 2)

    def test_coupon_entry_records_round(self):
        result = dv.coupon_entry(self.db, self.session,
                                 {"title": "薯条买一送一"}, limit=2)
        self.assertEqual(result["round_id"], "RND001")
        # Title-only coupons are category-level, so they arrive as supplementary inspiration.
        self.assertTrue(result["shown_ids"])
        self.assertTrue(result["methods"] or result["supplementary"])
        self.assertEqual(ss.load_session(self.session)["rounds"][0]["source"], "by-coupon")

    def test_coupon_entry_keeps_selection_on_no_match(self):
        first = [m["id"] for m in dv.random_entry(self.db, self.session, limit=2, seed=3)["methods"]]
        dv.select(self.db, self.session, [first[0]], round_id="RND001")
        result = dv.coupon_entry(self.db, self.session,
                                 {"title": "完全无关", "products": [{"productName": "外星汉堡"}]})
        self.assertEqual(result["count"], 0)
        self.assertIsNone(result["round_id"])
        self.assertEqual(dv.selection_view(self.db, self.session)["current_selection"], [first[0]])


if __name__ == "__main__":
    unittest.main()
