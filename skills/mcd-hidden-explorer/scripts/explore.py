#!/usr/bin/env python3
"""Offline hidden-eating catalog. Standard library only; no ordering side effects."""
import argparse
import html
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "references/catalog.json"


def validate(data):
    if data.get("schema_version") != 1 or not isinstance(data.get("entries"), list):
        raise ValueError("Unsupported catalog schema")
    seen = set()
    for row in data["entries"]:
        for key in ("id", "name", "recipe_status", "source_url", "observation", "ingredients", "steps"):
            if key not in row:
                raise ValueError("Missing field: " + key)
        for ident in [row["id"], *row.get("aliases", [])]:
            if not isinstance(ident, str) or not re.fullmatch(r"[A-Z][0-9]{2,4}", ident) or ident in seen:
                raise ValueError("Invalid or duplicate ID")
            seen.add(ident)
        url = urlsplit(row["source_url"])
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("Source must be a clean public HTTPS URL")
        if row["recipe_status"] not in ("cover_only", "reported_recipe"):
            raise ValueError("Unknown evidence status")
        if not isinstance(row["ingredients"], list) or not isinstance(row["steps"], list):
            raise ValueError("Ingredients and steps must be lists")
        if row["recipe_status"] == "cover_only" and (row["ingredients"] or row["steps"]):
            raise ValueError("Cover evidence cannot contain inferred recipes")
        for item in row["ingredients"]:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip():
                raise ValueError("Ingredient needs a name")
            quantity = item.get("quantity")
            if quantity is not None and (type(quantity) not in (int, float) or not 0 < quantity < float("inf")):
                raise ValueError("Quantity must be positive or null")
        if row.get("assets"):
            raise ValueError("Public text-only edition does not accept image assets yet")
    return data


def lookup(data, ident):
    ident = ident.strip().upper()
    for row in data["entries"]:
        if ident in [row["id"], *row.get("aliases", [])]:
            return {"canonical_id": row["id"], "requested_id": ident, "entry": row,
                    "next_action": "verify_source" if row["recipe_status"] == "cover_only" else "verify_current_menu"}
    raise ValueError("Unknown ID; choose a displayed stable identifier")


def render(data):
    esc = lambda value: html.escape(str(value), quote=True)
    cards = []
    for row in data["entries"]:
        cards.append('<article><small>' + esc(row["id"]) + ' · ' + esc(row["recipe_status"]) +
                     '</small><h2>' + esc(row["name"]) + '</h2><p>' + esc(row["observation"]) +
                     '</p><a target="_blank" rel="noopener noreferrer" href="' + esc(row["source_url"]) +
                     '">查看来源</a><p>回到聊天说：我选 ' + esc(row["id"]) + '</p></article>')
    body = ''.join(cards) or '<article><h2>等待收录你的隐藏吃法</h2><p>当前公开库为 0 条。请先录入有来源、可公开的资料；这里不会虚构配方或展示未授权图片。</p></article>'
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><title>麦麦隐藏吃法探索器</title><style>body{background:#faf7f0;color:#30281e;font:16px/1.7 system-ui;margin:0;padding:40px 6%}header{max-width:900px}h1{font-size:36px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:20px}article{padding:25px;background:white;border:1px solid #e6dccb;border-radius:18px}small,a{color:#9b3028}footer{margin-top:35px;color:#625a50}</style><header><p>MCD HIDDEN EXPLORER</p><h1>发现吃法，再配置餐品。</h1><p>看资料 → 选编号 → 核实配方 → MCP 核实门店餐品。民间组合不是官方隐藏商品。</p></header><main>''' + body + '</main><footer>当前为公开文字基础版。图片授权确认后另行接入。价格、库存和供应以门店实时结果为准。</footer></html>'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=DEFAULT)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    sub.add_parser("validate")
    find = sub.add_parser("lookup")
    find.add_argument("id")
    build = sub.add_parser("build")
    build.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        data = validate(json.loads(args.catalog.read_text(encoding="utf-8")))
        if args.command == "build":
            output = args.output.resolve()
            if output.exists() or output.suffix.lower() != ".html" or output.is_relative_to(ROOT / "references") or output.is_relative_to(ROOT / "scripts"):
                raise ValueError("Output must be a new HTML file outside references/scripts")
            with output.open("x", encoding="utf-8") as stream:
                stream.write(render(data))
            print(output)
        elif args.command == "lookup":
            print(json.dumps(lookup(data, args.id), ensure_ascii=False, indent=2))
        else:
            print(json.dumps({"valid": True, "count": len(data["entries"]), "entries": data["entries"] if args.command == "list" else []}, ensure_ascii=False, indent=2))
    except (ValueError, OSError, TypeError, KeyError) as exc:
        parser.exit(2, str(exc) + "\n")


if __name__ == "__main__":
    main()
