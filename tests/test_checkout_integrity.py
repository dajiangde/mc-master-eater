"""Financial configuration invariants; all quote fixtures are synthetic/offline."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/mcd-hidden-explorer/scripts'))
import basket
import checkout_contract as cc
import explore
import numbered_catalog as nc


def quote():
    request = {'storeCode': 'test-store', 'orderType': 1, 'beType': 1,
               'coupon': None, 'needTableware': False,
               'items': [{'productCode': 'parent', 'quantity': 2,
                 'roundList': [{'round': '1', 'comboItemList': [{'code': 'flavour', 'quantity': 1}]}],
                 'modifyList': [{'code': 'sauce', 'quantity': 0}]}]}
    return basket.build_confirmation({'price_request': request, 'take_way_code': 'take-in-store',
        'price_cents': 1000, 'price_checked_at': '2026-10-25T13:00:00+08:00',
        'methods': ['U06'], 'calories': {'label': '已知部分热量', 'complete': False}})


def request_for(summary):
    return {**deepcopy(summary['price_request']), 'takeWayCode': summary['take_way_code']}


def check(summary, token=None, request=None):
    return explore.order_confirmation_blockers(summary, True,
        token or summary['confirmation_fingerprint'], request if request is not None else request_for(summary))


class CheckoutIntegrityTests(unittest.TestCase):
    def test_full_configuration_survives_confirmation_and_normalization(self):
        summary = quote()
        self.assertEqual(summary['items'], summary['price_request']['items'])
        self.assertEqual(explore.normalize_summary(summary)['price_request'], summary['price_request'])
        self.assertFalse(summary['ready_for_order'])
        self.assertTrue(summary['ready_for_confirmation'])
        self.assertEqual(check(summary), [])

    def test_input_and_output_are_not_aliased(self):
        summary = quote()
        summary['items'][0]['roundList'][0]['comboItemList'][0]['code'] = 'other'
        self.assertEqual(summary['price_request']['items'][0]['roundList'][0]['comboItemList'][0]['code'], 'flavour')
        self.assertTrue(check(summary))

    def test_flag_alone_cannot_confirm(self):
        summary = quote()
        self.assertTrue(explore.order_confirmation_blockers(summary, True))
        self.assertTrue(explore.order_confirmation_blockers(summary, False,
            summary['confirmation_fingerprint'], request_for(summary)))

    def test_dropping_options_or_modifications_blocks_submission(self):
        summary = quote()
        for key in ('roundList', 'modifyList'):
            with self.subTest(key=key):
                request = request_for(summary)
                del request['items'][0][key]
                self.assertTrue(check(summary, request=request))

    def test_changed_order_fields_are_all_bound(self):
        summary = quote()
        for key, value in [('storeCode', 'other'), ('takeWayCode', 'eat-in'),
                           ('coupon', {'id': 'other'}), ('needTableware', True), ('beType', 2)]:
            with self.subTest(key=key):
                request = request_for(summary)
                request[key] = value
                self.assertTrue(check(summary, request=request))
        for key, value in [('quantity', 1), ('productCode', 'other')]:
            request = request_for(summary)
            request['items'][0][key] = value
            self.assertTrue(check(summary, request=request))

    def test_changed_summary_invalidates_old_confirmation(self):
        for key, value in [('price_cents', 999), ('take_way_code', 'eat-in'),
                           ('methods', ['U18']), ('calories', {'total_kcal': 900}),
                           ('price_checked_at', '2026-10-25T13:01:00+08:00')]:
            with self.subTest(key=key):
                summary = quote()
                summary[key] = value
                self.assertTrue(check(summary))

    def test_requote_needs_new_human_confirmation(self):
        old = quote()
        changed = deepcopy(old)
        changed['price_request']['items'][0]['quantity'] = 3
        changed['items'][0]['quantity'] = 3
        changed['price_cents'] = 1500
        changed['price_checked_at'] = '2026-10-25T13:02:00+08:00'
        new = basket.build_confirmation(changed)
        self.assertTrue(check(new, token=old['confirmation_fingerprint']))
        self.assertEqual(check(new), [])

    def test_old_flat_summary_cannot_become_ready(self):
        summary = basket.build_confirmation({'store_code': 'test', 'take_way': 'take-in-store',
            'items': [{'productCode': 'parent', 'quantity': 1}], 'price_cents': 1000,
            'price_checked_at': '2026-10-25 13:00'})
        self.assertFalse(summary['ready_for_confirmation'])
        self.assertTrue(any('price_request' in e for e in summary['blockers']))

    def test_invalid_quantities_and_amounts_rejected(self):
        for value in (True, 0, -1, 1.5, '2'):
            with self.subTest(value=value):
                summary = quote()
                summary['items'][0]['quantity'] = value
                summary['price_request']['items'][0]['quantity'] = value
                self.assertTrue(cc.configuration_blockers(summary))
                with self.assertRaises(ValueError):
                    basket.build_price_items([{'price_code': 'test', 'quantity': value}])
        for amount in (True, -1, 1.5, '1000'):
            summary = quote()
            summary['price_cents'] = amount
            self.assertTrue(cc.configuration_blockers(summary))

    def test_malformed_rounds_rejected(self):
        for rounds in ([], {}, [None], [{'round': '1', 'comboItemList': [{'code': 'x', 'quantity': 0}]}]):
            summary = quote()
            summary['price_request']['items'][0]['roundList'] = rounds
            summary['items'][0]['roundList'] = rounds
            self.assertTrue(cc.configuration_blockers(summary))

    def test_conflicting_aliases_are_rejected(self):
        summary = quote()
        summary['total_cents'] = 1
        self.assertTrue(check(summary))

    def test_human_display_labels_do_not_change_order_configuration(self):
        summary = quote()
        request = request_for(summary)
        request['items'][0]['productName'] = '测试商品'
        self.assertEqual(check(summary, request=request), [])

    def test_live_config_is_preserved_by_price_items(self):
        item = quote()['items'][0]
        result = basket.build_price_items({'items': [{'quantity': 2, 'live_item': item}]})
        self.assertEqual(result['items'], [item])
        with self.assertRaises(ValueError):
            basket.build_price_items({'items': [{'quantity': 3, 'live_item': item}]})


class QuantityRuleTests(unittest.TestCase):
    def product(self, **kwargs):
        return {'name': '测试餐品', 'reference_menu': {'code': 'p'}, **kwargs}

    def plan(self, product, mid='U01'):
        return basket.build_purchase_plan([{'id': mid, 'required_products': [product]}])['items'][0]

    def test_reported_quantity_and_evidence_retained(self):
        item = self.plan(self.product(quantity=2, quantity_evidence='合成测试：两片'))
        self.assertEqual(item['quantity'], 2)
        self.assertFalse(item['quantity_needs_confirmation'])
        self.assertEqual(item['quantity_basis'][0]['basis'], '合成测试：两片')

    def test_purchase_suggestion_is_not_promoted_to_reported_quantity(self):
        item = self.plan(self.product(purchase_quantity_suggestion=2))
        self.assertEqual(item['quantity'], 2)
        self.assertTrue(item['quantity_needs_confirmation'])
        self.assertEqual(item['quantity_basis'][0]['status'], 'purchase_suggestion')

    def test_unknown_quantity_is_explicit_suggestion(self):
        item = self.plan(self.product())
        self.assertEqual(item['quantity'], 1)
        self.assertTrue(item['quantity_needs_confirmation'])
        self.assertEqual(item['quantity_basis'][0]['status'], 'needs_confirmation')

    def test_shared_quantities_add_and_keep_both_bases(self):
        methods = [{'id': mid, 'required_products': [self.product(purchase_quantity_suggestion=q)]}
                   for mid, q in [('U01', 2), ('U04', 2)]]
        item = basket.build_purchase_plan(methods)['items'][0]
        self.assertEqual(item['quantity'], 4)
        self.assertEqual(len(item['quantity_basis']), 2)
        self.assertTrue(item['quantity_needs_confirmation'])
        self.assertEqual(basket.compute_calories([item], {'测试餐品': 100})['total_kcal'], 400)

    def test_rule_roundtrip_through_database_without_claiming_source_quantity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, policy, db = [root / x for x in ('source.json', 'policy.json', 'catalog.sqlite')]
            source.write_text(json.dumps({'entries': [{'id': 'U01', 'title': '测试组合',
                'products': [{'name': '测试餐品', 'code': 'p'}], 'image_ids': [], 'source_ids': []}],
                'images': [], 'sources': []}), encoding='utf8')
            rule = {'quantity': 2, 'status': 'source_reported', 'basis': '合成来源：两片'}
            roles = {'recipes': {'U01': {'purchase_quantities': {'p': rule}}}}
            policy.write_text(json.dumps(roles), encoding='utf8')
            nc.sync_database(source, db, policy)
            method = nc.resolve(db, '1')['methods'][0]
            self.assertIsNone(method['required_products'][0]['quantity'])
            self.assertFalse(method['required_products'][0]['current_store_verified'])
            self.assertEqual(basket.build_purchase_plan([method])['items'][0]['quantity'], 2)
            roles['recipes']['U01']['purchase_quantities']['p']['quantity'] = True
            with self.assertRaises(ValueError):
                nc.validate_source(json.loads(source.read_text()), roles)


if __name__ == '__main__':
    unittest.main()
