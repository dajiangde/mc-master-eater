#!/usr/bin/env python3
"""Session state for continuous hidden-eating-method recommendation.

Tracks recommendation rounds, user selections, and the current selection list
across a conversation. State persists to a JSON file in a writable location.

Design:
  - Each recommendation round gets a stable round_id (RND001, RND002, ...)
    and records which method IDs were shown.
  - User selections are tracked by (method_id, round_id): the user picks
    from a specific round, and we keep that provenance.
  - current_selection is the running list the user is building; it
    persists across rounds.  Deselect removes from this list.
  - The state file never lives inside the skill package or research data.
"""
import argparse
import json
import re
import sqlite3
import time
import uuid
from pathlib import Path

SESSION_SCHEMA_VERSION = 1


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _utc_now_iso():
    # RFC 3339 / ISO 8601 UTC timestamp
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _valid_method_id(ident):
    """Accept U##, R##, HM##, CNB##, S## — stable IDs used across the project."""
    return isinstance(ident, str) and bool(re.fullmatch(
        r"(?:U|R|HM|CNB|S)[0-9]{2,4}", ident))


def _valid_round_id(ident):
    return isinstance(ident, str) and bool(re.fullmatch(r"RND[0-9]{3,}", ident))


def validate_selection_against_catalog(database, method_ids):
    """Verify every numbered ID exists and is active in the numbered database.

    Unknown or withdrawn IDs reject the whole batch; nothing is silenced or
    partially added. Non-numbered IDs (R##, HM##) are outside this database's
    authority and are returned unvalidated rather than blocked.
    """
    database = Path(database)
    _require(database.is_file(), "编号数据库不存在，请先确认 --database 路径：" + str(database))
    conn = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        resolved, missing, inactive = {}, [], []
        for mid in method_ids:
            if not re.fullmatch(r"U[0-9]{2,4}", mid):
                continue
            row = conn.execute(
                "SELECT id,number,title,card_title,active FROM recipes WHERE id=?", (mid,)
            ).fetchone()
            if row is None:
                missing.append(mid)
            elif not row["active"]:
                inactive.append(mid)
            else:
                resolved[mid] = {"number": row["number"], "name": row["title"],
                                 "card_title": row["card_title"]}
        reasons = []
        if missing:
            reasons.append("资料库中不存在：" + "、".join(missing))
        if inactive:
            reasons.append("已下架：" + "、".join(inactive))
        _require(not reasons, "；".join(reasons) + "。本次不加入任何编号，请重新选择。")
        return resolved
    finally:
        conn.close()


def load_session(path):
    """Load a session state file.  Raises if missing or corrupt."""
    path = Path(path)
    _require(path.is_file(), "Session file does not exist; run `init` first.")
    raw = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(raw, dict), "Session file is not a JSON object.")
    _require(raw.get("session_schema_version") == SESSION_SCHEMA_VERSION,
             "Unsupported session schema version.")
    _require(isinstance(raw.get("rounds"), list), "Session rounds must be a list.")
    _require(isinstance(raw.get("selections"), list), "Session selections must be a list.")
    _require(isinstance(raw.get("current_selection"), list), "current_selection must be a list.")
    raw.setdefault("seen_methods", [])  # Added after v1 shipped; old files still load.
    raw.setdefault("phase", "exploring")
    raw.setdefault("plan_generation", 0)
    _require(raw["phase"] in ("exploring", "purchasing"), "Unknown session phase.")
    return raw


def save_session(path, state):
    """Save session state atomically (write temp, then rename)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def init_session(path):
    """Create a new empty session file."""
    path = Path(path)
    _require(not path.exists(), "Session file already exists; use `status` to inspect or delete it first.")
    state = {
        "session_schema_version": SESSION_SCHEMA_VERSION,
        "created_at": _utc_now_iso(),
        "updated_at": _utc_now_iso(),
        "rounds": [],
        "selections": [],
        "current_selection": [],
        "seen_methods": [],
        "session_id": uuid.uuid4().hex,
        "phase": "exploring",
        "plan_generation": 0,
    }
    save_session(path, state)
    return state


def _next_round_id(rounds):
    """Generate the next round ID: RND001, RND002, ..."""
    max_num = 0
    for rnd in rounds:
        m = re.fullmatch(r"RND([0-9]{3,})", str(rnd.get("round_id", "")))
        if m:
            max_num = max(max_num, int(m.group(1)))
    return "RND" + str(max_num + 1).zfill(3)


def recommend_round(path, method_ids, query=None, source=None, database=None):
    """Record a new recommendation round with the shown method IDs.

    When a numbered database is supplied, every numbered ID must exist and be
    active before the round is recorded.
    """
    state = load_session(path)
    _require(isinstance(method_ids, list) and len(method_ids) > 0,
             "A recommendation round must show at least one method.")
    _require(all(_valid_method_id(mid) for mid in method_ids),
             "All method IDs must be valid stable IDs (e.g. U11, R12, HM01).")
    _require(len(method_ids) == len(set(method_ids)),
             "Duplicate method IDs in a single round are not allowed.")
    catalog_meta = validate_selection_against_catalog(database, method_ids) if database else {}
    round_id = _next_round_id(state["rounds"])
    rnd = {
        "round_id": round_id,
        "shown_methods": list(method_ids),
        "query": query,
        "source": source,
        "catalog_checked": bool(database),
        "created_at": _utc_now_iso(),
    }
    state["rounds"].append(rnd)
    seen = list(state.get("seen_methods", []))
    for mid in method_ids:
        if mid not in seen:
            seen.append(mid)
    state["seen_methods"] = seen
    state["updated_at"] = _utc_now_iso()
    save_session(path, state)
    rnd["catalog_meta"] = catalog_meta
    return rnd


def seen_methods(path):
    """Method IDs already shown in this session, oldest first."""
    return list(load_session(path).get("seen_methods", []))


def validate_selection(path, method_ids, round_id=None, database=None):
    """Check a selection without writing anything.

    Callers that replace the current list use this first, so a bad ID or a
    round mismatch fails before the old list is touched.
    """
    state = load_session(path)
    _require(isinstance(method_ids, list) and len(method_ids) > 0,
             "Provide at least one method ID to select.")
    _require(all(_valid_method_id(mid) for mid in method_ids),
             "All method IDs must be valid stable IDs.")
    _require(len(method_ids) == len(set(method_ids)),
             "Duplicate method IDs in a single selection are not allowed.")
    catalog_meta = validate_selection_against_catalog(database, method_ids) if database else {}
    if round_id is not None:
        _require(_valid_round_id(round_id), "Invalid round ID format.")
        round_ids = [r["round_id"] for r in state["rounds"]]
        _require(round_id in round_ids, "Unknown round ID; check `status` for available rounds.")
        rnd = next(r for r in state["rounds"] if r["round_id"] == round_id)
        for mid in method_ids:
            _require(mid in rnd["shown_methods"],
                     "Method {} was not shown in round {}; cannot select from a round that did not display it."
                     .format(mid, round_id))
    return {"state": state, "catalog_meta": catalog_meta}


def select_methods(path, method_ids, round_id=None, database=None):
    """Add method IDs to the current selection list.

    When a numbered database is supplied, every numbered ID is verified to
    exist and still be active before anything is added; an unknown or
    withdrawn ID rejects the whole batch.
    """
    checked = validate_selection(path, method_ids, round_id, database)
    state, catalog_meta = checked["state"], checked["catalog_meta"]
    new_records = []
    current = list(state["current_selection"])
    for mid in method_ids:
        if mid in current:
            continue  # Already selected; idempotent.
        current.append(mid)
        meta = catalog_meta.get(mid, {})
        record = {
            "method_id": mid,
            "round_id": round_id,
            "name": meta.get("name"),
            "number": meta.get("number"),
            "catalog_checked": bool(database),
            "selected_at": _utc_now_iso(),
        }
        state["selections"].append(record)
        new_records.append(record)
    state["current_selection"] = current
    state["updated_at"] = _utc_now_iso()
    save_session(path, state)
    return {"current_selection": current, "new_records": new_records,
            "catalog_checked": bool(database)}


def deselect_methods(path, method_ids):
    """Remove method IDs from the current selection list.

    The selection history is preserved (the record stays in selections[] but
    gets a deselected_at timestamp).  This way the user's full history is kept.
    """
    state = load_session(path)
    _require(isinstance(method_ids, list) and len(method_ids) > 0,
             "Provide at least one method ID to deselect.")
    _require(all(_valid_method_id(mid) for mid in method_ids),
             "All method IDs must be valid stable IDs.")
    current = list(state["current_selection"])
    removed = []
    for mid in method_ids:
        if mid not in current:
            continue  # Not in current selection; idempotent.
        current.remove(mid)
        removed.append(mid)
    # Mark deselected in history.
    now = _utc_now_iso()
    for record in reversed(state["selections"]):
        if record["method_id"] in removed and "deselected_at" not in record:
            record["deselected_at"] = now
    state["current_selection"] = current
    state["updated_at"] = now
    save_session(path, state)
    return {"current_selection": current, "removed": removed}


def get_status(path):
    """Return the full session state for display."""
    return load_session(path)


def set_phase(path, phase):
    """Purchase intent is recorded separately from selecting a recipe.

    This is workflow state, never consent to claim coupons or create an order.
    """
    _require(phase in ("exploring", "purchasing"), "Unknown session phase.")
    state = load_session(path)
    _require(phase != "purchasing" or state["current_selection"],
             "当前清单为空，先选编号再开始购买配置")
    state["phase"] = phase
    state["updated_at"] = _utc_now_iso()
    save_session(path, state)
    return state


def clear_selection(path):
    """Clear the current selection list but keep round and selection history."""
    state = load_session(path)
    now = _utc_now_iso()
    for record in reversed(state["selections"]):
        if record["method_id"] in state["current_selection"] and "deselected_at" not in record:
            record["deselected_at"] = now
    state["current_selection"] = []
    state["phase"] = "exploring"
    state["plan_generation"] += 1
    state.pop("purchase_plan_file", None)
    state["updated_at"] = now
    save_session(path, state)
    return {"current_selection": [], "cleared": True}


def reset_session(path):
    """Completely reset the session: new empty state, old file replaced."""
    path = Path(path)
    _require(path.is_file(), "Session file does not exist.")
    state = {
        "session_schema_version": SESSION_SCHEMA_VERSION,
        "created_at": _utc_now_iso(),
        "updated_at": _utc_now_iso(),
        "rounds": [],
        "selections": [],
        "current_selection": [],
        "seen_methods": [],
        "session_id": uuid.uuid4().hex,
        "phase": "exploring",
        "plan_generation": 0,
    }
    save_session(path, state)
    return state


def _common_options():
    """Options accepted both before and after the subcommand."""
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--session", type=Path, default=argparse.SUPPRESS,
                        help="Path to the session state JSON file.")
    common.add_argument("--database", type=Path, default=argparse.SUPPRESS,
                        help="Numbered catalog SQLite; when given, IDs are verified before use.")
    return common


def main():
    common = _common_options()
    parser = argparse.ArgumentParser(
        description="Session state for continuous hidden-eating recommendation.")
    parser.add_argument("--session", type=Path, default=None,
                        help="Path to the session state JSON file.")
    parser.add_argument("--database", type=Path, default=None,
                        help="Numbered catalog SQLite; when given, IDs are verified before use.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create a new empty session.", parents=[common])
    sub.add_parser("status", help="Show full session state.", parents=[common])

    rec = sub.add_parser("recommend", help="Record a recommendation round.", parents=[common])
    rec.add_argument("methods", nargs="+", help="Method IDs shown in this round.")
    rec.add_argument("--query", type=str, default=None, help="The query or theme of this round.")
    rec.add_argument("--source", type=str, default=None, help="Data source (e.g. numbered_catalog, research-lookup).")

    sel = sub.add_parser("select", help="Add methods to current selection.", parents=[common])
    sel.add_argument("methods", nargs="+", help="Method IDs to select.")
    sel.add_argument("--round", type=str, default=None, help="Round ID the user is selecting from.")

    des = sub.add_parser("deselect", help="Remove methods from current selection.", parents=[common])
    des.add_argument("methods", nargs="+", help="Method IDs to deselect.")

    sub.add_parser("clear", help="Clear current selection, keep history.", parents=[common])
    sub.add_parser("reset", help="Completely reset the session.", parents=[common])

    args = parser.parse_args()
    if not getattr(args, "session", None):
        parser.error("the following arguments are required: --session")
    try:
        if args.command == "init":
            result = init_session(args.session)
        elif args.command == "status":
            result = get_status(args.session)
        elif args.command == "recommend":
            result = recommend_round(args.session, args.methods, args.query, args.source,
                                     getattr(args, "database", None))
        elif args.command == "select":
            result = select_methods(args.session, args.methods, args.round,
                                    getattr(args, "database", None))
        elif args.command == "deselect":
            result = deselect_methods(args.session, args.methods)
        elif args.command == "clear":
            result = clear_selection(args.session)
        elif args.command == "reset":
            result = reset_session(args.session)
        else:
            raise ValueError("Unknown command: " + args.command)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, TypeError, KeyError, sqlite3.DatabaseError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
