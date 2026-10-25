#!/usr/bin/env python3
"""Offline confirmation binding. Never calls MCP or establishes human consent."""
from copy import deepcopy
import hashlib
import json

ALIASES = {
    'store_code': ('store_code', 'storeCode'),
    'order_type': ('order_type', 'orderType'),
    'be_type': ('be_type', 'beType'),
    'take_way_code': ('take_way_code', 'takeWayCode', 'take_way', 'takeWay'),
    'be_code': ('be_code', 'beCode'),
    'price_cents': ('price_cents', 'total_cents', 'totalCents', 'price'),
    'price_checked_at': ('price_checked_at', 'priceCheckedAt'),
    'items': ('items', 'productList'),
}
CONTEXT = {'store_code': 'storeCode', 'order_type': 'orderType',
           'be_type': 'beType', 'be_code': 'beCode'}
DISPLAY_FIELDS = {'name', 'display_name', 'nutrition_name', 'productName', 'product_name'}


def positive_int(value):
    return type(value) is int and value > 0


def item_config(raw):
    """Remove display labels only; preserve every unknown configuration field."""
    item = deepcopy(raw)
    if not isinstance(item, dict):
        raise ValueError('商品配置必须是对象')
    if 'product_code' in item:
        if 'productCode' in item and item['productCode'] != item['product_code']:
            raise ValueError('商品编码字段冲突')
        item['productCode'] = item.pop('product_code')
    return {k: v for k, v in item.items() if k not in DISPLAY_FIELDS}


def normalize(summary):
    out = deepcopy(summary)
    for key, aliases in ALIASES.items():
        present = [out[a] for a in aliases if out.get(a) is not None]
        if present and any(v != present[0] for v in present):
            raise ValueError('摘要字段冲突：' + key)
        if present:
            out[key] = present[0]
    return out


def prepare(summary):
    """Fill absent fields from the saved actual calculate-price request."""
    out = normalize(summary)
    request = out.get('price_request')
    if isinstance(request, dict):
        for target, key in CONTEXT.items():
            if target not in out and request.get(key) is not None:
                out[target] = deepcopy(request[key])
        if 'items' not in out and 'items' in request:
            out['items'] = deepcopy(request['items'])
        if 'coupon' not in out:
            out['coupon'] = deepcopy(request.get('coupon'))
        if 'take_way_code' not in out and request.get('takeWayCode'):
            out['take_way_code'] = request['takeWayCode']
    return out


def snapshot(summary):
    data = prepare(summary)
    keys = ['price_request', 'store_code', 'order_type', 'be_type', 'be_code',
            'store_name', 'take_way_code', 'time', 'coupon', 'price_cents',
            'original_cents', 'discount_cents', 'price_checked_at', 'methods', 'calories']
    result = {k: deepcopy(data.get(k)) for k in keys}
    result['items'] = [item_config(i) for i in data.get('items') or []]
    return result


def fingerprint(summary):
    value = json.dumps(snapshot(summary), sort_keys=True, ensure_ascii=False,
                       separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(value.encode('utf8')).hexdigest()


def configuration_blockers(summary):
    try:
        data = prepare(summary)
    except (ValueError, TypeError) as exc:
        return [str(exc)]
    errors = []
    if not data.get('store_code'):
        errors.append('缺少门店编码')
    if data.get('order_type') not in (1, 2) or type(data.get('order_type')) is not int:
        errors.append('缺少有效订单类型')
    if data.get('be_type') is None:
        errors.append('缺少业务类型 beType，需按本轮 MCP 参数补齐')
    if data.get('order_type') == 1 and not data.get('take_way_code'):
        errors.append('到店订单缺少取餐方式编码，需重新核价取得')
    if data.get('order_type') == 2 and not data.get('be_code'):
        errors.append('外送订单缺少业务编码')
    if not str(data.get('price_checked_at') or '').strip():
        errors.append('缺少价格核实时间，需先调用价格试算')
    if type(data.get('price_cents')) is not int or data['price_cents'] < 0:
        errors.append('缺少有效试算总价，需先调用官方核价（单位分）')
    items = data.get('items')
    if not isinstance(items, list) or not items:
        errors.append('缺少商品清单')
    else:
        for item in items:
            if not isinstance(item, dict):
                errors.append('商品条目不是对象')
                continue
            if not (item.get('productCode') or item.get('product_code')):
                errors.append('存在缺少商品编码的条目')
            if not positive_int(item.get('quantity')):
                errors.append('存在数量无效的条目')
            if 'roundList' in item:
                rounds = item['roundList']
                if not isinstance(rounds, list) or not rounds:
                    errors.append('口味轮次配置无效')
                else:
                    for group in rounds:
                        if not isinstance(group, dict) or not group.get('round') or not isinstance(group.get('comboItemList'), list) or not group['comboItemList']:
                            errors.append('口味轮次配置不完整')
                            continue
                        if any(not isinstance(c, dict) or not c.get('code') or not positive_int(c.get('quantity')) for c in group['comboItemList']):
                            errors.append('口味子项编码或数量无效')
    request = data.get('price_request')
    if not isinstance(request, dict) or not request.get('items'):
        errors.append('缺少完整官方核价请求 price_request，不能用展示清单代替')
    else:
        for target, key in CONTEXT.items():
            if data.get(target) != request.get(key):
                errors.append('摘要与核价请求不一致：' + key)
        if request.get('takeWayCode') is not None and data.get('take_way_code') != request['takeWayCode']:
            errors.append('取餐方式与核价请求不一致，需重新核价')
        if data.get('coupon') != request.get('coupon'):
            errors.append('优惠券与核价请求不一致，需重新核价')
        try:
            if [item_config(i) for i in items or []] != [item_config(i) for i in request['items']]:
                errors.append('商品、数量、口味或特调与核价请求不一致，需重新核价')
        except (ValueError, TypeError) as exc:
            errors.append(str(exc))
    return list(dict.fromkeys(errors))


def order_blockers(summary, confirmed=False, confirmation_fingerprint=None, order_request=None):
    errors = configuration_blockers(summary)
    if not confirmed:
        errors.append('尚未得到用户对这份订单摘要的明确确认')
    try:
        digest = fingerprint(summary)
        if summary.get('confirmation_fingerprint') != digest:
            errors.append('确认摘要已改变或未生成，需重新生成并展示最新摘要')
        if confirmed and confirmation_fingerprint != digest:
            errors.append('用户确认版本与最新摘要不一致，需重新确认')
        if confirmed:
            if not isinstance(order_request, dict):
                errors.append('缺少待提交的完整订单参数 order_request')
            else:
                data = prepare(summary)
                expected = deepcopy(data.get('price_request') or {})
                if data.get('take_way_code'):
                    expected['takeWayCode'] = data['take_way_code']
                # Only display labels are excluded; unknown nested fields remain bound.
                actual = deepcopy(order_request)
                expected['items'] = [item_config(i) for i in expected.get('items') or []]
                actual['items'] = [item_config(i) for i in actual.get('items') or []]
                if expected != actual:
                    errors.append('待提交订单参数与已确认核价配置不一致，禁止下单')
    except (ValueError, TypeError, KeyError) as exc:
        errors.append('确认摘要无效：' + str(exc))
    return list(dict.fromkeys(errors))
