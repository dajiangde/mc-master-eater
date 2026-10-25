#!/usr/bin/env python3
"""Stable numbered selections over an explicitly supplied local research database.

No network calls. Existing numbers are reserved even when a recipe is withdrawn.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import re
import sqlite3
import unicodedata
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from image_delivery import inline_response

ALIAS_FILE = Path(__file__).resolve().parents[1] / 'references/product-aliases.json'

PACKAGED_DATABASE = Path(__file__).resolve().parents[1] / 'data/unified-v2/隐藏吃法编号.sqlite3'

SCHEMA_VERSION = '1'
SCHEMA = '''
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS recipes(
 id TEXT PRIMARY KEY, number INTEGER UNIQUE NOT NULL CHECK(number>0),
 title TEXT NOT NULL, card_title TEXT NOT NULL, active INTEGER NOT NULL,
 payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS products(
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, reference_code TEXT NOT NULL,
 UNIQUE(name,reference_code));
CREATE TABLE IF NOT EXISTS recipe_products(
 recipe_id TEXT NOT NULL REFERENCES recipes(id), product_id INTEGER NOT NULL REFERENCES products(id),
 position INTEGER NOT NULL, role TEXT NOT NULL CHECK(role IN ('required','optional','choice')),
 choice_group TEXT, reference_payload TEXT NOT NULL,
 PRIMARY KEY(recipe_id,product_id));
'''


def require(ok, message):
    if not ok:
        raise ValueError(message)


def dump(obj):
    return json.dumps(obj, ensure_ascii=False)


def open_db(database, readonly=True):
    database = Path(database).resolve()
    require(database.is_file(), '编号数据库不存在，请先使用明确的资料来源建立映射。')
    conn = sqlite3.connect(database.as_uri() + ('?mode=ro' if readonly else '?mode=rw'), uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    try:
        require(conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0]
                == SCHEMA_VERSION, '不支持的编号数据库版本')
    except (sqlite3.DatabaseError, TypeError, ValueError):
        conn.close()
        raise ValueError('不是隐藏吃法编号数据库')
    return conn


def validate_source(data, policy):
    require(isinstance(data, dict) and isinstance(data.get('entries'), list)
            and isinstance(data.get('images'), list) and isinstance(data.get('sources'), list),
            '需要统一图库资料；不接受公开 catalog 或旧批次表。')
    require(isinstance(policy, dict) and isinstance(policy.get('recipes', {}), dict), '无效的商品角色表')
    seen = set()
    for row in data['entries']:
        ident = row.get('id', '')
        require(re.fullmatch(r'U[0-9]{2,}', ident) and int(ident[1:]) > 0, '无效的统一编号')
        number = int(ident[1:])
        require(number not in seen, '编号重复')
        seen.add(number)
        require(isinstance(row.get('title'), str) and row['title'].strip(), '吃法缺少名称')
        products = row.get('products')
        require(isinstance(products, list) and products, '吃法缺少商品映射')
        codes = [p.get('code') for p in products]
        require(all(isinstance(p.get('name'), str) and p['name'] and isinstance(p.get('code'), str)
                    and p['code'] for p in products), '商品缺少名称或参考编码')
        require(len(codes) == len(set(codes)), '一款吃法内参考商品编码重复')
        rule = policy.get('recipes', {}).get(ident, {})
        require(isinstance(rule, dict), '无效的商品角色规则')
        quantities = rule.get('purchase_quantities', {})
        require(isinstance(quantities, dict) and set(quantities) <= set(codes), '采购份数规则引用了未知商品')
        for quantity_rule in quantities.values():
            require(isinstance(quantity_rule, dict) and type(quantity_rule.get('quantity')) is int
                    and quantity_rule['quantity'] > 0, '采购份数必须为正整数')
            require(quantity_rule.get('status') in ('source_reported', 'purchase_suggestion')
                    and isinstance(quantity_rule.get('basis'), str) and quantity_rule['basis'].strip(),
                    '采购份数缺少来源或待核状态')
        configured = set(rule.get('optional_codes', []))
        group_codes = []
        for group in rule.get('choice_groups', []):
            require(group.get('name') and len(group.get('codes', [])) >= 2, '选择组至少需要两个商品')
            group_codes += group['codes']
            default = group.get('default_code')
            require(default is None or default in group['codes'], '默认选项必须属于本选择组')
        require(not (configured & set(group_codes)) and len(group_codes) == len(set(group_codes)),
                '商品不能重复归入可选或多组选项')
        require((configured | set(group_codes)) <= set(codes), '角色规则引用了未知商品')
    require(set(policy.get('recipes', {})) <= {r['id'] for r in data['entries']}, '角色表引用未知吃法')
    active_numbers = {int(r['id'][1:]) for r in data['entries']}
    retired_numbers = set()
    for row in policy.get('retired', []):
        number = row.get('number')
        require(isinstance(number, int) and number > 0, '停用条目缺少有效编号')
        require(number not in active_numbers, '停用编号不能与在售编号冲突')
        require(number not in retired_numbers, '停用编号重复')
        retired_numbers.add(number)


def sync_database(source, database, policy_file):
    source, database = Path(source).resolve(), Path(database).resolve()
    require(database != source and database != Path(policy_file).resolve(), '数据库不能覆盖资料文件')
    raw_bytes = source.read_bytes()
    data = json.loads(raw_bytes)
    policy_bytes = Path(policy_file).read_bytes()
    policy = json.loads(policy_bytes)
    validate_source(data, policy)
    require(database.parent.is_dir(), '数据库父目录必须已经存在')
    # Do not take over arbitrary existing SQLite files.
    if database.exists():
        existing = open_db(database, readonly=False)
        existing.close()
    conn = sqlite3.connect(database)
    conn.execute('PRAGMA foreign_keys=ON')
    try:
        conn.executescript(SCHEMA)
        with conn:
            # Reserve withdrawn IDs; never reuse a number or delete its identity.
            conn.execute('UPDATE recipes SET active=0')
            for row in data['entries']:
                ident, number = row['id'], int(row['id'][1:])
                previous = conn.execute('SELECT number FROM recipes WHERE id=?', (ident,)).fetchone()
                require(not previous or previous[0] == number, '不允许修改已分配编号')
                occupied = conn.execute('SELECT id FROM recipes WHERE number=?', (number,)).fetchone()
                require(not occupied or occupied[0] == ident, '编号已被其他吃法永久占用')
                rule = policy.get('recipes', {}).get(ident, {})
                payload = {**row, 'mapped_images': [im for im in data['images'] if im['id'] in row.get('image_ids', [])],
                           'mapped_sources': [s for s in data['sources'] if s['id'] in row.get('source_ids', [])],
                           'menu_scope': data.get('menu_scope', {})}
                conn.execute('''INSERT INTO recipes VALUES(?,?,?,?,1,?)
                    ON CONFLICT(id) DO UPDATE SET title=excluded.title,card_title=excluded.card_title,
                    active=1,payload=excluded.payload''',
                    (ident, number, row['title'], rule.get('card_title', row['title']), dump(payload)))
                conn.execute('DELETE FROM recipe_products WHERE recipe_id=?', (ident,))
                choices = {code: g['name'] for g in rule.get('choice_groups', []) for code in g['codes']}
                defaults = {g.get('default_code') for g in rule.get('choice_groups', []) if g.get('default_code')}
                for pos, product in enumerate(row['products']):
                    conn.execute('INSERT OR IGNORE INTO products(name,reference_code) VALUES(?,?)',
                                 (product['name'], product['code']))
                    pk = conn.execute('SELECT id FROM products WHERE name=? AND reference_code=?',
                                      (product['name'], product['code'])).fetchone()[0]
                    role = ('optional' if product['code'] in rule.get('optional_codes', [])
                            else 'choice' if product['code'] in choices else 'required')
                    reference = {**product, 'is_default_choice': product['code'] in defaults,
                                 'purchase_quantity_rule': rule.get('purchase_quantities', {}).get(product['code'])}
                    conn.execute('INSERT INTO recipe_products VALUES(?,?,?,?,?,?)',
                                 (ident, pk, pos, role, choices.get(product['code']), dump(reference)))
            # Withdrawn methods keep their number forever; they stay queryable but inactive.
            for row in policy.get('retired', []):
                ident = row.get('id') or 'U{:02d}'.format(row['number'])
                previous = conn.execute('SELECT number FROM recipes WHERE id=?', (ident,)).fetchone()
                require(not previous or previous[0] == row['number'], '不允许修改已分配编号')
                occupied = conn.execute('SELECT id FROM recipes WHERE number=?', (row['number'],)).fetchone()
                require(not occupied or occupied[0] == ident, '编号已被其他吃法永久占用')
                title = row.get('title') or '（已停用）'
                payload = {'id': ident, 'number': row['number'], 'title': title, 'category': '已停用',
                           'retired': True, 'retired_on': row.get('retired_on'),
                           'retired_note': row.get('note', '')}
                conn.execute('''INSERT INTO recipes VALUES(?,?,?,?,0,?)
                    ON CONFLICT(id) DO UPDATE SET title=excluded.title,card_title=excluded.card_title,
                    active=0,payload=excluded.payload''',
                    (ident, row['number'], title, title, dump(payload)))
            metadata = {'schema_version': SCHEMA_VERSION,
                        'source_sha256': hashlib.sha256(raw_bytes).hexdigest(),
                        'policy_sha256': hashlib.sha256(policy_bytes).hexdigest(),
                        'mode': 'local_unified_research'}
            for key, value in metadata.items():
                conn.execute('INSERT OR REPLACE INTO meta VALUES(?,?)', (key, value))
    finally:
        conn.close()
    return {'active_recipes': len(data['entries']), 'source_sha256': metadata['source_sha256']}


def chinese_number(text):
    digits = dict(zip('零〇一二两三四五六七八九', [0, 0, 1, 2, 2, 3, 4, 5, 6, 7, 8, 9]))
    if all(c in digits for c in text):
        # Standard short Chinese ID words, not arbitrary digit sequences like 一一.
        require(len(text) == 1, '请用阿拉伯数字表达此编号')
        return digits[text]
    require(re.fullmatch(r'[一二两三四五六七八九]?十[一二三四五六七八九]?', text), '无法识别中文编号')
    tens, ones = text.split('十')
    return (digits[tens] if tens else 1) * 10 + (digits[ones] if ones else 0)


def parse_selection(text):
    require(isinstance(text, str) and text.strip(), '请提供固定编号')
    text = unicodedata.normalize('NFKC', text).strip()
    require('第' not in text, '“第几个”需要当前推荐批次；请提供卡片固定编号，如11号。')
    text = re.sub(r'^(?:我想要|我要|我选择|我选|选择|选|要)\s*', '', text)
    text = text.rstrip('。.!！')
    tokens = re.split(r'[、,，\s]+|以及|和|与|及', text)
    require(tokens and all(tokens), '编号表达不完整')
    ids = []
    for token in tokens:
        m = re.fullmatch(r'(?:编号)?(?:[Uu])?([0-9]+|[零〇一二两三四五六七八九十]+)(?:号)?', token)
        require(m, '只接受固定编号列表；份数、范围或其他要求请另外确认。')
        num = int(m[1]) if m[1].isascii() and m[1].isdigit() else chinese_number(m[1])
        require(num > 0, '编号必须大于0')
        ident = 'U' + str(num).zfill(2)
        if ident not in ids:
            ids.append(ident)
    return ids


def recipe_result(conn, row):
    payload = json.loads(row['payload'])
    mapped = []
    for p in conn.execute('''SELECT p.name,p.reference_code,rp.role,rp.choice_group,rp.reference_payload
            FROM recipe_products rp JOIN products p ON p.id=rp.product_id
            WHERE rp.recipe_id=? ORDER BY rp.position''', (row['id'],)):
        ref = json.loads(p['reference_payload'])
        mapped.append({'name': p['name'], 'role': p['role'], 'choice_group': p['choice_group'],
                       'quantity': None,
                       'purchase_quantity_suggestion': ref.get('purchase_quantity_suggestion'),
                       'purchase_quantity_rule': ref.get('purchase_quantity_rule'),
                       'is_default_choice': bool(ref.get('is_default_choice')),
                       'reference_menu': {'code': p['reference_code'], 'parent_code': ref.get('parent_code'),
                                          'parent_name': ref.get('parent_name'),
                                          'time': ref.get('time'), 'evidence': ref.get('evidence')},
                       'current_store_verified': False})
    groups = {}
    for p in mapped:
        if p['role'] == 'choice':
            groups.setdefault(p['choice_group'], []).append(p)
    product_choices = []
    for name, options in groups.items():
        default = next((p for p in options if p['is_default_choice']), None)
        product_choices.append({'name': name, 'choose': 1, 'options': options,
                                'default_code': default['reference_menu']['code'] if default else None,
                                'default_name': default['name'] if default else None})
    default_plan = [p['name'] for p in mapped if p['role'] == 'required']
    default_plan += [g['default_name'] for g in product_choices if g['default_name']]
    return {'id': row['id'], 'number': row['number'], 'display_number': str(row['number']) + '号',
            'name': row['title'], 'card_title': row['card_title'],
            'required_products': [p for p in mapped if p['role'] == 'required'],
            'optional_products': [p for p in mapped if p['role'] == 'optional'],
            'product_choices': product_choices,
            'default_plan': default_plan,
            'has_choices': bool(product_choices),
            'optional_notes': payload.get('optional', ''), 'variants': payload.get('variants', []),
            'suggested_steps': payload.get('suggested_steps', []),
            'step_basis': payload.get('step_basis'), 'tested_by_project': payload.get('tested_by_project', False),
            'differences': payload.get('differences', ''), 'reference_time': payload.get('reference_time'),
            'images': payload['mapped_images'], 'sources': payload['mapped_sources'],
            'historical_menu_scope': payload['menu_scope']}


def resolve(database, text):
    ids = parse_selection(text)
    conn = open_db(database)
    try:
        rows = []
        unknown = []
        retired = []
        for ident in ids:
            row = conn.execute('SELECT * FROM recipes WHERE id=?', (ident,)).fetchone()
            if row is None:
                unknown.append(ident)
            elif not row['active']:
                retired.append('{}（{}号）「{}」已停用，编号保留不再分配'.format(ident, row['number'], row['title']))
            else:
                rows.append(row)
        require(not retired, '；'.join(retired) + '。请改选其他编号。')
        require(not unknown, '未找到编号：' + '、'.join(unknown) + '；本次不返回部分选择。')
        return {'result_schema_version': 1, 'mode': 'local_unified_research', 'selection_ids': ids,
                'methods': [recipe_result(conn, r) for r in rows],
                'notice': '固定编号查询；历史菜单编码不证明当前供应、价格或下单规格。',
                'created_order': False}
    finally:
        conn.close()


def _lead_fillers():
    return set('我想要看找来找去吃帮有俺没请给')


def _trail_fillers():
    return ('相关', '系列', '类型', '那种', '一下', '一点', '的', '吗', '呢', '吧', '啊', '？', '?', '。', '，', ',')


def normalize_query(text):
    """Strip intent words so '想看薯条相关的' becomes '薯条'.

    Only leading intent characters and trailing particles are removed; product
    names such as 麦香鱼 or 玉米 are left intact.
    """
    require(isinstance(text, str) and text.strip(), '请说明想找的餐品或方向')
    t = unicodedata.normalize('NFKC', text).strip()
    changed = True
    while changed and len(t) > 1:
        changed = False
        for f in _trail_fillers():
            if len(t) > len(f) and t.endswith(f):
                t = t[:-len(f)].strip()
                changed = True
        while len(t) > 1 and t[0] in _lead_fillers():
            t = t[1:].strip()
            changed = True
    return t or text.strip()


def load_aliases(path=None):
    path = Path(path) if path else ALIAS_FILE
    require(path.is_file(), '别名表缺失：' + str(path))
    data = json.loads(path.read_text(encoding='utf-8'))
    require(isinstance(data, dict) and isinstance(data.get('families'), list), '别名表结构不正确')
    for family in data['families']:
        require(isinstance(family.get('id'), str) and isinstance(family.get('label'), str)
                and isinstance(family.get('aliases'), list), '别名条目缺少 id/label/aliases')
    return data


def match_families(query, alias_data):
    """Return the alias families the query refers to, honouring exclusions."""
    q = unicodedata.normalize('NFKC', query).casefold()
    hits = []
    for family in alias_data['families']:
        terms = [family['label']] + list(family['aliases'])
        if any(term and (term.casefold() in q or q in term.casefold()) for term in terms):
            hits.append(family)
    if not hits:
        return []
    blocked = set()
    for family in hits:
        for term in family.get('excludes', []):
            if term.casefold() not in q:
                blocked.add(term)
    return [f for f in hits if f['label'] not in blocked]


def _family_of_product(product_name, alias_data):
    name = unicodedata.normalize('NFKC', product_name).casefold()
    for family in alias_data['families']:
        for term in [family['label']] + list(family['aliases']):
            if term and (term.casefold() in name or name in term.casefold()):
                return family
    return None


def match_category_terms(query, alias_data):
    """Category words such as 炸鸡 cover several products without naming an SKU."""
    q = unicodedata.normalize('NFKC', query).casefold()
    for term in alias_data.get('category_terms', []):
        word = str(term.get('term', '')).casefold()
        if word and word in q:
            return term
    return None


def _recipe_products(conn, recipe_id):
    return [row['name'] for row in conn.execute(
        '''SELECT p.name FROM recipe_products rp JOIN products p ON p.id=rp.product_id
           WHERE rp.recipe_id=? ORDER BY rp.position''', (recipe_id,))]


def _payload_category(payload_text):
    try:
        return json.loads(payload_text).get('category') or '未分类'
    except (ValueError, TypeError):
        return '未分类'


def _result(conn, row, reason, matched_products=None):
    method = recipe_result(conn, row)
    return {'id': method['id'], 'number': method['number'],
            'display_number': method['display_number'], 'name': method['name'],
            'card_title': method['card_title'], 'category': _payload_category(row['payload']),
            'matched_products': matched_products or [],
            'reason': reason,
            'required_products': [p['name'] for p in method['required_products']],
            'optional_products': [p['name'] for p in method['optional_products']],
            'product_choices': [{'name': g['name'], 'default_code': g['default_code'],
                                 'default_name': g['default_name'],
                                 'options': [{'name': p['name'], 'code': p['reference_menu']['code'],
                                              'is_default': p['is_default_choice']} for p in g['options']]}
                                for g in method['product_choices']],
            'default_plan': method['default_plan'],
            'caption': card_caption(method)}


def find_by_product(database, query, limit=3, alias_path=None, exclude=()):
    """Find methods whose products match the query's product family.

    Product families are disjoint: 薯饼 never enters a 薯条 result. No invented
    results — an empty match returns suggestions instead.

    `exclude` holds IDs already shown in this session ("换一批"). Fresh results
    come first and the theme is kept; when the theme is used up the answer says
    so instead of silently repeating the same three cards.
    """
    exclude = {str(mid) for mid in (exclude or ())}
    alias_data = load_aliases(alias_path)
    cleaned = normalize_query(query)
    families = match_families(cleaned, alias_data)
    conn = open_db(database)
    try:
        if not families:
            term = match_category_terms(cleaned, alias_data)
            if term is not None:
                wanted = set(term['products'])
                scored = []
                for row in conn.execute('SELECT * FROM recipes WHERE active=1 ORDER BY number'):
                    hits = [name for name in _recipe_products(conn, row['id']) if name in wanted]
                    if hits:
                        scored.append((len(hits), row, hits))
                scored.sort(key=lambda item: (-item[0], item[1]['number']))
                fresh = [s for s in scored if s[1]['id'] not in exclude]
                methods = [_result(conn, row, '同类餐品匹配', hits)
                           for _, row, hits in fresh[:limit]]
                return {'result_schema_version': 1, 'mode': 'local_unified_research',
                        'entry': 'by_product', 'query': query, 'normalized': cleaned,
                        'matched_families': [term['label']],
                        'total_matched': len(scored), 'count': len(methods),
                        'methods': methods,
                        'fresh_count': len(fresh),
                        'exhausted': len(fresh) <= limit,
                        'excluded': sorted(exclude),
                        'notice': ('按%s匹配；同一类里的具体商品仍以当前门店菜单为准。' % term['label'])
                                  + ('这个主题的吃法已经全部看过。' if len(fresh) <= limit and scored else '')}
            return {'result_schema_version': 1, 'mode': 'local_unified_research',
                    'entry': 'by_product', 'query': query, 'normalized': cleaned,
                    'count': 0, 'methods': [],
                    'no_match_reason': '没有识别到可对应的餐品',
                    'suggestions': suggest_directions(conn, cleaned, alias_data),
                    'notice': '未匹配时不硬凑结果；可换一种叫法，或改用随机看看。'}
        family_ids = {f['id'] for f in families}
        scored = []
        for row in conn.execute('SELECT * FROM recipes WHERE active=1 ORDER BY number'):
            names = _recipe_products(conn, row['id'])
            hits = []
            for name in names:
                fam = _family_of_product(name, alias_data)
                if fam and fam['id'] in family_ids:
                    hits.append(name)
            if not hits:
                continue
            title_hit = any(f['label'].casefold() in row['title'].casefold() or
                            f['label'].casefold() in row['card_title'].casefold()
                            for f in families)
            scored.append((len(hits) + (1 if title_hit else 0), row, hits))
        scored.sort(key=lambda item: (-item[0], item[1]['number']))
        fresh = [s for s in scored if s[1]['id'] not in exclude]
        if not fresh and scored:
            return {'result_schema_version': 1, 'mode': 'local_unified_research',
                    'entry': 'by_product', 'query': query, 'normalized': cleaned,
                    'matched_families': [f['label'] for f in families],
                    'total_matched': len(scored), 'count': 0, 'methods': [],
                    'fresh_count': 0, 'exhausted': True,
                    'exhausted_reason': '这个主题的 {} 款吃法都已经看过了'.format(len(scored)),
                    'excluded': sorted(exclude),
                    'notice': '不重复展示同一批；可以换主题、选已有编号，或让我重新随机。'}
        methods = [_result(conn, row, '按餐品匹配', hits) for _, row, hits in fresh[:limit]]
        remaining = max(len(fresh) - len(methods), 0)
        notice = '按餐品匹配；份数未知不补，价格与供应须用当前门店实时结果核实。'
        if remaining == 0 and scored:
            notice += '这个主题的吃法已经全部看过。'
        return {'result_schema_version': 1, 'mode': 'local_unified_research',
                'entry': 'by_product', 'query': query, 'normalized': cleaned,
                'matched_families': [f['label'] for f in families],
                'total_matched': len(scored), 'count': len(methods), 'methods': methods,
                'fresh_count': len(fresh), 'remaining': remaining,
                'exhausted': remaining == 0,
                'excluded': sorted(exclude),
                'notice': notice}
    finally:
        conn.close()


def suggest_directions(conn, query, alias_data, limit=3):
    """Related directions when nothing matched — never invented dishes.

    Families sharing a character pair with the query come first; otherwise fall
    back to the categories that actually exist in the gallery.
    """
    q = unicodedata.normalize('NFKC', query)
    grams = {q[i:i + 2] for i in range(max(len(q) - 1, 1))}
    families = []
    for family in alias_data['families']:
        text = family['label'] + ''.join(family['aliases'])
        score = sum(1 for g in grams if g and g in text)
        if score:
            families.append((score, family['label']))
    families.sort(key=lambda item: (-item[0], item[1]))
    categories = {}
    for row in conn.execute('SELECT payload FROM recipes WHERE active=1'):
        category = _payload_category(row['payload'])
        categories[category] = categories.get(category, 0) + 1
    ranked = sorted(categories.items(), key=lambda item: (-item[1], item[0]))
    return {'families': [label for _, label in families[:limit]],
            'categories': [name for name, _ in ranked[:limit]]}


def random_batch(database, limit=3, seen=(), seed=None):
    """Random methods, preferring unseen ones and spreading across categories."""
    conn = open_db(database)
    try:
        rows = list(conn.execute('SELECT * FROM recipes WHERE active=1 ORDER BY number'))
        seen_set = set(seen)
        rng = random.Random(seed) if seed is not None else random.Random()
        unseen = [r for r in rows if r['id'] not in seen_set]
        fresh = unseen if len(unseen) >= limit else unseen + [r for r in rows if r['id'] in seen_set]
        by_category = {}
        for row in fresh:
            by_category.setdefault(_payload_category(row['payload']), []).append(row)
        categories = list(by_category)
        rng.shuffle(categories)
        for bucket in by_category.values():
            rng.shuffle(bucket)
        picked = []
        while len(picked) < min(limit, len(fresh)):
            progressed = False
            for category in categories:
                bucket = by_category[category]
                if bucket and len(picked) < min(limit, len(fresh)):
                    picked.append(bucket.pop(0))
                    progressed = True
            if not progressed:
                break
        methods = [_result(conn, row, '随机推荐',
                           _recipe_products(conn, row['id'])) for row in picked]
        return {'result_schema_version': 1, 'mode': 'local_unified_research',
                'entry': 'random', 'count': len(methods), 'methods': methods,
                'fresh_count': len(unseen),
                'notice': '随机推荐优先给没看过的新款；再次换一批会继续避开已看过的。'}
    finally:
        conn.close()


def coupon_link(database, coupon, limit=3, alias_path=None):
    """Associate a live coupon with gallery methods. Usability is never asserted."""
    alias_data = load_aliases(alias_path)
    conn = open_db(database)
    try:
        titles = [coupon.get(k) for k in ('title', 'name', 'display_name', 'description')]
        coupon_text = ' '.join(str(t) for t in titles if t)
        names, codes = [], set()
        if coupon.get('productName'):
            names.append(str(coupon['productName']).strip())
        if coupon.get('productCode'):
            codes.add(str(coupon['productCode']).strip())
        raw_products = coupon.get('products') or coupon.get('eligible_products') or []
        if isinstance(raw_products, dict):
            raw_products = [raw_products]
        for product in raw_products:
            if isinstance(product, dict):
                for key in ('productName', 'name'):
                    if product.get(key):
                        names.append(str(product[key]).strip())
                if product.get('productCode'):
                    codes.add(str(product['productCode']).strip())
            elif isinstance(product, str) and product.strip():
                names.append(product.strip())
        matched = []
        for row in conn.execute('SELECT * FROM recipes WHERE active=1 ORDER BY number'):
            products = _recipe_products(conn, row['id'])
            score, match_type, reasons = 0, 'no_match', []
            for cname in names:
                for pname in products:
                    if cname.casefold() == pname.casefold():
                        score, match_type = 100, 'exact'
                        reasons.append('商品名称精确匹配：' + pname)
                        break
                if score == 100:
                    break
            if score < 100:
                joined = ' '.join(products)
                if any(c and (c.casefold() in joined.casefold()) for c in names):
                    score, match_type = 70, 'possible'
                    reasons.append('券商品名包含于吃法商品名')
                elif any(p and p.casefold() in ' '.join(names).casefold() for p in products):
                    score, match_type = 70, 'possible'
                    reasons.append('吃法商品名包含于券商品名')
                elif coupon_text and any(p and p.casefold() in coupon_text.casefold() for p in products):
                    score, match_type = 30, 'possible'
                    reasons.append('券名或活动文案关联')
                else:
                    for cname in names:
                        fam = _family_of_product(cname, alias_data)
                        if fam and any(_family_of_product(p, alias_data) is fam for p in products):
                            score, match_type = 70, 'possible'
                            reasons.append('同一商品家族（' + fam['label'] + '），规格可能不同')
                            break
                    if not score and coupon_text:
                        # Campaign wording such as "薯条买一送一" names the family, not an SKU.
                        for pname in products:
                            fam = _family_of_product(pname, alias_data)
                            if not fam:
                                continue
                            terms = [fam['label']] + list(fam['aliases'])
                            if any(t and t.casefold() in coupon_text.casefold() for t in terms):
                                score, match_type = 30, 'possible'
                                reasons.append('券名或活动文案关联（' + fam['label'] + '）')
                                break
                    if not score and coupon_text:
                        # Category wording such as "王牌炸鸡任选2" covers several SKUs.
                        for term in alias_data.get('category_terms', []):
                            word = str(term.get('term', ''))
                            if not word or word.casefold() not in coupon_text.casefold():
                                continue
                            if any(p in set(term['products']) for p in products):
                                score, match_type = 30, 'possible'
                                reasons.append('券名同类餐品关联（' + term['label'] + '）')
                                break
            if score:
                item = _result(conn, row, '优惠关联', products)
                item['match'] = {'type': match_type, 'score': score,
                                 'tier': 'primary' if score >= 70 else 'supplementary',
                                 'reasons': reasons,
                                 'coupon_product_names': sorted(set(names)),
                                 'coupon_product_codes': sorted(codes),
                                 'usability': 'not_yet_confirmed',
                                 'usability_note': '需门店菜单核验与 calculate-price 确认'}
                matched.append(item)
        matched.sort(key=lambda m: (-m['match']['score'], m['number']))
        # Category fallback: the coupon product's broader category, inspiration only.
        coupon_fams = {f['id'] for f in (_family_of_product(n, alias_data) for n in names) if f}
        coupon_cats = []
        for term in alias_data.get('category_terms', []):
            fam_ids = {f['id'] for f in (_family_of_product(p, alias_data) for p in term.get('products', [])) if f}
            if fam_ids & coupon_fams:
                coupon_cats.append(term)
        seen_ids = {m['id'] for m in matched}
        for row in conn.execute('SELECT * FROM recipes WHERE active=1 ORDER BY number'):
            if row['id'] in seen_ids:
                continue
            products = _recipe_products(conn, row['id'])
            for term in coupon_cats:
                fam_ids = {f['id'] for f in (_family_of_product(p, alias_data) for p in term.get('products', [])) if f}
                if any((_family_of_product(p, alias_data) or {}).get('id') in fam_ids for p in products):
                    item = _result(conn, row, '优惠关联', products)
                    item['match'] = {'type': 'possible', 'score': 30, 'tier': 'supplementary',
                                     'reasons': ['券商品所属大类（' + term['label'] + '）补充灵感'],
                                     'coupon_product_names': sorted(set(names)),
                                     'coupon_product_codes': sorted(codes),
                                     'usability': 'not_yet_confirmed',
                                     'usability_note': '大类关联不代表这张券能用于这份吃法'}
                    matched.append(item)
                    break
        primary = [m for m in matched if m['match']['tier'] == 'primary']
        supplementary = [m for m in matched if m['match']['tier'] == 'supplementary']
        # Keep the two lists disjoint: an entry is either a direct match or
        # inspiration, never both, so counts can be added without double counting.
        shown_primary = primary[:limit]
        remaining = max(limit - len(shown_primary), 0)
        shown_supplementary = supplementary[:remaining] if remaining else []
        if not shown_primary and not shown_supplementary:
            shown_supplementary = supplementary[:limit]
        return {'result_schema_version': 1, 'mode': 'local_unified_research',
                'entry': 'by_coupon', 'coupon_title': coupon.get('title'),
                'total_matched': len(matched),
                'count': len(shown_primary) + len(shown_supplementary),
                'primary_count': len(shown_primary),
                'supplementary_count': len(shown_supplementary),
                'has_direct_match': bool(shown_primary),
                'methods': shown_primary,
                'supplementary': shown_supplementary,
                'notice': '主要推荐按商品命中；补充灵感仅同类相关，券未必覆盖。两者可用性均未确认。'}
    finally:
        conn.close()


def list_numbers(database):
    conn = open_db(database)
    try:
        return [{'id': r['id'], 'number': r['number'], 'display_number': str(r['number']) + '号',
                 'name': r['title'], 'card_title': r['card_title']}
                for r in conn.execute('SELECT * FROM recipes WHERE active=1 ORDER BY number')]
    finally:
        conn.close()


def choice_label(group):
    """Readable label for a choice group, showing the default option when known."""
    default = next((o for o in group.get('options', []) if o.get('is_default_choice')), None)
    if default is None:
        return group['name'] + '（任选一项）'
    parent = (default.get('reference_menu') or {}).get('parent_name')
    return '{}（默认{}）'.format(parent or group['name'], default['name'])


def list_retired(database):
    """Withdrawn numbers stay visible so nobody mistakes the gap for a new number."""
    conn = open_db(database)
    try:
        out = []
        for r in conn.execute('SELECT * FROM recipes WHERE active=0 ORDER BY number'):
            payload = json.loads(r['payload'])
            out.append({'id': r['id'], 'number': r['number'], 'display_number': str(r['number']) + '号',
                        'name': r['title'], 'retired_on': payload.get('retired_on'),
                        'note': payload.get('retired_note'),
                        'notice': '编号保留，不再分配；后续编号不因停用而前移。'})
        return out
    finally:
        conn.close()


def card_caption(method):
    """Keep optional ingredients and alternatives labelled in the caption."""
    products = [p['name'] for p in method['required_products']]
    products += [choice_label(g) for g in method['product_choices']]
    text = '、'.join(dict.fromkeys(products)) or '待核'
    if method['optional_products']:
        text += '；可选：' + '、'.join(p['name'] for p in method['optional_products'])
    return '[图片] {} · {}｜对应餐品：{}'.format(method['id'], method['card_title'], text)


def asset_path(root, relative):
    """Only return files inside the explicitly selected asset directory."""
    require(isinstance(relative, str) and relative and not Path(relative).is_absolute(),
            '图片必须是资料包内相对路径')
    result = (root / relative).resolve()
    require(result.is_relative_to(root.resolve()), '图片路径越出资料包')
    return result


def presentation_index(database, catalog=None):
    # Portable card-only libraries keep their catalog alongside the SQLite file.
    if catalog is None:
        bundled = Path(database).resolve().parent / 'catalog.json'
        if bundled.is_file():
            candidate = json.loads(bundled.read_text(encoding='utf-8'))
            if candidate.get('image_policy') == 'processed_cards_only':
                catalog = bundled
    catalog = Path(catalog) if catalog is not None else Path(database).resolve().parent.parent / 'base-cards-v1/catalog.json'
    if not catalog.is_file():
        return catalog, {}
    data = json.loads(catalog.read_text(encoding='utf-8'))
    require(data.get('schema_version') == 1 and isinstance(data.get('entries'), list), '无效的基础卡片数据')
    conn = open_db(database)
    try:
        source_hash = conn.execute("SELECT value FROM meta WHERE key='source_sha256'").fetchone()
        require(not data.get('source_catalog_sha256') or
                source_hash and data['source_catalog_sha256'] == source_hash[0],
                '卡片与编号库版本不一致，请更新完整资料包')
    finally:
        conn.close()
    result = {}
    for entry in data['entries']:
        ident = entry.get('id')
        require(isinstance(ident, str) and re.fullmatch(r'U[0-9]{2,}', ident)
                and ident not in result, '卡片编号无效或重复')
        path = asset_path(catalog.parent, entry.get('card'))
        require(path.name == ident + '.png', '卡片文件名与编号不一致')
        expected = entry.get('card_sha256')
        require(isinstance(expected, str) and re.fullmatch(r'[0-9a-f]{64}', expected), '卡片缺少有效哈希')
        result[ident] = entry
    return catalog, result


def cards(database, ids, card_catalog=None):
    """Deliver the approved PNG card by stable ID; source photos are evidence only."""
    ids = parse_selection('、'.join(ids))
    conn = open_db(database)
    try:
        image_root = Path(database).resolve().parent
        rows, unknown, retired = [], [], []
        for ident in ids:
            row = conn.execute('SELECT * FROM recipes WHERE id=?', (ident,)).fetchone()
            if row is None:
                unknown.append(ident)
            elif not row['active']:
                retired.append('{}（{}号）「{}」已停用，编号保留不再分配'.format(ident, row['number'], row['title']))
            else:
                rows.append(row)
        require(not retired, '；'.join(retired) + '。请改选其他编号。')
        require(not unknown, '未找到编号：' + '、'.join(unknown) + '；本次不返回部分结果。')
        catalog_path, presentation = presentation_index(database, card_catalog)
        payload = []
        for row in rows:
            method = recipe_result(conn, row)
            source_images = []
            for im in method['images']:
                path = asset_path(image_root, im['path'])
                source_images.append({'image_id': im.get('id'), 'absolute_path': str(path),
                                      'relative_path': im['path'], 'sha256': im.get('sha256'),
                                      'exists': path.is_file()})
            entry = presentation.get(method['id'])
            hero, ready, images = None, False, []
            reason = '缺少统一PNG卡片，请更新含图资料包；不回退到原始照片。'
            title = method['card_title']
            caption = card_caption(method)
            if entry:
                require(entry.get('source_title', method['name']) == method['name'], '卡片名称与编号库不一致')
                path = asset_path(catalog_path.parent, entry['card'])
                if path.is_file():
                    require(hashlib.sha256(path.read_bytes()).hexdigest() == entry['card_sha256'],
                            '卡片哈希不符：' + method['id'])
                    require(path.read_bytes()[:8] == b'\x89PNG\r\n\x1a\n', '卡片不是有效PNG：' + method['id'])
                    hero, ready, reason = str(path), True, None
                    images = [{'image_id': method['id'] + '-card', 'absolute_path': hero,
                               'relative_path': entry['card'], 'sha256': entry['card_sha256'],
                               'kind': 'presentation_card', 'mime_type': 'image/png', 'exists': True}]
                title = entry.get('title') or title
                display_products = entry.get('display_products')
                # A fixed list cannot show which option is the default; keep the computed caption.
                if display_products and not method['product_choices']:
                    caption = '[图片] {} · {}｜对应餐品：{}'.format(method['id'], title, ' / '.join(display_products))
            payload.append({'id': method['id'], 'number': method['number'],
                            'display_number': method['display_number'], 'name': method['name'],
                            'card_title': title, 'images': images, 'source_images': source_images,
                            'hero_image_absolute_path': hero, 'delivery_image_absolute_path': hero,
                            'delivery_kind': 'presentation_card', 'caption': caption,
                            'required_products': [p['name'] for p in method['required_products']],
                            'optional_products': [p['name'] for p in method['optional_products']],
                            'product_choices': [{'name': g['name'],
                                                 'default_code': g['default_code'],
                                                 'default_name': g['default_name'],
                                                 'options': [{'name': p['name'], 'code': p['reference_menu']['code'],
                                                              'is_default': p['is_default_choice']}
                                                             for p in g['options']]}
                                                for g in method['product_choices']],
                            'default_plan': method['default_plan'],
                            'optional_notes': method['optional_notes'], 'suggested_steps': method['suggested_steps'],
                            'tested_by_project': method['tested_by_project'],
                            'images_ready': ready, 'image_unavailable_reason': reason})
        return inline_response({'result_schema_version': 1, 'mode': 'local_unified_research',
                'count': len(payload), 'cards': payload, 'card_catalog': str(catalog_path),
                'notice': 'PNG为整理后的展示卡；原照片和来源作为证据保留。价格与供应需实时核实。',
                'created_order': False})
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sync = sub.add_parser('sync')
    sync.add_argument('--source', type=Path, required=True)
    sync.add_argument('--policy', type=Path, required=True)
    sync.add_argument('--database', type=Path, required=True)
    sel = sub.add_parser('select')
    sel.add_argument('text')
    sel.add_argument('--database', type=Path, default=PACKAGED_DATABASE)
    show = sub.add_parser('list')
    show.add_argument('--database', type=Path, default=PACKAGED_DATABASE)
    gone = sub.add_parser('retired')
    gone.add_argument('--database', type=Path, default=PACKAGED_DATABASE)
    card = sub.add_parser('cards')
    card.add_argument('ids', nargs='+')
    card.add_argument('--card-catalog', type=Path)
    card.add_argument('--database', type=Path, default=PACKAGED_DATABASE)
    rnd = sub.add_parser('random')
    rnd.add_argument('--database', type=Path, default=PACKAGED_DATABASE)
    rnd.add_argument('--limit', type=int, default=3)
    rnd.add_argument('--seen', nargs='*', default=[])
    rnd.add_argument('--seed', type=int)
    prod = sub.add_parser('by-product')
    prod.add_argument('query')
    prod.add_argument('--database', type=Path, default=PACKAGED_DATABASE)
    prod.add_argument('--limit', type=int, default=3)
    prod.add_argument('--aliases', type=Path)
    coup = sub.add_parser('coupon-link')
    coup.add_argument('--database', type=Path, default=PACKAGED_DATABASE)
    coup.add_argument('--coupon', type=str, required=True)
    coup.add_argument('--limit', type=int, default=3)
    coup.add_argument('--aliases', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'sync':
            result = sync_database(args.source, args.database, args.policy)
        elif args.command == 'select':
            result = resolve(args.database, args.text)
        elif args.command == 'list':
            result = list_numbers(args.database)
        elif args.command == 'retired':
            result = list_retired(args.database)
        elif args.command == 'cards':
            result = cards(args.database, args.ids, args.card_catalog)
        elif args.command == 'random':
            result = random_batch(args.database, args.limit, args.seen, args.seed)
        elif args.command == 'by-product':
            result = find_by_product(args.database, args.query, args.limit, args.aliases)
        else:
            result = coupon_link(args.database, json.loads(args.coupon), args.limit, args.aliases)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, sqlite3.DatabaseError, KeyError, TypeError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
