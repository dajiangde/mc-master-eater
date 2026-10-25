#!/usr/bin/env python3
"""Exercise the runtime imported from a clean installed Skill, without real MCP."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import basket
import content_pipeline as cp
import discover
import numbered_catalog as nc
import session_state as ss


def check(root):
    root = Path(root).resolve()
    for module in (basket, discover, nc, ss):
        cp.require(Path(module.__file__).resolve().is_relative_to(root), '检查加载了源码而非安装副本')
    cp.verify_bundle(root)
    database = root / 'data/unified-v2/隐藏吃法编号.sqlite3'
    with sqlite3.connect(database) as conn:
        ids = [r[0] for r in conn.execute('SELECT id FROM recipes WHERE active=1 ORDER BY number')]
    with tempfile.TemporaryDirectory(prefix='mcd-installed-smoke-') as temporary:
        session = Path(temporary) / 'random.json'; ss.init_session(session)
        # Inspect the whole random pool once. Repeated user-sized batches can
        # repeat seen cards near exhaustion, making a finite coverage test flaky.
        result = discover.random_entry(database, session, limit=len(ids), seed=1)
        cp.require(result['inline_image_count'] == len(ids), '随机推荐缺图')
        cp.require({r['id'] for r in result['methods']} == set(ids), '新增吃法未进入随机推荐池')
        for ident in ids:
            methods = nc.resolve(database, ident)['methods']
            method = methods[0]
            product = (method['required_products'] or method['product_choices'][0]['options'])[0]
            by_product = nc.find_by_product(database, product['name'], limit=len(ids))
            cp.require(ident in [m['id'] for m in by_product['methods']], '新增吃法无法按餐品找到：' + ident)
            session = Path(temporary) / (ident + '.json'); ss.init_session(session)
            coupon = {'title': product['name'], 'products': [{'productName': product['name'],
                       'productCode': product['reference_menu']['parent_code'] or product['reference_menu']['code']}]}
            recommended = discover.coupon_entry(database, session, coupon, limit=len(ids))
            cp.require(ident in recommended['shown_ids'], '新增吃法未进入适用的优惠推荐：' + ident)
            cp.require(recommended['inline_image_count'] == len(recommended['shown_ids']), '优惠推荐缺图')
            selected = discover.select(database, session, [ident])
            cp.require(selected['inline_image_count'] == 1, '选号缺图')
            cp.require(discover.selection_view(database, session)['inline_image_count'] == 1, '当前清单缺图')
            plan = discover.plan_entry(database, session)
            cp.require(plan['items'], '选后购买清单为空')
            basket.build_price_items(plan)
            missing = basket.compute_calories(plan['items'], {})
            cp.require(missing['total_kcal'] is None and not missing['complete'], '缺失营养数据被当作0')
    return {'active_count': len(ids), 'checked': ['random', 'by-product', 'by-coupon', 'select',
            'selection', 'plan', 'price-items', 'missing-nutrition'], 'real_mcp_called': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.bundle), ensure_ascii=False))
