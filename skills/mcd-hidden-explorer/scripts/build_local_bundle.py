#!/usr/bin/env python3
"""Build a portable LOCAL-only Skill with a numbered DB and verified PNG cards.

This never installs, publishes, downloads, or copies host configuration.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import zipfile


def require(ok, message):
    if not ok:
        raise ValueError(message)


def build(skill, database, card_catalog, output):
    skill, database, card_catalog, output = [Path(x).resolve() for x in (skill, database, card_catalog, output)]
    require(not output.exists(), '输出目录已存在，拒绝覆盖')
    require((skill / 'SKILL.md').is_file(), '缺少Skill入口')
    require(database.is_file() and card_catalog.is_file(), '缺少编号库或卡片资料')
    data = json.loads(card_catalog.read_text(encoding='utf8'))
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as conn:
        active = {r[0] for r in conn.execute('SELECT id FROM recipes WHERE active=1')}
        policy_row = conn.execute("SELECT value FROM meta WHERE key='policy_sha256'").fetchone()
        policy_hash = policy_row[0] if policy_row else None
        source_hash = conn.execute("SELECT value FROM meta WHERE key='source_sha256'").fetchone()[0]
        require(source_hash == data.get('source_catalog_sha256'), '卡片与编号库不是同一版本')
    entries = data['entries']
    require(len(entries) == len(active) and {e['id'] for e in entries} == active, '卡片与启用编号不完全对应')
    for e in entries:
        relative = Path(e['card'])
        source = (card_catalog.parent / relative).resolve()
        require(not relative.is_absolute() and source.is_relative_to(card_catalog.parent), '卡片路径越界')
        require(relative.name == e['id'] + '.png', '卡片文件名与编号不一致')
        require(source.is_file() and hashlib.sha256(source.read_bytes()).hexdigest() == e['card_sha256'],
                '图片缺失或哈希不符：' + e['id'])
    output.mkdir(parents=True)
    shutil.copy2(skill / 'SKILL.md', output / 'SKILL.md')
    for directory in ['scripts', 'references']:
        shutil.copytree(skill / directory, output / directory,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'private', '.private'))
    target_db = output / 'data/unified-v2/隐藏吃法编号.sqlite3'
    target_db.parent.mkdir(parents=True)
    # Plain file copy: sqlite's backup API needs a temp dir, which some sandboxes block.
    shutil.copy2(database, target_db)
    with sqlite3.connect(target_db.as_uri() + '?mode=ro', uri=True) as check:
        require(check.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', '编号库复制后校验失败')
    target = output / 'data/base-cards-v1'
    (target / 'cards').mkdir(parents=True)
    manifest = {k: data[k] for k in ['schema_version', 'style', 'source_catalog_sha256', 'retired_entries'] if k in data}
    manifest['entries'] = []
    for e in entries:
        shutil.copy2(card_catalog.parent / e['card'], target / e['card'])
        manifest['entries'].append({k:e[k] for k in ['id','title','source_title','card','card_sha256',
             'display_products','display_steps','display_note','source_ids','image_source_ids','rights'] if k in e})
    (target / 'catalog.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    info = {'schema_version': 1, 'mode':'local_research_bundle', 'public_release':False,
            'database':'data/unified-v2/隐藏吃法编号.sqlite3', 'card_catalog':'data/base-cards-v1/catalog.json',
            'active_count':len(active), 'source_catalog_sha256':source_hash,
            'policy_sha256':policy_hash,
            'rights':'第三方图片权利未核，仅授权用户本地测试；不得直接公开发布。'}
    (output / 'references/local-bundle.json').write_text(json.dumps(info, ensure_ascii=False, indent=2) + '\n')
    files = {str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(output.rglob('*')) if p.is_file()}
    bundle_id = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    (output / 'bundle-manifest.json').write_text(json.dumps({'files':files, 'bundle_id':bundle_id, **info},ensure_ascii=False,indent=2)+'\n')
    info['bundle_id'] = bundle_id
    return info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ['skill','database','card-catalog','output']:
        parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--zip',type=Path)
    args=parser.parse_args()
    try:
        if args.zip:
            require(not args.zip.exists(), 'ZIP已存在，拒绝覆盖')
        result=build(args.skill,args.database,args.card_catalog,args.output)
        if args.zip:
            with zipfile.ZipFile(args.zip,'w',zipfile.ZIP_DEFLATED) as archive:
                for file in sorted(args.output.rglob('*')):
                    if file.is_file():archive.write(file,str(Path(args.output.name)/file.relative_to(args.output)))
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (ValueError,OSError,KeyError,TypeError,sqlite3.DatabaseError) as exc:
        print(json.dumps({'error':str(exc)},ensure_ascii=False));return 2
    return 0


if __name__=='__main__':
    raise SystemExit(main())
