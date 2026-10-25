import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "skills/mcd-hidden-explorer/scripts/session_state.py"
spec = importlib.util.spec_from_file_location("session_state", SCRIPT)
ss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ss)


class SessionStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.session_file = self.root / "session.json"

    # ── init ──

    def test_init_creates_empty_session(self):
        state = ss.init_session(self.session_file)
        self.assertEqual(state["session_schema_version"], 1)
        self.assertEqual(state["rounds"], [])
        self.assertEqual(state["selections"], [])
        self.assertEqual(state["current_selection"], [])
        self.assertTrue(self.session_file.is_file())

    def test_init_refuses_overwrite(self):
        ss.init_session(self.session_file)
        with self.assertRaises(ValueError):
            ss.init_session(self.session_file)

    def test_load_missing_raises(self):
        with self.assertRaises(ValueError):
            ss.load_session(self.session_file)

    # ── recommend ──

    def test_recommend_creates_first_round(self):
        ss.init_session(self.session_file)
        rnd = ss.recommend_round(self.session_file, ["U11", "U12"], query="玉米")
        self.assertEqual(rnd["round_id"], "RND001")
        self.assertEqual(rnd["shown_methods"], ["U11", "U12"])
        self.assertEqual(rnd["query"], "玉米")

    def test_recommend_increments_round_id(self):
        ss.init_session(self.session_file)
        ss.recommend_round(self.session_file, ["U11"])
        ss.recommend_round(self.session_file, ["U12"])
        rnd3 = ss.recommend_round(self.session_file, ["U14"])
        self.assertEqual(rnd3["round_id"], "RND003")

    def test_recommend_rejects_empty(self):
        ss.init_session(self.session_file)
        with self.assertRaises(ValueError):
            ss.recommend_round(self.session_file, [])

    def test_recommend_rejects_duplicates(self):
        ss.init_session(self.session_file)
        with self.assertRaises(ValueError):
            ss.recommend_round(self.session_file, ["U11", "U11"])

    def test_recommend_rejects_invalid_id(self):
        ss.init_session(self.session_file)
        with self.assertRaises(ValueError):
            ss.recommend_round(self.session_file, ["invalid_id"])
        with self.assertRaises(ValueError):
            ss.recommend_round(self.session_file, ["U1"])

    def test_recommend_accepts_various_id_formats(self):
        ss.init_session(self.session_file)
        rnd = ss.recommend_round(self.session_file, ["U11", "R12", "HM01", "CNB03"])
        self.assertEqual(len(rnd["shown_methods"]), 4)

    # ── select ──

    def test_select_adds_to_current_selection(self):
        ss.init_session(self.session_file)
        ss.recommend_round(self.session_file, ["U11", "U12"])
        result = ss.select_methods(self.session_file, ["U11"])
        self.assertEqual(result["current_selection"], ["U11"])
        self.assertEqual(len(result["new_records"]), 1)

    def test_select_multi_in_one_call(self):
        ss.init_session(self.session_file)
        ss.recommend_round(self.session_file, ["U11", "U12", "U14"])
        result = ss.select_methods(self.session_file, ["U11", "U14"])
        self.assertEqual(set(result["current_selection"]), {"U11", "U14"})

    def test_select_from_round_validates_membership(self):
        ss.init_session(self.session_file)
        ss.recommend_round(self.session_file, ["U11", "U12"])
        # U14 was not shown in round RND001.
        with self.assertRaises(ValueError):
            ss.select_methods(self.session_file, ["U14"], round_id="RND001")

    def test_select_from_unknown_round_fails(self):
        ss.init_session(self.session_file)
        ss.recommend_round(self.session_file, ["U11"])
        with self.assertRaises(ValueError):
            ss.select_methods(self.session_file, ["U11"], round_id="RND999")

    def test_select_from_correct_round_succeeds(self):
        ss.init_session(self.session_file)
        rnd1 = ss.recommend_round(self.session_file, ["U11", "U12"])
        result = ss.select_methods(self.session_file, ["U11"], round_id=rnd1["round_id"])
        self.assertEqual(result["new_records"][0]["round_id"], "RND001")

    def test_select_is_idempotent(self):
        ss.init_session(self.session_file)
        ss.recommend_round(self.session_file, ["U11"])
        ss.select_methods(self.session_file, ["U11"])
        result = ss.select_methods(self.session_file, ["U11"])
        self.assertEqual(result["current_selection"], ["U11"])
        self.assertEqual(len(result["new_records"]), 0)

    def test_select_across_rounds_maintains_list(self):
        ss.init_session(self.session_file)
        rnd1 = ss.recommend_round(self.session_file, ["U11", "U12"])
        ss.select_methods(self.session_file, ["U11"], round_id=rnd1["round_id"])
        rnd2 = ss.recommend_round(self.session_file, ["U14", "U15"])
        ss.select_methods(self.session_file, ["U14"], round_id=rnd2["round_id"])
        state = ss.get_status(self.session_file)
        self.assertEqual(set(state["current_selection"]), {"U11", "U14"})
        self.assertEqual(len(state["selections"]), 2)

    def test_select_same_id_from_different_rounds(self):
        """If U11 is shown in both RND001 and RND002, selecting it from
        RND002 when already in current_selection should be idempotent
        (it's already selected), but the selection history preserves both."""
        ss.init_session(self.session_file)
        rnd1 = ss.recommend_round(self.session_file, ["U11", "U12"])
        ss.select_methods(self.session_file, ["U11"], round_id=rnd1["round_id"])
        rnd2 = ss.recommend_round(self.session_file, ["U11", "U14"])
        result = ss.select_methods(self.session_file, ["U11"], round_id=rnd2["round_id"])
        self.assertEqual(result["current_selection"], ["U11"])
        self.assertEqual(len(result["new_records"]), 0)  # Already in current selection.

    # ── deselect ──

    def test_deselect_removes_from_current(self):
        ss.init_session(self.session_file)
        ss.recommend_round(self.session_file, ["U11", "U12"])
        ss.select_methods(self.session_file, ["U11", "U12"])
        result = ss.deselect_methods(self.session_file, ["U11"])
        self.assertEqual(result["current_selection"], ["U12"])
        self.assertEqual(result["removed"], ["U11"])

    def test_deselect_preserves_history(self):
        """Deselect marks deselected_at but keeps the selection record."""
        ss.init_session(self.session_file)
        ss.recommend_round(self.session_file, ["U11"])
        ss.select_methods(self.session_file, ["U11"])
        ss.deselect_methods(self.session_file, ["U11"])
        state = ss.get_status(self.session_file)
        self.assertEqual(state["current_selection"], [])
        self.assertEqual(len(state["selections"]), 1)
        self.assertIn("deselected_at", state["selections"][0])

    def test_deselect_not_in_list_is_idempotent(self):
        ss.init_session(self.session_file)
        ss.recommend_round(self.session_file, ["U11"])
        result = ss.deselect_methods(self.session_file, ["U99"])
        self.assertEqual(result["removed"], [])

    # ── status ──

    def test_status_shows_full_state(self):
        ss.init_session(self.session_file)
        rnd1 = ss.recommend_round(self.session_file, ["U11", "U12"], query="玉米")
        ss.select_methods(self.session_file, ["U11"], round_id=rnd1["round_id"])
        rnd2 = ss.recommend_round(self.session_file, ["U14"], query="薯条")
        state = ss.get_status(self.session_file)
        self.assertEqual(len(state["rounds"]), 2)
        self.assertEqual(state["rounds"][0]["query"], "玉米")
        self.assertEqual(state["rounds"][1]["query"], "薯条")
        self.assertEqual(state["current_selection"], ["U11"])
        self.assertEqual(len(state["selections"]), 1)

    def test_status_rounds_in_order(self):
        ss.init_session(self.session_file)
        ss.recommend_round(self.session_file, ["U11"])
        ss.recommend_round(self.session_file, ["U12"])
        ss.recommend_round(self.session_file, ["U14"])
        state = ss.get_status(self.session_file)
        ids = [r["round_id"] for r in state["rounds"]]
        self.assertEqual(ids, ["RND001", "RND002", "RND003"])

    # ── clear ──

    def test_clear_empties_current_keeps_history(self):
        ss.init_session(self.session_file)
        ss.recommend_round(self.session_file, ["U11", "U12"])
        ss.select_methods(self.session_file, ["U11", "U12"])
        result = ss.clear_selection(self.session_file)
        self.assertEqual(result["current_selection"], [])
        state = ss.get_status(self.session_file)
        self.assertEqual(state["current_selection"], [])
        self.assertEqual(len(state["selections"]), 2)
        self.assertEqual(len(state["rounds"]), 1)

    # ── reset ──

    def test_reset_creates_fresh_state(self):
        ss.init_session(self.session_file)
        ss.recommend_round(self.session_file, ["U11"])
        ss.select_methods(self.session_file, ["U11"])
        ss.reset_session(self.session_file)
        state = ss.get_status(self.session_file)
        self.assertEqual(state["rounds"], [])
        self.assertEqual(state["selections"], [])
        self.assertEqual(state["current_selection"], [])

    # ── persistence ──

    def test_state_persists_across_calls(self):
        ss.init_session(self.session_file)
        ss.recommend_round(self.session_file, ["U11", "U12"])
        ss.select_methods(self.session_file, ["U11"])
        # Re-load to verify it's on disk.
        state = ss.load_session(self.session_file)
        self.assertEqual(len(state["rounds"]), 1)
        self.assertEqual(state["current_selection"], ["U11"])

    def test_updated_at_changes(self):
        import time
        ss.init_session(self.session_file)
        state1 = ss.load_session(self.session_file)
        time.sleep(1.1)  # Ensure the timestamp rolls over.
        ss.recommend_round(self.session_file, ["U11"])
        state2 = ss.load_session(self.session_file)
        self.assertNotEqual(state1["updated_at"], state2["updated_at"])


class CatalogBackedSelectionTests(unittest.TestCase):
    """Selection must consult the numbered catalog before adding anything."""

    def setUp(self):
        import importlib.util as iu
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        script = Path(__file__).resolve().parents[1] / "skills/mcd-hidden-explorer/scripts/numbered_catalog.py"
        spec = iu.spec_from_file_location("numbered_catalog_for_session", script)
        nc = iu.module_from_spec(spec)
        spec.loader.exec_module(nc)
        self.nc = nc
        source, policy, self.db = [self.root / x for x in ["source.json", "roles.json", "numbers.sqlite"]]

        def row(ident, name):
            return {"id": ident, "title": name,
                    "products": [{"name": "某商品", "code": "c1"}],
                    "image_ids": [], "source_ids": [], "tested_by_project": False}

        source.write_text(json.dumps({"entries": [row("U01", "保留款"), row("U02", "将下架款")],
                                      "images": [], "sources": []}), encoding="utf8")
        policy.write_text(json.dumps({"recipes": {}}), encoding="utf8")
        nc.sync_database(source, self.db, policy)
        # Withdraw U02 the same way a real resync does: drop it from the source.
        source.write_text(json.dumps({"entries": [row("U01", "保留款")],
                                      "images": [], "sources": []}), encoding="utf8")
        nc.sync_database(source, self.db, policy)
        self.session_file = self.root / "session.json"
        ss.init_session(self.session_file)

    def test_active_unknown_and_withdrawn_are_classified(self):
        meta = ss.validate_selection_against_catalog(self.db, ["U01"])
        self.assertEqual(meta["U01"]["name"], "保留款")
        with self.assertRaisesRegex(ValueError, "不存在"):
            ss.validate_selection_against_catalog(self.db, ["U77"])
        with self.assertRaisesRegex(ValueError, "已下架"):
            ss.validate_selection_against_catalog(self.db, ["U02"])

    def test_unknown_id_never_enters_selection(self):
        with self.assertRaises(ValueError):
            ss.select_methods(self.session_file, ["U77"], database=self.db)
        self.assertEqual(ss.load_session(self.session_file)["current_selection"], [])

    def test_withdrawn_id_never_enters_selection(self):
        with self.assertRaises(ValueError):
            ss.select_methods(self.session_file, ["U02"], database=self.db)
        self.assertEqual(ss.load_session(self.session_file)["current_selection"], [])

    def test_batch_rejection_is_atomic(self):
        with self.assertRaises(ValueError):
            ss.select_methods(self.session_file, ["U01", "U77"], database=self.db)
        state = ss.load_session(self.session_file)
        self.assertEqual(state["current_selection"], [])
        self.assertEqual(state["selections"], [])

    def test_valid_selection_records_catalog_name(self):
        result = ss.select_methods(self.session_file, ["U01"], database=self.db)
        self.assertEqual(result["current_selection"], ["U01"])
        self.assertTrue(result["catalog_checked"])
        record = result["new_records"][0]
        self.assertEqual(record["name"], "保留款")
        self.assertEqual(record["number"], 1)

    def test_recommend_with_database_rejects_unknown(self):
        with self.assertRaises(ValueError):
            ss.recommend_round(self.session_file, ["U77"], database=self.db)
        self.assertEqual(ss.load_session(self.session_file)["rounds"], [])

    def test_recommend_with_database_records_check(self):
        rnd = ss.recommend_round(self.session_file, ["U01"], query="随便", database=self.db)
        self.assertTrue(rnd["catalog_checked"])
        self.assertEqual(rnd["catalog_meta"]["U01"]["name"], "保留款")

    def test_missing_database_is_reported(self):
        with self.assertRaisesRegex(ValueError, "编号数据库不存在"):
            ss.select_methods(self.session_file, ["U01"], database=self.root / "nope.sqlite")

    def test_non_numbered_ids_are_not_blocked(self):
        """Research IDs outside the numbered catalog are recorded unvalidated."""
        ss.recommend_round(self.session_file, ["R12"])
        result = ss.select_methods(self.session_file, ["R12"], database=self.db)
        self.assertEqual(result["current_selection"], ["R12"])


class CliInvocationTests(unittest.TestCase):
    """The documented command form must actually run: --session after the command."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.session_file = self.root / "cli.json"

    def _run(self, *argv):
        import contextlib
        import io
        buf = io.StringIO()
        old = __import__("sys").argv
        __import__("sys").argv = ["session_state.py", *argv]
        try:
            with contextlib.redirect_stdout(buf):
                code = ss.main()
        finally:
            __import__("sys").argv = old
        return code, buf.getvalue()

    def test_documented_init_then_recommend_then_select(self):
        code, out = self._run("init", "--session", str(self.session_file))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["current_selection"], [])

        code, out = self._run("recommend", "U11", "U12", "--query", "玉米",
                              "--session", str(self.session_file))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["round_id"], "RND001")

        code, out = self._run("select", "U11", "--round", "RND001",
                              "--session", str(self.session_file))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["current_selection"], ["U11"])

        code, out = self._run("status", "--session", str(self.session_file))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["current_selection"], ["U11"])

    def test_session_before_command_still_works(self):
        code, _ = self._run("--session", str(self.session_file), "init")
        self.assertEqual(code, 0)
        self.assertTrue(self.session_file.is_file())

    def test_error_path_returns_nonzero(self):
        self.session_file.write_text("{}", encoding="utf8")
        code, out = self._run("status", "--session", str(self.session_file))
        self.assertEqual(code, 2)
        self.assertIn("error", json.loads(out))


if __name__ == "__main__":
    unittest.main()
