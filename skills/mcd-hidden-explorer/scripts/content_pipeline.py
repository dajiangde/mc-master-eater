#!/usr/bin/env python3
"""One intake, immutable numbering and portable bundle pipeline. No MCP writes.

Only explicit --fetch-photo downloads a permitted GitHub attachment. Everything
else is offline. Raw photographs never enter content/ or a built Skill.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import struct
import sys
import tempfile
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numbered_catalog as nc

SKILL = Path(__file__).resolve().parents[1]
CONTENT = SKILL / 'content'
MAX_IMAGE_BYTES = 20 * 1024 * 1024
RIGHTS = {'owned', 'licensed', 'permission_granted'}
FIELDS = {'schema_version', 'key', 'title', 'category', 'products', 'configuration',
          'steps', 'step_basis', 'tested_by_project', 'optional', 'differences',
          'sources', 'menu_scope', 'image', 'display', 'photo_url'}
RECORD_FIELDS = FIELDS | {'id', 'status', 'review', 'card', 'thumbnail'}


def skill_name(skill):
    names = re.findall(r'^name:\s*([a-z0-9]+(?:-[a-z0-9]+)*)\s*$',
                       (Path(skill) / 'SKILL.md').read_text(encoding='utf-8').split('---', 2)[1], re.M)
    require(len(names) == 1, 'Skill 标识缺失或无效')
    return names[0]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def atomic_write(path, data):
    path = Path(path)
    temporary = path.with_name('.' + path.name + '.new')
    try:
        with temporary.open('x', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write('\n'); handle.flush(); os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def text(value, label, limit=2000):
    require(isinstance(value, str) and value.strip() and len(value) <= limit, label + '缺失或过长')
    require(not any(ord(c) < 32 and c not in '\n\t' for c in value), label + '含控制字符')
    return value.strip()


def date(value, label):
    require(isinstance(value, str), label + '缺少日期')
    try:
        datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError(label + '须为 ISO 日期或时间')


def public_url(value):
    parts = urlsplit(text(value, '来源链接'))
    require(parts.scheme == 'https' and parts.hostname and not parts.username and
            not parts.password and not parts.query and not parts.fragment and
            parts.port in (None, 443), '来源须为无签名、无凭据的 HTTPS 页面链接')
    return value


def owned(root, relative):
    p = Path(relative)
    require(not p.is_absolute() and '..' not in p.parts, '资源路径越界')
    target = Path(root) / p
    require(target.resolve().is_relative_to(Path(root).resolve()) and target.is_file()
            and not target.is_symlink(), '资源不存在或是软链接：' + str(relative))
    return target


def png_size(path):
    raw = Path(path).read_bytes()
    require(len(raw) >= 45 and raw[:8] == b'\x89PNG\r\n\x1a\n', '图片不是 PNG')
    position, size, compressed, ended, stride = 8, None, [], False, None
    while position < len(raw):
        require(position + 12 <= len(raw), 'PNG数据不完整')
        length = struct.unpack('>I', raw[position:position + 4])[0]
        kind = raw[position + 4:position + 8]
        payload = raw[position + 8:position + 8 + length]
        end = position + 12 + length
        require(end <= len(raw) and zlib.crc32(kind + payload) ==
                struct.unpack('>I', raw[end - 4:end])[0], 'PNG数据校验失败')
        require(kind in {b'IHDR', b'PLTE', b'IDAT', b'IEND', b'tRNS', b'sRGB', b'gAMA', b'cHRM', b'pHYs'},
                'PNG含未允许的元数据或动画，请重新导出加工图')
        if position == 8:
            require(kind == b'IHDR' and length == 13, 'PNG头无效')
            size = struct.unpack('>II', payload[:8])
            require(0 < size[0] <= 1080 and 0 < size[1] <= 1440, 'PNG尺寸过大')
            depth, colour, compression, filtering, interlace = payload[8:13]
            channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(colour)
            require(channels and depth in (1, 2, 4, 8, 16) and
                    (colour in (0, 3) or depth in (8, 16)) and (colour != 3 or depth <= 8) and
                    compression == filtering == interlace == 0, 'PNG编码不支持，请使用常规非交错PNG')
            stride = (size[0] * channels * depth + 7) // 8 + 1
        if kind == b'IDAT':
            compressed.append(payload)
        if kind == b'IEND':
            require(length == 0 and end == len(raw), 'PNG结尾无效'); ended = True
        position = end
    require(ended and compressed, 'PNG缺少像素数据或结尾')
    decoder = zlib.decompressobj()
    pixels = decoder.decompress(b''.join(compressed), 1080 * 1440 * 8 + 1441)
    require(pixels and decoder.eof and not decoder.unconsumed_tail and not decoder.unused_data, 'PNG像素数据损坏或过大')
    require(len(pixels) == stride * size[1] and all(pixels[i] <= 4 for i in range(0, len(pixels), stride)),
            'PNG像素行数据不完整')
    return size


def validate_submission(row):
    require(isinstance(row, dict) and not set(row) - FIELDS, '投稿含未知字段')
    require(row.get('schema_version') == 1, '不支持的投稿版本')
    require(re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', row.get('key', '')), '投稿 key 无效')
    text(row.get('title'), '名称', 60)
    text(row.get('category'), '类别', 30)
    require(isinstance(row.get('steps'), list) and row['steps'], '缺少操作步骤')
    for step in row['steps']:
        text(step, '步骤', 500)
    require(row.get('step_basis') in ('source_reported', 'project_suggestion'), '步骤依据未标注')
    require(type(row.get('tested_by_project')) is bool, '试做状态须明确为 true/false')
    require(isinstance(row.get('sources'), list) and row['sources'], '缺少来源')
    for source in row['sources']:
        require(set(source) <= {'url', 'author', 'published_at', 'captured_at', 'region', 'read_status'}, '来源含未知字段')
        public_url(source.get('url'))
        for field in ('author', 'region', 'read_status'):
            text(source.get(field), '来源 ' + field)
        date(source.get('captured_at'), '采集日期')
        if source.get('published_at') is not None:
            date(source['published_at'], '发布日期')
    image = row.get('image', {})
    require(set(image) <= {'kind', 'author', 'source_url', 'published_at', 'captured_at', 'region', 'photo_evidence', 'rights'}, '图片含未知字段')
    require(image.get('kind') in ('finished', 'process'), '须有吃法本身的实拍依据')
    for field in ('author', 'region', 'photo_evidence'):
        text(image.get(field), '图片 ' + field)
    public_url(image.get('source_url'))
    date(image.get('captured_at'), '图片采集日期')
    if image.get('published_at') is not None:
        date(image['published_at'], '图片发布日期')
    rights = image.get('rights', {})
    require(set(rights) <= {'status', 'basis'} and rights.get('status') in RIGHTS, '图片公开使用依据尚未确认')
    text(rights.get('basis'), '图片使用依据')
    scope = row.get('menu_scope', {})
    require(set(scope) == {'store_code', 'channel', 'checked_at', 'serving_time'}, '缺少门店核对上下文')
    for field in scope:
        text(scope[field], '门店核对 ' + field)
    date(scope['checked_at'], '菜单核对日期')
    products = row.get('products')
    require(isinstance(products, list) and products, '主要餐品映射尚未补齐')
    for product in products:
        require(set(product) <= {'name', 'code', 'parent_code', 'parent_name', 'time', 'evidence'}, '商品含未知字段')
        for field in ('name', 'code', 'time', 'evidence'):
            text(product.get(field), '商品 ' + field)
        if product.get('parent_code'):
            text(product.get('parent_code'), '父商品编码')
            text(product.get('parent_name'), '父商品名')
    config = row.get('configuration', {})
    require(set(config) <= {'optional_codes', 'choice_groups', 'purchase_quantities'}, '商品配置含未知字段')
    nc.validate_source({'entries': [{'id': 'U999999', 'title': row['title'], 'products': products}],
                        'images': [], 'sources': []}, {'recipes': {'U999999': config}})
    codes = {p['code'] for p in products}
    require(set(config.get('purchase_quantities', {})) == codes, '每项商品都须标明购买份数和依据')
    for rule in config.get('purchase_quantities', {}).values():
        require(set(rule) == {'quantity', 'status', 'basis'}, '份数配置含未知字段')
    for group in config.get('choice_groups', []):
        require(set(group) <= {'name', 'codes', 'default_code'} and group.get('default_code') in group['codes'], '口味组须有默认选项')
        options = [p for p in products if p['code'] in group['codes']]
        require(len({p.get('parent_code') for p in options}) == 1 and options[0].get('parent_code'), '口味选项须关联同一父商品')
    for label in ('products', 'steps'):
        values = row.get('display', {}).get(label)
        require(isinstance(values, list) and values, '缺少卡面 ' + label)
        for value in values:
            text(value, '卡面文字', 160)
    require(set(row.get('display', {})) <= {'products', 'steps'}, '卡面含未知字段')
    # Only labelled factual fields can reach a runtime database; never embed raw payloads.
    for field in ('optional', 'differences'):
        require(isinstance(row.get(field, ''), str), field + '须为文字')
    return row


def submission_of(record):
    return {k: v for k, v in record.items() if k in FIELDS}


def validate_catalog(root, baseline=None):
    root = Path(root)
    data = read(root / 'catalog.json')
    require(set(data) == {'schema_version', 'reserved_through', 'retired', 'recipes'} and
            data['schema_version'] == 1, '无效的收录目录')
    require(type(data['reserved_through']) is int and data['reserved_through'] >= 23, '历史编号 1～23 必须保留')
    require(isinstance(data['recipes'], list) and isinstance(data['retired'], list), '无效的条目列表')
    ids, keys, fingerprints, hashes = set(), set(), set(), set()
    for row in data['retired']:
        require(type(row.get('number')) is int and row['number'] > 0 and
                row.get('id') == 'U{:02d}'.format(row['number']), '停用编号无效')
        require(row['id'] not in ids, '停用编号重复')
        ids.add(row['id'])
    for row in data['recipes']:
        require(not set(row) - RECORD_FIELDS, '收录含未知字段')
        validate_submission(submission_of(row))
        ident = row.get('id', '')
        require(re.fullmatch(r'U[0-9]{2,}', ident) and ident == 'U{:02d}'.format(int(ident[1:])) and
                int(ident[1:]) > data['reserved_through'], '新吃法不能占用历史编号')
        require(ident not in ids and row['key'] not in keys, '编号或投稿 key 重复')
        ids.add(ident); keys.add(row['key'])
        require(row.get('status') in ('active', 'retired'), '收录状态无效')
        review = row.get('review', {})
        require(set(review) == {'by', 'at', 'recipe', 'image', 'menu'} and
                all(review.get(k) is True for k in ('recipe', 'image', 'menu')), '缺少逐项复核')
        text(review.get('by'), '复核人'); date(review.get('at'), '复核日期')
        fingerprint = (re.sub(r'\s+', '', row['title']), tuple(sorted(p['code'] for p in row['products'])))
        require(fingerprint not in fingerprints, '相同吃法重复收录')
        fingerprints.add(fingerprint)
        for kind, folder, size in [('card', 'cards', (1080, 1440)), ('thumbnail', 'thumbnails', (360, 480))]:
            asset = row.get(kind, {})
            require(set(asset) == {'path', 'sha256'} and asset['path'] == folder + '/' + ident + '.png', '图片编号或路径不一致')
            path = owned(root, asset['path'])
            require(path.stat().st_size <= MAX_IMAGE_BYTES and png_size(path) == size, '图片尺寸或大小不正确')
            require(digest(path) == asset['sha256'], '图片哈希不符：' + ident)
        require(row['card']['sha256'] not in hashes, '重复卡片')
        hashes.add(row['card']['sha256'])
    if baseline is not None:
        old = read(baseline)
        require(data['reserved_through'] == old['reserved_through'], '不得修改历史编号保留范围')
        old_retired = {r['id']: r for r in old['retired']}
        require(all(r in data['retired'] for r in old_retired.values()), '不得删除或复用停用编号')
        current = {r['key']: r for r in data['recipes']}
        old_max = max([data['reserved_through']] + [int(r['id'][1:]) for r in old['recipes']])
        old_keys = {r['key'] for r in old['recipes']}
        for row in old['recipes']:
            require(row['key'] in current and current[row['key']]['id'] == row['id'], '不得删除或重分配已收录编号；请停用')
            if row['status'] == 'retired':
                require(current[row['key']]['status'] == 'retired', '停用编号不得恢复复用')
        require(all(int(r['id'][1:]) > old_max for r in data['recipes'] if r['key'] not in old_keys), '新编号须在当前最大编号之后；请基于最新主分支重建')
    expected = {r[k]['path'] for r in data['recipes'] for k in ('card', 'thumbnail')}
    actual = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
    require(actual == expected | {'catalog.json'}, '存在缺失或未登记的文件；原图不能放入收录目录')
    return data


def add(root, submission, photo, reviewer, font=None, card=None, thumbnail=None):
    root = Path(root)
    lock = root.parent / ('.' + root.name + '.intake.lock')
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError('已有收录任务运行；停止并发写入，确认前一任务结束后再重试')
    try:
        os.close(descriptor)
        return _add(root, submission, photo, reviewer, font, card, thumbnail)
    finally:
        lock.unlink(missing_ok=True)


def _add(root, submission, photo, reviewer, font=None, card=None, thumbnail=None):
    """Both entry points call this function. It refuses updates and never copies a photo."""
    root = Path(root)
    data = validate_catalog(root)
    validate_submission(submission)
    require(not any(r['key'] == submission['key'] for r in data['recipes']), '该投稿已收录，拒绝重复编号')
    text(reviewer, '复核人')
    number = max([data['reserved_through']] + [int(r['id'][1:]) for r in data['recipes']] +
                 [r['number'] for r in data['retired']]) + 1
    ident = 'U{:02d}'.format(number)
    with tempfile.TemporaryDirectory(prefix='mcd-card-') as temporary:
        stage = Path(temporary)
        if photo:
            from render_card import render
            render(submission, number, Path(photo), stage / 'card.png', stage / 'thumbnail.png', font)
        else:
            require(card and thumbnail, '须提供本地照片，或已按新编号生成的主卡和缩图')
            shutil.copyfile(card, stage / 'card.png'); shutil.copyfile(thumbnail, stage / 'thumbnail.png')
        for name, size in [('card', (1080, 1440)), ('thumbnail', (360, 480))]:
            require(png_size(stage / (name + '.png')) == size, '加工图尺寸不正确')
        row = {**deepcopy(submission), 'id': ident, 'status': 'active',
               'review': {'by': reviewer, 'at': datetime.now(timezone(timedelta(hours=8))).date().isoformat(),
                          'recipe': True, 'image': True, 'menu': True}}
        row.pop('photo_url', None)
        created = []
        try:
            for name, folder in [('card', 'cards'), ('thumbnail', 'thumbnails')]:
                target = root / folder / (ident + '.png')
                target.parent.mkdir(exist_ok=True)
                require(not target.exists(), '图片已存在，拒绝覆盖')
                shutil.copyfile(stage / (name + '.png'), target); created.append(target)
                row[name] = {'path': folder + '/' + ident + '.png', 'sha256': digest(target)}
            data['recipes'].append(row)
            # Validate the whole prospective catalogue in an isolated directory first.
            check = stage / 'check'; shutil.copytree(root, check)
            write(check / 'catalog.json', data); validate_catalog(check)
            atomic_write(root / 'catalog.json', data)
        except Exception:
            for target in created:
                target.unlink(missing_ok=True)
            raise
    return {'id': ident, 'key': row['key'], 'card_sha256': row['card']['sha256']}


def compile_data(data):
    entries, sources, images, policies = [], [], [], {}
    retired = deepcopy(data['retired'])
    for row in data['recipes']:
        ident = row['id']
        if row['status'] == 'retired':
            retired.append({'id': ident, 'number': int(ident[1:]), 'title': row['title'], 'note': '已停用，编号保留'})
            continue
        sids = []
        for index, source in enumerate(row['sources']):
            sid = ident + '-source-' + str(index + 1)
            sources.append({'id': sid, 'title': row['title'], **source}); sids.append(sid)
        images.append({'id': ident + '-card', 'path': row['card']['path'],
                       'sha256': row['card']['sha256'], 'kind': 'processed_card',
                       'source_metadata': row['image'], 'rights': row['image']['rights']})
        entries.append({'id': ident, 'title': row['title'], 'category': row['category'],
                        'products': row['products'], 'source_ids': sids, 'image_ids': [ident + '-card'],
                        'suggested_steps': row['steps'], 'step_basis': row['step_basis'],
                        'tested_by_project': row['tested_by_project'], 'optional': row.get('optional', ''),
                        'differences': row.get('differences', ''), 'reference_time': row['menu_scope']['checked_at']})
        policies[ident] = {**row['configuration'], 'card_title': row['title']}
    return {'entries': entries, 'images': images, 'sources': sources,
            'menu_scope': {'notice': '历史参考，不代表本轮门店可售或实时价格',
                           'per_recipe': {r['id']: r['menu_scope'] for r in data['recipes'] if r['status'] == 'active'}}}, {
                'recipes': policies, 'retired': retired}


def bundle(root, skill, output, archive=None, baseline=None):
    root, skill, output = Path(root).resolve(), Path(skill).resolve(), Path(output).resolve()
    data = validate_catalog(root, baseline)
    require(not output.exists() and not output.is_relative_to(skill) and not output.is_relative_to(root), '输出目录已存在或位于源码内')
    if archive:
        archive = Path(archive).resolve()
        require(not archive.exists() and not archive.is_relative_to(output), 'ZIP已存在或位于包内')
    source, policy = compile_data(data)
    require(source['entries'], '暂无通过复核的可分发吃法；不生成空安装包')
    with tempfile.TemporaryDirectory(prefix='mcd-bundle-') as temporary:
        stage = Path(temporary) / skill_name(skill); stage.mkdir()
        shutil.copyfile(skill / 'SKILL.md', stage / 'SKILL.md')
        for folder, suffixes in [('scripts', {'.py'}), ('references', {'.md', '.json'})]:
            for path in (skill / folder).rglob('*'):
                if path.is_file() and path.suffix in suffixes and '__pycache__' not in path.parts:
                    require(not path.is_symlink(), '源码中不允许软链接')
                    if path.name in {'local-bundle.json', 'public-bundle.json'}:
                        continue
                    target = stage / path.relative_to(skill); target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, target)
        runtime = stage / 'data/unified-v2'; runtime.mkdir(parents=True)
        write(Path(temporary) / 'source.json', source); write(Path(temporary) / 'roles.json', policy)
        database = runtime / '隐藏吃法编号.sqlite3'
        nc.sync_database(Path(temporary) / 'source.json', database, Path(temporary) / 'roles.json')
        source_hash = digest(Path(temporary) / 'source.json')
        presentation = {'schema_version': 1, 'image_policy': 'processed_cards_only',
                        'source_catalog_sha256': source_hash, 'entries': []}
        for row in data['recipes']:
            if row['status'] != 'active':
                continue
            for kind in ('card', 'thumbnail'):
                target = runtime / row[kind]['path']; target.parent.mkdir(exist_ok=True)
                shutil.copyfile(owned(root, row[kind]['path']), target)
            presentation['entries'].append({'id': row['id'], 'title': row['title'], 'source_title': row['title'],
                'card': row['card']['path'], 'card_sha256': row['card']['sha256'],
                'thumbnail': row['thumbnail']['path'], 'thumbnail_sha256': row['thumbnail']['sha256'],
                'display_products': row['display']['products'], 'display_steps': row['display']['steps']})
        write(runtime / 'catalog.json', presentation)
        info = {'schema_version': 1, 'mode': 'reviewed_content_bundle', 'public_release': False,
                'skill_name': skill_name(skill),
                'distribution_eligible': True, 'active_count': len(source['entries']),
                'content_sha256': digest(root / 'catalog.json'), 'source_catalog_sha256': source_hash,
                'database': 'data/unified-v2/隐藏吃法编号.sqlite3', 'original_image_files': 0}
        write(stage / 'references/public-bundle.json', info)
        files = {str(p.relative_to(stage)): digest(p) for p in sorted(stage.rglob('*')) if p.is_file()}
        bundle_id = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
        write(stage / 'bundle-manifest.json', {**info, 'bundle_id': bundle_id, 'files': files})
        verify_bundle(stage)
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(stage, output)
    if archive:
        archive.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as z:
            for path in sorted(output.rglob('*')):
                if path.is_file():
                    z.write(path, str(Path(skill_name(skill)) / path.relative_to(output)))
    return {**info, 'bundle_id': bundle_id}


def verify_bundle(root):
    root = Path(root).resolve()
    manifest = read(root / 'bundle-manifest.json')
    actual = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts} - {'bundle-manifest.json'}
    require(actual == set(manifest['files']), '安装包文件清单不一致')
    for relative, expected in manifest['files'].items():
        require(digest(owned(root, relative)) == expected, '安装包哈希不一致：' + relative)
    require(manifest['bundle_id'] == hashlib.sha256(json.dumps(manifest['files'], sort_keys=True).encode()).hexdigest(), '安装包版本标识不一致')
    database = root / 'data/unified-v2/隐藏吃法编号.sqlite3'
    with sqlite3.connect(database) as conn:
        require(conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok' and
                not conn.execute('PRAGMA foreign_key_check').fetchall(), '安装包编号库损坏')
        ids = [r[0] for r in conn.execute('SELECT id FROM recipes WHERE active=1 ORDER BY number')]
    require(len(ids) == manifest['active_count'] and ids, '启用编号数不一致')
    cards = nc.cards(database, ids)
    require(cards['inline_image_count'] == len(ids), '安装包缺少正文图片')
    for card in cards['cards']:
        require(Path(card['hero_image_absolute_path']).is_relative_to(root), '图片依赖包外路径')
        require(png_size(card['hero_image_absolute_path']) == (1080, 1440), '安装包主卡损坏')
    presentation = read(database.parent / 'catalog.json')
    require({row['id'] for row in presentation['entries']} == set(ids), '卡片与启用编号不完全一致')
    for row in presentation['entries']:
        path = owned(database.parent, row['thumbnail'])
        require(digest(path) == row['thumbnail_sha256'] and png_size(path) == (360, 480), '安装包缩图损坏')
    import basket
    for ident in ids:
        methods = nc.resolve(database, ident)['methods']
        plan = basket.build_purchase_plan(methods)
        require(plan['items'], '吃法不能生成购买清单：' + ident)
        basket.build_price_items(plan)
        calories = basket.compute_calories(plan['items'], {})
        require(not calories['complete'] and calories['total_kcal'] is None, '缺失官方营养数据不能按0计算')
    return {'active_count': len(ids), 'inline_image_count': cards['inline_image_count'], 'files': len(actual)}


def issue_submission(issue):
    """Forms are Markdown, not trusted executable input. Unknown fields stay out."""
    sections = {}
    for match in re.finditer(r'^### ([^\n]+)\n+([\s\S]*?)(?=^### |\Z)', issue.get('body') or '', re.M):
        sections[match[1].strip()] = match[2].strip()
    def value(label):
        result = sections.get(label, '')
        return '' if result == '_No response_' else result
    def lines(label):
        return [re.sub(r'^\s*(?:[-*]|\d+[.)、])\s*', '', line).strip()
                for line in value(label).splitlines() if line.strip()]
    row = read(SKILL / 'references/submission-template.json')
    row.update(key='issue-' + str(int(issue['number'])), title=value('吃法名称'), category=value('类别'),
               steps=lines('做法'), step_basis='source_reported' if value('步骤依据') == '来源明确描述' else 'project_suggestion')
    captured = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    row['sources'] = [{'url': value('来源链接'), 'author': value('作者或出处'), 'published_at': None,
                       'captured_at': captured, 'region': value('地区与时段'), 'read_status': '投稿者提供，维护者待核'}]
    row['image'].update(author=value('作者或出处'), source_url=value('来源链接'), captured_at=captured,
                         region=value('地区与时段'), photo_evidence='投稿者提供，维护者待核')
    row['image']['rights'] = {'status': value('图片使用依据'), 'basis': value('图片授权说明')}
    urls = re.findall(r'https://github\.com/user-attachments/assets/[0-9a-fA-F-]{36}', value('允许公开的投稿配图'))
    row['photo_url'] = urls[0] if len(urls) == 1 else ''
    row['display'] = {'products': lines('所需餐品'), 'steps': row['steps'][:3]}
    config = value('维护者配置（可留空）')
    if config:
        config = re.sub(r'^```(?:json)?\s*|\s*```$', '', config)
        extra = json.loads(config)
        require(isinstance(extra, dict) and not set(extra) - (FIELDS - {'key', 'schema_version', 'photo_url'}), '维护者配置含未知字段')
        row.update(extra)
    return row


def download_photo(url, destination):
    """Allow only GitHub user attachments, check every redirect, limit response size."""
    require(re.fullmatch(r'https://github\.com/user-attachments/assets/[0-9a-fA-F-]{36}', url or ''), '只接受 GitHub 投稿附件地址')
    def allowed(target):
        p = urlsplit(target)
        require(p.scheme == 'https' and p.hostname in {'github.com', 'objects.githubusercontent.com',
                'private-user-images.githubusercontent.com', 'user-images.githubusercontent.com'} and
                not p.username and not p.password and p.port in (None, 443), '附件重定向到了不允许的地址')
    class Redirects(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            allowed(newurl)
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    with build_opener(Redirects()).open(Request(url, headers={'User-Agent': 'mc-master-eater-intake'}), timeout=30) as response:
        allowed(response.url)
        data = response.read(MAX_IMAGE_BYTES + 1)
        require(0 < len(data) <= MAX_IMAGE_BYTES, '附件为空或超过20MB')
    Path(destination).write_bytes(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare-issue'); p.add_argument('--issue', required=True, type=Path); p.add_argument('--output', required=True, type=Path)
    p = sub.add_parser('check-submission'); p.add_argument('--submission', required=True, type=Path)
    p = sub.add_parser('add'); p.add_argument('--submission', required=True, type=Path); p.add_argument('--content', type=Path, default=CONTENT)
    p.add_argument('--reviewer', required=True); p.add_argument('--photo', type=Path); p.add_argument('--fetch-photo', action='store_true')
    p.add_argument('--card', type=Path); p.add_argument('--thumbnail', type=Path); p.add_argument('--font', type=Path)
    p = sub.add_parser('validate'); p.add_argument('--content', type=Path, default=CONTENT); p.add_argument('--baseline', type=Path)
    p = sub.add_parser('build'); p.add_argument('--content', type=Path, default=CONTENT); p.add_argument('--skill', type=Path, default=SKILL)
    p.add_argument('--output', required=True, type=Path); p.add_argument('--zip', type=Path); p.add_argument('--baseline', type=Path)
    p = sub.add_parser('verify'); p.add_argument('--bundle', required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'prepare-issue':
            row = issue_submission(read(args.issue)); require(not args.output.exists(), '输出已存在，拒绝覆盖')
            args.output.parent.mkdir(parents=True, exist_ok=True); write(args.output, row)
            result = {'key': row['key'], 'status': 'pending', 'output': str(args.output)}
        elif args.command == 'check-submission':
            validate_submission(read(args.submission)); result = {'valid': True}
        elif args.command == 'add':
            row = read(args.submission)
            require(not (args.photo and args.fetch_photo), '本地照片与下载只能选一种')
            if args.fetch_photo:
                validate_submission(row)
                with tempfile.TemporaryDirectory(prefix='mcd-photo-') as temporary:
                    photo = Path(temporary) / 'photo'; download_photo(row.get('photo_url'), photo)
                    result = add(args.content, row, photo, args.reviewer, args.font)
            else:
                result = add(args.content, row, args.photo, args.reviewer, args.font, args.card, args.thumbnail)
        elif args.command == 'validate':
            data = validate_catalog(args.content, args.baseline)
            result = {'active_count': sum(r['status'] == 'active' for r in data['recipes']), 'valid': True}
        elif args.command == 'build':
            result = bundle(args.content, args.skill, args.output, args.zip, args.baseline)
        else:
            result = verify_bundle(args.bundle)
        print(json.dumps(result, ensure_ascii=False)); return 0
    except (ValueError, OSError, KeyError, TypeError, sqlite3.DatabaseError) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False), file=sys.stderr); return 2


if __name__ == '__main__':
    raise SystemExit(main())
