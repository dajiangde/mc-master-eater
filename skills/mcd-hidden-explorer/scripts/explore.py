#!/usr/bin/env python3
"""Offline hidden-eating catalog with stable IDs and batch selections."""
import argparse
from copy import deepcopy
import base64
import html
import json
import re
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "references/catalog.json"


def validate(data, root=ROOT):
    if data.get("schema_version") != 1 or not isinstance(data.get("entries"), list):
        raise ValueError("Unsupported catalog schema")
    seen = set()
    for row in data["entries"]:
        for key in ("id", "name", "recipe_status", "source_url", "observation", "ingredients", "steps"):
            if key not in row:
                raise ValueError("Missing field: " + key)
        for ident in [row["id"], *row.get("aliases", [])]:
            if not isinstance(ident, str) or not re.fullmatch(r"[A-Z]{1,3}[0-9]{2,4}", ident) or ident in seen:
                raise ValueError("Invalid or duplicate ID")
            seen.add(ident)
        url = urlsplit(row["source_url"])
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("Source must be a clean public HTTPS URL")
        if row["recipe_status"] not in ("cover_only", "reported_recipe"):
            raise ValueError("Unknown evidence status")
        if not isinstance(row["ingredients"], list) or not isinstance(row["steps"], list) or not isinstance(row.get("associated_meals", []), list):
            raise ValueError("Ingredients, associated meals and steps must be lists")
        for meal in row.get("associated_meals", []):
            if not isinstance(meal, dict) or not isinstance(meal.get("name"), str) or not meal["name"].strip():
                raise ValueError("Associated meal needs a name")
        if row["recipe_status"] == "cover_only" and (row["ingredients"] or row["steps"]):
            raise ValueError("Cover evidence cannot contain inferred recipes")
        for item in row["ingredients"]:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip():
                raise ValueError("Ingredient needs a name")
            quantity = item.get("quantity")
            if quantity is not None and (type(quantity) not in (int, float) or not 0 < quantity < float("inf")):
                raise ValueError("Quantity must be positive or null")
        for image in row.get("images", []):
            if not isinstance(image, dict) or not isinstance(image.get("path"), str):
                raise ValueError("Image needs a relative path")
            path = (root / image["path"]).resolve()
            if not path.is_relative_to(root.resolve()) or not path.exists():
                raise ValueError("Image path is missing or outside catalog root")
            if image.get("role") not in ("finished", "process", "collage", "unknown", None):
                raise ValueError("Unknown image role")
        if row.get("assets") and not row.get("images"):
            raise ValueError("Assets must be represented as images")
    return data


def _ordinal(text):
    m = re.fullmatch(r"第\s*([0-9一二三四五六七八九十]+)\s*个", text.strip())
    if not m:
        return None
    value = m.group(1)
    if value.isdigit():
        return int(value)
    chars = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    return chars.get(value)


def read_batch(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("ids"), list) or not data["ids"]:
        raise ValueError("Invalid or empty batch mapping")
    return data


def _text_tokens(value):
    text = str(value or "").casefold()
    text = re.sub(r"[^0-9a-z\u3400-\u9fff]+", " ", text)
    return {token for token in text.split() if token}


def _coupon_text(coupon):
    parts = [coupon.get("title"), coupon.get("name"), coupon.get("display_name"), coupon.get("description"), coupon.get("promotion_tag")]
    return " ".join(str(part) for part in parts if part)


def _meal_names(row):
    names = []
    for meal in row.get("associated_meals", []):
        if isinstance(meal, dict):
            names.extend([meal.get("name"), *meal.get("aliases", [])])
    names.extend([row.get("name"), *row.get("tags", [])])
    return [str(name) for name in names if name]


def recommend_by_coupons(data, coupons):
    """Rank hidden-eating entries by coupon relevance, without claiming eligibility.

    Exact product/rule hits outrank menu-name or category hits, which outrank
    title/campaign text hits. Partial and fuzzy associations remain visible.
    """
    results = []
    for row in data.get("entries", []):
        row_names = _meal_names(row)
        row_text = " ".join(row_names + [str(tag) for tag in row.get("tags", [])])
        row_tokens = _text_tokens(row_text)
        for coupon in coupons:
            coupon_text = _coupon_text(coupon)
            coupon_tokens = _text_tokens(coupon_text)
            score = 0
            reasons = []
            eligible = coupon.get("eligible_products") or coupon.get("eligibleProducts") or []
            eligible_names = []
            eligible_codes = set()
            for product in eligible:
                if isinstance(product, dict):
                    eligible_names.extend([product.get("name"), product.get("productName")])
                    if product.get("productCode"):
                        eligible_codes.add(str(product["productCode"]))
                elif product:
                    eligible_names.append(str(product))
            if eligible_codes:
                row_codes = {str(meal.get("productCode")) for meal in row.get("associated_meals", []) if isinstance(meal, dict) and meal.get("productCode")}
                if eligible_codes & row_codes:
                    score = max(score, 100)
                    reasons.append("商品规则命中")
            eligible_tokens = _text_tokens(" ".join(str(name) for name in eligible_names if name))
            if eligible_tokens & row_tokens or any(name and str(name).casefold() in row_text.casefold() for name in eligible_names):
                score = max(score, 70)
                reasons.append("商品名称或集合关联")
            if coupon_tokens & row_tokens or any(name and str(name).casefold() in coupon_text.casefold() for name in row_names):
                score = max(score, 30)
                reasons.append("券名或活动文案关联")
            if score:
                results.append({"coupon": coupon, "entry": row, "score": score, "reasons": reasons})
    return sorted(results, key=lambda item: (-item["score"], item["entry"]["id"], str(item["coupon"].get("title", item["coupon"].get("name", "")))))


def _coupon_label(coupon):
    for key in ("title", "name", "display_name"):
        value = coupon.get(key)
        if value:
            return str(value)
    return "未命名优惠券"


def _coupon_status(coupon):
    return str(coupon.get("status") or coupon.get("couponStatus") or "").strip()


CLAIMABLE_STATUS = ("可领取", "未领取", "available")
CLAIMED_STATUS = ("已领取", "claimed", "received")


def coupon_claim_plan(coupons):
    """Build a confirmation-ready claim plan. Never claims anything by itself.

    The live claim tool claims every currently available coupon at once, so a
    plan must say that picking one coupon is not possible, and that the user has
    to agree before the claim call happens.
    """
    claimable, claimed, unknown = [], [], []
    for coupon in coupons or []:
        status = _coupon_status(coupon)
        item = {"name": _coupon_label(coupon), "status": status or "未知"}
        if status in CLAIMABLE_STATUS:
            claimable.append(item)
        elif status in CLAIMED_STATUS:
            claimed.append(item)
        else:
            unknown.append(item)
    warnings = [
        "领券是整批领取：当前工具会领取所有可领优惠券，不能只领指定的一张。",
        "选择隐藏吃法编号不等于同意领券，必须先得到用户明确同意。",
    ]
    if not claimable:
        warnings.append("当前没有可领取的优惠券，无需执行领券。")
    return {
        "mode": "auto_bind_all",
        "selective": False,
        "requires_confirmation": True,
        "claimable": claimable,
        "already_claimed": claimed,
        "unknown_status": unknown,
        "warnings": warnings,
    }


def verify_claim(before, after):
    """Compare wallet snapshots before/after a claim to report what actually landed."""
    before_names = {_coupon_label(coupon) for coupon in before or []}
    after_names = {_coupon_label(coupon) for coupon in after or []}
    return {
        "newly_claimed": sorted(after_names - before_names),
        "unchanged": sorted(after_names & before_names),
        "missing_after_claim": sorted(before_names - after_names),
        "count_before": len(before_names),
        "count_after": len(after_names),
    }


ORDER_CONFIRM_PHRASES = ("确认下单", "创建订单", "确认支付并下单", "下单吧", "确认下单吧")

# The MCP returns camelCase while the skill scripts use snake_case. Accept both so a
# summary can be copied from a tool result without silent false blockers.
SUMMARY_FIELDS = {
    "store_code": ("store_code", "storeCode"),
    "store_name": ("store_name", "storeName"),
    "order_type": ("order_type", "orderType"),
    "be_type": ("be_type", "beType"),
    "take_way_code": ("take_way_code", "takeWayCode", "take_way", "takeWay"),
    "be_code": ("be_code", "beCode"),
    "price_checked_at": ("price_checked_at", "priceCheckedAt"),
    "total_cents": ("total_cents", "totalCents", "price", "price_cents"),
    "original_cents": ("original_cents", "originalPrice"),
    "discount_cents": ("discount_cents", "discount"),
    "calories": ("calories",),
    "items": ("items", "productList"),
}


def normalize_summary(summary):
    """Map camelCase MCP fields onto the snake_case keys used by the checks."""
    if not isinstance(summary, dict):
        raise ValueError("订单摘要必须是 JSON 对象")
    out = deepcopy(summary)
    for target, keys in SUMMARY_FIELDS.items():
        for key in keys:
            if key in summary and summary[key] is not None:
                out[target] = summary[key]
                break
    items = []
    for raw in out.get("items") or []:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        if "product_code" not in item and raw.get("productCode") is not None:
            item["product_code"] = raw["productCode"]
        if "product_name" not in item and raw.get("productName") is not None:
            item["product_name"] = raw["productName"]
        if "quantity" not in item and raw.get("quantity") is not None:
            item["quantity"] = raw["quantity"]
        items.append(item)
    out["items"] = items
    return out


def load_json_argument(value):
    """Accept inline JSON or a path to a JSON file; both are used in practice."""
    text = str(value).strip()
    if text.startswith("{") or text.startswith("["):
        return json.loads(text)
    path = Path(text)
    if not path.is_file():
        raise ValueError("找不到摘要文件：" + text + "（也可以直接传内联 JSON）")
    return json.loads(path.read_text(encoding="utf-8"))


def order_confirmation_warnings(summary):
    """Non-blocking gaps worth showing before the final confirmation."""
    calories = summary.get("calories") or {}
    if not calories:
        return ["摘要未附热量，需按官方营养数据补齐后再确认"]
    if calories.get("complete") is False or calories.get("label") == "已知部分热量":
        return ["热量为已知部分热量：" + "、".join(
            str(item.get("name")) for item in calories.get("missing") or [])]
    return []


def order_confirmation_blockers(summary, confirmed=False, confirmation_fingerprint=None, order_request=None):
    """Validate the quoted configuration, confirmed revision and submission payload."""
    import checkout_contract as checkout
    return checkout.order_blockers(summary or {}, confirmed, confirmation_fingerprint, order_request)


def lookup(data, ident, batch=None):
    text = str(ident).strip()
    ordinal = _ordinal(text)
    if ordinal is not None:
        if batch is None:
            raise ValueError("Ordinal selection requires the latest displayed batch")
        ids = batch["ids"]
        if ordinal < 1 or ordinal > len(ids):
            raise ValueError("Ordinal is outside the latest displayed batch")
        text = ids[ordinal - 1]
    normalized = text.upper()
    candidates = [row for row in data["entries"] if normalized in [row["id"], *row.get("aliases", [])]]
    if not candidates:
        candidates = [row for row in data["entries"] if text.casefold() == row["name"].casefold()]
    if not candidates:
        raise ValueError("Unknown selection; choose a displayed ID, name, or latest-batch ordinal")
    row = candidates[0]
    return {"canonical_id": row["id"], "requested": ident, "entry": row,
            "batch_position": (batch["ids"].index(row["id"]) + 1) if batch and row["id"] in batch["ids"] else None,
            "next_action": "verify_source" if row["recipe_status"] == "cover_only" else "verify_current_menu"}


def render(data, batch_ids=None, asset_root=ROOT):
    esc = lambda value: html.escape(str(value), quote=True)
    cards = []
    rows = data["entries"]
    for number, row in enumerate(rows, 1):
        meals = row.get("associated_meals", [])
        meal_text = "、".join(esc(x["name"]) + (" × " + esc(x["quantity"]) if x.get("quantity") is not None else "") for x in meals) or "待核"
        image_parts = []
        for image in row.get("images", []):
            raw = (asset_root / image["path"]).read_bytes() if image["path"].startswith("assets/") else None
            src = image["path"]
            if raw is not None:
                src = "data:image/webp;base64," + base64.b64encode(raw).decode("ascii")
            image_parts.append("<div class='image'><img alt='" + esc(row["name"]) + " · " + esc(image.get("role", "unknown")) + "' src='" + esc(src) + "'></div>")
        images = "".join(image_parts)
        cards.append('<article><p class="batch">' + (str(number) + ". " if batch_ids else "") + esc(row["id"]) + ' · ' + esc(row["recipe_status"]) +
                     '</p>' + images + '<h2>' + esc(row["name"]) + '</h2><p>' + esc(row["observation"]) +
                     '</p><p><strong>对应餐品：</strong>' + meal_text + '</p><a target="_blank" rel="noopener noreferrer" href="' + esc(row["source_url"]) +
                     '">查看来源</a><p>回到聊天说：我选 ' + esc(row["id"]) + '，或说“第 ' + str(number) + ' 个”</p></article>')
    body = ''.join(cards) or '<article><h2>等待收录你的隐藏吃法</h2><p>当前公开库为 0 条。请先录入有来源、可公开的资料。</p></article>'
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><title>麦麦隐藏吃法探索器</title><style>body{background:#faf7f0;color:#30281e;font:16px/1.7 system-ui;margin:0;padding:40px 6%}header{max-width:900px}h1{font-size:36px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:20px}article{padding:20px;background:white;border:1px solid #e6dccb;border-radius:18px}.image img{width:100%;max-height:260px;object-fit:contain}.batch,small,a{color:#9b3028}footer{margin-top:35px;color:#625a50}</style><header><p>MCD HIDDEN EXPLORER</p><h1>发现吃法，再配置餐品。</h1><p>本批次编号只对应本页顺序；选“第几个”时必须使用同一批映射。</p></header><main>''' + body + '</main><footer>图片、配方和门店可售性分别核实；价格与供应以实时结果为准。</footer></html>'


# ── Local research mode (schema_version 3, read-only, never touches public catalog) ──


def research_validate(data):
    """Validate that a research table has the expected schema-3 structure."""
    if not isinstance(data, dict):
        raise ValueError("Research catalog must be a JSON object")
    if data.get("schema_version") != 3:
        raise ValueError("Research catalog must have schema_version 3")
    entries = data.get("entries")
    if not isinstance(entries, list):
        raise ValueError("Research catalog entries must be a list")
    seen = set()
    for row in entries:
        if not isinstance(row, dict):
            raise ValueError("Research entry must be an object")
        rid = row.get("record_id")
        if not isinstance(rid, str) or not rid.strip():
            raise ValueError("Research entry needs a record_id")
        if rid in seen:
            raise ValueError("Duplicate record_id: " + rid)
        seen.add(rid)
    return data


def _research_product_names(row):
    """Collect all product-name strings from a research record."""
    names = []
    for key in ("dish_name", "dish_name_as_reported"):
        val = row.get(key)
        if isinstance(val, str) and val.strip():
            names.append(val)
    for item in row.get("needed_products_as_reported", []):
        if isinstance(item, str) and item.strip():
            names.append(item)
    for item in row.get("mainland_display_products", []):
        if isinstance(item, str) and item.strip():
            names.append(item)
    for mapping in row.get("product_name_mappings", []):
        if isinstance(mapping, dict):
            for key in ("source_name", "mainland_display_name", "mainland_canonical_name"):
                val = mapping.get(key)
                if isinstance(val, str) and val.strip():
                    names.append(val)
            for candidate in mapping.get("mainland_candidates", []):
                if isinstance(candidate, str) and candidate.strip():
                    names.append(candidate)
    return names


def unified_method(row, images_by_id, mode="local_research"):
    """Build a unified method object from a research record and image lookup."""
    resolved_images = []
    for image_id in row.get("image_ids", []):
        image = images_by_id.get(image_id)
        if not isinstance(image, dict):
            continue
        resolved_images.append({
            "id": image.get("image_id", image_id),
            "relative_path": image.get("path"),
            "sha256": image.get("sha256"),
            "kind": image.get("image_kind", image.get("kind")),
            "source_url": image.get("image_source_url", image.get("source_url")),
            "rights": image.get("rights"),
            "creator": image.get("creator"),
            "verification_status": image.get("photo_verification_status"),
        })
    required_products = []
    if row.get("evidence_status") != "cover_only":
        mappings = [m for m in row.get("product_name_mappings", []) if isinstance(m, dict)]
        used_indexes = set()
        for product in row.get("needed_products_as_reported", []):
            source_name = product if isinstance(product, str) else (
                product.get("source_name") if isinstance(product, dict) else None
            )
            if source_name is None:
                continue
            source_name = str(source_name)
            mapping = None
            for idx, cand in enumerate(mappings):
                cand_name = cand.get("source_name")
                if idx not in used_indexes and isinstance(cand_name, str) and cand_name.casefold() == source_name.casefold():
                    mapping = cand
                    used_indexes.add(idx)
                    break
            mapping = mapping or {}
            required_products.append({
                "source_name": source_name,
                "display_name": mapping.get("mainland_display_name") or source_name,
                "canonical_name": mapping.get("mainland_canonical_name"),
                "mapping_status": mapping.get("mapping_status"),
                "quantity": None,
                "quantity_evidence": row.get("quantity_evidence"),
            })
        for idx, mapping in enumerate(mappings):
            if idx in used_indexes:
                continue
            source_name = mapping.get("source_name") or mapping.get("mainland_display_name")
            if source_name is None:
                continue
            required_products.append({
                "source_name": source_name,
                "display_name": mapping.get("mainland_display_name") or source_name,
                "canonical_name": mapping.get("mainland_canonical_name"),
                "mapping_status": mapping.get("mapping_status"),
                "quantity": None,
                "quantity_evidence": row.get("quantity_evidence"),
            })
    unresolved = []
    for field in ("blocking_gaps", "recipe_pending_items", "product_name_pending_items", "image_pending_items"):
        items = row.get(field, [])
        if isinstance(items, list):
            unresolved.extend(items)
        elif items is not None:
            unresolved.append(str(items))
    if row.get("nonseasonal_status") == "unknown":
        unresolved.append({"field": "nonseasonal_status", "value": "unknown"})
    if row.get("current_store_verified") is False:
        unresolved.append({"field": "current_store_verified", "value": False})
    return {
        "id": row.get("record_id"),
        "name": row.get("dish_name"),
        "evidence_status": row.get("evidence_status"),
        "images": resolved_images,
        "required_products": required_products,
        "sources": list(row.get("recipe_sources") or []),
        "recipe": {
            "method_as_reported": None if row.get("evidence_status") == "cover_only" else row.get("method_as_reported"),
            "quantity_evidence": row.get("quantity_evidence"),
            "tested_by_project": row.get("recipe_tested_by_project", row.get("tested_by_project")),
        },
        "status": {
            "collection_status": row.get("collection_status"),
            "actionable": row.get("eligible_for_actionable_pool"),
            "nonseasonal_status": row.get("nonseasonal_status"),
            "current_store_verified": row.get("current_store_verified"),
            "unresolved": unresolved,
        },
        "mode": mode,
    }


def dedup_report(main_entries, batch_entries):
    """Compare supplemental batch entries against main entries and return disposition."""
    rules = {
        "CNB01": {"disposition": "variant", "canonical_id": None, "action": "keep_independent",
                   "reason": "different pie+mcflurry flavors from R15/R48"},
        "CNB02": {"disposition": "related_lead", "canonical_id": None, "action": "keep_independent",
                   "reason": "related to X03 but not the same recipe"},
        "CNB03": {"disposition": "new_method", "canonical_id": None, "action": "keep_independent",
                   "reason": "eating technique, not a flavor combination"},
        "CNB04": {"disposition": "same_method", "canonical_id": "R28", "action": "merge_source",
                   "reason": "fish+beef double already in historical library"},
        "CNB05": {"disposition": "same_method", "canonical_id": "R27", "action": "merge_source",
                   "reason": "land-air-sea combination already in historical library"},
        "CNB06": {"disposition": "same_method", "canonical_id": "R26", "action": "merge_source",
                   "reason": "chicken-nugget double cheeseburger already in historical library"},
        "CNB07": {"disposition": "lead", "canonical_id": None, "action": "keep_lead",
                   "reason": "cover_only, no recipe"},
        "CNB08": {"disposition": "same_method", "canonical_id": "R03", "action": "merge_image",
                   "reason": "same XHS note_id as X04"},
    }
    if isinstance(batch_entries, dict):
        batch_entries = batch_entries.get("entries", [])
    report = []
    for row in batch_entries:
        if not isinstance(row, dict):
            continue
        batch_id = row.get("id")
        rule = rules.get(batch_id)
        if rule is None:
            report.append({"batch_id": batch_id, "batch_name": row.get("name"),
                           "disposition": "unknown", "canonical_id": None,
                           "action": "manual_review", "reason": "no dedup rule for this entry"})
            continue
        report.append({
            "batch_id": batch_id,
            "batch_name": row.get("name"),
            "disposition": rule["disposition"],
            "canonical_id": rule["canonical_id"],
            "action": rule["action"],
            "reason": rule["reason"],
        })
    return report


def research_lookup(data, query):
    """Look up research records by product name or dish name.

    Returns unified method objects with stable ID, name, images, required products,
    sources, recipe, and all unresolved fields.
    """
    query_text = str(query).strip()
    if not query_text:
        raise ValueError("Research lookup query cannot be empty")
    images_by_id = {
        img["image_id"]: img for img in data.get("images", [])
        if isinstance(img, dict) and img.get("image_id")
    }
    query_lower = query_text.casefold()
    methods = []
    for row in data.get("entries", []):
        names = _research_product_names(row)
        if any(query_lower in name.casefold() for name in names):
            methods.append(unified_method(row, images_by_id))
    return {
        "result_schema_version": 1,
        "mode": "local_research",
        "query": query,
        "count": len(methods),
        "methods": methods,
    }


def coupon_match_research(data, coupon):
    """Match a single coupon against research records using unified method objects.

    Returns methods[] with match info. Usability is always 'not_yet_confirmed'.
    Does NOT use historical menu_code as coupon productCode.
    """
    images_by_id = {
        img["image_id"]: img for img in data.get("images", [])
        if isinstance(img, dict) and img.get("image_id")
    }
    coupon_title = coupon.get("title") or coupon.get("name") or ""
    coupon_products = coupon.get("products") or coupon.get("eligible_products") or coupon.get("eligibleProducts") or []
    if isinstance(coupon_products, dict):
        coupon_products = [coupon_products]
    coupon_product_names = []
    coupon_product_codes = set()
    direct_code = coupon.get("productCode")
    if direct_code is not None and str(direct_code).strip():
        coupon_product_codes.add(str(direct_code))
    direct_name = coupon.get("productName")
    if isinstance(direct_name, str) and direct_name.strip():
        coupon_product_names.append(direct_name.strip())
    for product in coupon_products:
        if isinstance(product, dict):
            for key in ("productName", "name"):
                val = product.get(key)
                if isinstance(val, str) and val.strip():
                    coupon_product_names.append(val.strip())
            code = product.get("productCode")
            if code is not None and str(code).strip():
                coupon_product_codes.add(str(code))
        elif isinstance(product, str) and product.strip():
            coupon_product_names.append(product.strip())
    product_name_text = " ".join(coupon_product_names)
    product_name_tokens = _text_tokens(product_name_text)
    title_tokens = _text_tokens(coupon_title)
    results = []
    for row in data.get("entries", []):
        row_names = _research_product_names(row)
        row_text = " ".join(row_names)
        row_tokens = _text_tokens(row_text)
        score = 0
        match_type = "no_match"
        reasons = []
        # Exact: coupon product name exactly equals a row product name
        for cname in coupon_product_names:
            for rname in row_names:
                if cname.strip() and cname.casefold() == rname.casefold():
                    score = 100
                    match_type = "exact"
                    reasons.append("商品名称精确匹配: " + rname)
                    break
            if score == 100:
                break
        # Possible: token overlap or bidirectional substring match
        if score < 100:
            if product_name_tokens and row_tokens and (product_name_tokens & row_tokens):
                score = max(score, 70)
                match_type = "possible"
                reasons.append("商品名称或集合关联")
            elif any(cname and cname.strip().casefold() in row_text.casefold() for cname in coupon_product_names if cname and cname.strip()):
                score = max(score, 70)
                match_type = "possible"
                reasons.append("券商品名包含于吃法商品名")
            elif any(rname and rname.strip().casefold() in product_name_text.casefold() for rname in row_names if rname and rname.strip()):
                score = max(score, 70)
                match_type = "possible"
                reasons.append("吃法商品名包含于券商品名")
        # Fallback: title/campaign text overlap
        if score == 0 and coupon_title:
            if title_tokens and row_tokens and (title_tokens & row_tokens):
                score = max(score, 30)
                match_type = "possible"
                reasons.append("券名或活动文案关联")
            elif any(rname and rname.strip().casefold() in coupon_title.casefold() for rname in row_names if rname and rname.strip()):
                score = max(score, 30)
                match_type = "possible"
                reasons.append("券名或活动文案关联")
        if score > 0:
            method = unified_method(row, images_by_id)
            method["match"] = {
                "type": match_type,
                "score": score,
                "reasons": reasons,
                "coupon_product_codes": sorted(coupon_product_codes),
                "coupon_product_names": coupon_product_names,
                "usability": "not_yet_confirmed",
                "usability_note": "需门店菜单核验与 calculate-price 确认后方可判断是否可用",
            }
            results.append(method)
    results.sort(key=lambda m: (-m["match"]["score"], str(m["id"])))
    return {
        "result_schema_version": 1,
        "coupon_title": coupon_title,
        "count": len(results),
        "methods": results,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=DEFAULT)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    sub.add_parser("validate")
    find = sub.add_parser("lookup")
    find.add_argument("selection")
    find.add_argument("--batch", type=Path)
    batch = sub.add_parser("batch")
    batch.add_argument("ids", nargs="+")
    batch.add_argument("--output", type=Path, required=True)
    build = sub.add_parser("build")
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--ids", nargs="*")
    # Research-mode subcommands (schema_version 3, read-only, never touches public catalog)
    rfind = sub.add_parser("research-lookup")
    rfind.add_argument("query")
    rfind.add_argument("--research-catalog", type=Path, required=True)
    rmatch = sub.add_parser("coupon-match")
    rmatch.add_argument("--research-catalog", type=Path, required=True)
    rmatch.add_argument("--coupon", type=str, required=True)
    rdedup = sub.add_parser("dedup")
    rdedup.add_argument("--research-catalog", type=Path, required=True)
    rdedup.add_argument("--batch-catalog", type=Path, required=True)
    cplan = sub.add_parser("claim-plan")
    cplan.add_argument("--coupons", type=Path, required=True)
    ocheck = sub.add_parser("order-check")
    ocheck.add_argument("--summary", required=True,
                        help="订单摘要：内联 JSON 或 JSON 文件路径，字段可用 camelCase 或 snake_case")
    ocheck.add_argument("--confirmed", action="store_true")
    ocheck.add_argument("--confirmation-fingerprint", help="用户刚确认的那份摘要的指纹")
    ocheck.add_argument("--order-request", help="按当前 MCP Schema 准备的完整待提交参数：JSON 或文件")
    args = parser.parse_args()
    try:
        if args.command == "claim-plan":
            raw = json.loads(args.coupons.read_text(encoding="utf-8"))
            coupons = raw.get("coupons", []) if isinstance(raw, dict) else raw
            print(json.dumps(coupon_claim_plan(coupons), ensure_ascii=False, indent=2))
            return
        if args.command == "order-check":
            summary = load_json_argument(args.summary)
            order_request = load_json_argument(args.order_request) if args.order_request else None
            blockers = order_confirmation_blockers(summary, args.confirmed,
                args.confirmation_fingerprint, order_request)
            print(json.dumps({"allowed": not blockers, "blockers": blockers,
                              "warnings": order_confirmation_warnings(summary),
                              "summary": summary}, ensure_ascii=False, indent=2))
            if blockers:
                raise SystemExit(3)
            return
        # Research-mode commands use schema_version 3 and bypass public validate()
        if args.command in ("research-lookup", "coupon-match", "dedup"):
            rdata = research_validate(json.loads(args.research_catalog.read_text(encoding="utf-8")))
            if args.command == "research-lookup":
                print(json.dumps(research_lookup(rdata, args.query), ensure_ascii=False, indent=2))
            elif args.command == "coupon-match":
                coupon = json.loads(args.coupon)
                print(json.dumps(coupon_match_research(rdata, coupon), ensure_ascii=False, indent=2))
            else:
                bdata = json.loads(args.batch_catalog.read_text(encoding="utf-8"))
                report = dedup_report(rdata.get("entries", []), bdata.get("entries", []))
                print(json.dumps({"result_schema_version": 1, "dedup_report": report}, ensure_ascii=False, indent=2))
            return
        # Public catalog commands use schema_version 1
        data = validate(json.loads(args.catalog.read_text(encoding="utf-8")), args.catalog.parent.parent)
        if args.command == "build":
            rows = data["entries"] if not args.ids else [lookup(data, item)["entry"] for item in args.ids]
            batch_ids = [row["id"] for row in rows]
            output = args.output.resolve()
            if output.exists() or output.suffix.lower() != ".html":
                raise ValueError("Output must be a new HTML file")
            with output.open("x", encoding="utf-8") as stream:
                stream.write(render({"schema_version": 1, "entries": rows}, batch_ids, args.catalog.parent.parent))
            print(output)
        elif args.command == "batch":
            ids = [lookup(data, item)["entry"]["id"] for item in args.ids]
            if len(set(ids)) != len(ids):
                raise ValueError("Batch cannot repeat an ID")
            output = args.output.resolve()
            if output.exists():
                raise ValueError("Batch output already exists")
            output.write_text(json.dumps({"ids": ids}, ensure_ascii=False, indent=2), encoding="utf-8")
            print(output)
        elif args.command == "lookup":
            batch_data = read_batch(args.batch) if args.batch else None
            print(json.dumps(lookup(data, args.selection, batch_data), ensure_ascii=False, indent=2))
        else:
            print(json.dumps({"valid": True, "count": len(data["entries"]), "entries": data["entries"] if args.command == "list" else []}, ensure_ascii=False, indent=2))
    except (ValueError, OSError, TypeError, KeyError) as exc:
        parser.exit(2, str(exc) + "\n")


if __name__ == "__main__":
    main()
