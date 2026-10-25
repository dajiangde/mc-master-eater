#!/usr/bin/env python3
"""Export a card-only runtime library; raw research remains outside the package.

The output stays local. This tool neither publishes nor determines image rights.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
from urllib.parse import urlsplit, urlunsplit
import zipfile


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def owned_file(root, relative):
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Asset path must stay inside the card directory')
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
        raise ValueError('Asset missing or outside card directory')
    return resolved


def sources_only(sources):
    result = []
    for source in sources:
        parts = urlsplit(source.get('url', ''))
        host = parts.hostname or ''
        if parts.scheme != 'https' or not host or parts.username or parts.password:
            continue
        if 'xhscdn' in host or Path(parts.path).suffix.lower() in {'.jpg','.webp','.jpeg','.png','.gif'}:
            continue
        # Keep attribution page links, never expiring signatures or direct image URLs.
        result.append({'id': source.get('id'), 'title': source.get('title'),
                       'url': urlunsplit((parts.scheme, parts.netloc, parts.path, '', ''))})
    return result


def export_library(card_root, source_database, output):
    card_root, source_database, output = map(lambda p: Path(p).resolve(), (card_root, source_database, output))
    if output.exists() or not output.parent.is_dir():
        raise ValueError('Output must not exist and its parent must exist')
    source = json.loads((card_root / 'catalog.json').read_text())
    rows = source['entries']
    ids = [r['id'] for r in rows]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError('Missing or duplicate card IDs')
    checked = {}
    for r in rows:
        for kind in ['card', 'thumbnail']:
            path = owned_file(card_root, r[kind])
            if path.suffix.lower() != '.png' or digest(path) != r[kind + '_sha256']:
                raise ValueError('Processed card hash/type mismatch')
            checked[(r['id'], kind)] = path
    conn = sqlite3.connect(source_database.as_uri() + '?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    records = list(conn.execute('SELECT * FROM recipes ORDER BY number'))
    if {r['id'] for r in records if r['active']} != set(ids):
        conn.close()
        raise ValueError('Active database IDs must exactly match card IDs')
    output.mkdir()
    try:
        (output / 'cards').mkdir(); (output / 'thumbnails').mkdir()
        card_map, exported = {}, []
        for r in rows:
            ident = r['id']
            for kind, folder in [('card','cards'), ('thumbnail','thumbnails')]:
                shutil.copy2(checked[(ident,kind)], output / folder / (ident + '.png'))
            im = {'id': ident + '-card', 'path': 'cards/' + ident + '.png',
                  'sha256': r['card_sha256'], 'kind': 'processed_card'}
            card_map[ident] = (r, im)
            exported.append({'id': ident, 'title': r['title'], 'category': r['category'],
                             'card': im['path'], 'thumbnail': 'thumbnails/' + ident + '.png',
                             'card_sha256': r['card_sha256'], 'thumbnail_sha256': r['thumbnail_sha256'],
                             'display_products': r['display_products'], 'display_steps': r['display_steps'],
                             'display_note': r.get('display_note'), 'nutrition': r.get('nutrition')})
        # New SQLite from schema, not a backup+DELETE: no raw-image payload can survive in freed pages.
        target = sqlite3.connect(output / 'numbered-catalog.sqlite3')
        target.execute('PRAGMA foreign_keys=ON')
        for table in ['meta','recipes','products','recipe_products']:
            ddl = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()
            if not ddl:
                raise ValueError('Unsupported numbered database schema')
            target.execute(ddl[0])
        for r in records:
            p = json.loads(r['payload'])
            safe = {k:p.get(k) for k in ['category','optional','differences','reference_time','suggested_steps',
                                          'step_basis','tested_by_project','menu_scope']}
            safe['mapped_sources'] = sources_only(p.get('mapped_sources', []))
            safe['variants'] = [{k:v.get(k) for k in ['name','purchase','difference']}
                                for v in p.get('variants', [])]
            safe['mapped_images'] = [card_map[r['id']][1]] if r['active'] else []
            if r['active']:
                safe['nutrition'] = card_map[r['id']][0].get('nutrition')
            target.execute('INSERT INTO recipes VALUES(?,?,?,?,?,?)',
                           (r['id'],r['number'],r['title'],r['card_title'],r['active'],json.dumps(safe,ensure_ascii=False)))
        # Product and role rows contain no photographs; retain exact menu references/roles.
        for table in ['products','recipe_products']:
            for r in conn.execute('SELECT * FROM '+table):
                target.execute('INSERT INTO '+table+' VALUES('+','.join('?' for _ in r)+')',tuple(r))
        target.executemany('INSERT INTO meta VALUES(?,?)', [
            ('schema_version','1'), ('mode','processed_card_library'),
            ('image_policy','processed_cards_only'), ('rights','local_research_unconfirmed_public_reuse')])
        target.commit()
        if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Exported database integrity error')
        if target.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Exported database relation error')
        target.close()
        (output/'catalog.json').write_text(json.dumps({'schema_version':1,'image_policy':'processed_cards_only',
            'count':len(exported),'entries':exported},ensure_ascii=False,indent=2)+'\n')
        (output/'README.md').write_text('# 加工卡片运行资料包\n\n仅含成品PNG、缩图、编号/餐品SQLite与精简资料。无原图、源图地址、渲染HTML、采集快照或历史缓存。\n\n配合现有Skill的numbered_catalog.py/discover.py，通过--database指向包内numbered-catalog.sqlite3；图片路径均相对数据库目录。停用编号保留，不复用。此包是本地资料导出，不是完整Skill安装包，也未宣称获得图片公开使用权。\n\n热量为指定份数的参考或已知部分，具体依据保留于catalog.json。配方/当前供应/价格与来源试做状态仍需按返回字段区分。\n')
        files = {str(p.relative_to(output)):digest(p) for p in sorted(output.rglob('*')) if p.is_file()}
        (output/'manifest.json').write_text(json.dumps({'image_policy':'processed_cards_only','card_count':len(rows),
                'thumbnail_count':len(rows),'original_image_files':0,'files':files},ensure_ascii=False,indent=2)+'\n')
    finally:
        conn.close()
    return {'cards':len(rows),'original_image_files':0,'database':'numbered-catalog.sqlite3'}


def make_zip(folder, output):
    folder, output = Path(folder).resolve(), Path(output).resolve()
    if output.exists() or output.is_relative_to(folder):
        raise ValueError('ZIP must not exist and must be outside the library')
    with zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED) as archive:
        for name in ['README.md','catalog.json','numbered-catalog.sqlite3','manifest.json']:
            archive.write(folder/name,name)
        for sub in ['cards','thumbnails']:
            for p in sorted((folder/sub).glob('U*.png')):
                archive.write(p,str(p.relative_to(folder)))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cards',type=Path,required=True)
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--zip',type=Path)
    args=parser.parse_args()
    result=export_library(args.cards,args.database,args.output)
    if args.zip:make_zip(args.output,args.zip)
    print(json.dumps(result,ensure_ascii=False))
