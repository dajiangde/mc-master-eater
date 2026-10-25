import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'skills/mcd-hidden-explorer/scripts/numbered_catalog.py'
spec = importlib.util.spec_from_file_location('numbered_catalog', SCRIPT)
nc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nc)


class NumberedCatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source, self.policy, self.db = [self.root / x for x in ['source.json', 'roles.json', 'numbers.sqlite']]
        def row(ident, name, codes):
            return {'id': ident, 'title': name,
                    'products': [{'name': title, 'code': code, 'time': '12:00', 'evidence': 'historical.json'}
                                 for code, title in codes], 'image_ids': [], 'source_ids': [], 'tested_by_project': False}
        self.data = {'entries': [row('U11', '玉米冰淇淋', [('corn', '玉米杯'), ('ice', '麦旋风'), ('fries', '薯条')]),
                                 row('U12', '鸡翅去骨', [('wing', '鸡翅')]),
                                 row('U06', '派冰品', [('pie1', '派一'), ('pie2', '派二'), ('ice', '麦旋风')])],
                     'images': [], 'sources': []}
        self.source.write_text(json.dumps(self.data), encoding='utf8')
        self.policy.write_text(json.dumps({'recipes': {'U11': {'optional_codes': ['fries']},
                'U06': {'choice_groups': [{'name': '派二选一', 'codes': ['pie1', 'pie2']}]}}}), encoding='utf8')
        nc.sync_database(self.source, self.db, self.policy)

    def test_multi_selection_and_required_products(self):
        answer = nc.resolve(self.db, '我要11号、12号')
        self.assertEqual(answer['selection_ids'], ['U11', 'U12'])
        self.assertEqual([x['name'] for x in answer['methods'][0]['required_products']], ['玉米杯', '麦旋风'])
        self.assertEqual(answer['methods'][0]['optional_products'][0]['name'], '薯条')
        self.assertEqual(answer['methods'][1]['required_products'][0]['name'], '鸡翅')
        self.assertFalse(answer['methods'][0]['required_products'][0]['current_store_verified'])
        self.assertIsNone(answer['methods'][0]['required_products'][0]['quantity'])

    def test_normalization_dedup_preserves_order(self):
        self.assertEqual(nc.parse_selection('我选１２号、U011、十一号'), ['U12', 'U11'])
        self.assertEqual(nc.parse_selection('11、12号'), ['U11', 'U12'])

    def test_unknown_is_atomic_not_partial(self):
        with self.assertRaisesRegex(ValueError, 'U99'):
            nc.resolve(self.db, '11号、99号')

    def test_ordinal_quantities_ranges_rejected(self):
        for text in ['第二个', '11号两份', '11-12号', '11号不要12号', '0号', '11号、', '十一一号']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                nc.resolve(self.db, text)

    def test_choices_not_all_required(self):
        result = nc.resolve(self.db, '6号')['methods'][0]
        self.assertEqual([p['name'] for p in result['required_products']], ['麦旋风'])
        self.assertEqual(result['product_choices'][0]['choose'], 1)
        self.assertEqual(len(result['product_choices'][0]['options']), 2)

    def test_reorder_does_not_renumber_and_missing_reserved(self):
        self.data['entries'].reverse()
        self.source.write_text(json.dumps(self.data), encoding='utf8')
        nc.sync_database(self.source, self.db, self.policy)
        self.assertEqual(nc.resolve(self.db, '11')['methods'][0]['name'], '玉米冰淇淋')
        self.data['entries'] = [r for r in self.data['entries'] if r['id'] != 'U12']
        self.source.write_text(json.dumps(self.data), encoding='utf8')
        nc.sync_database(self.source, self.db, self.policy)
        with self.assertRaises(ValueError): nc.resolve(self.db, '12号')
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT number,active FROM recipes WHERE id='U12'").fetchone(), (12, 0))

    def test_number_cannot_be_reused_by_different_id(self):
        self.data['entries'][0]['id'] = 'U011'
        self.source.write_text(json.dumps(self.data), encoding='utf8')
        self.policy.write_text('{"recipes":{}}', encoding='utf8')
        with self.assertRaisesRegex(ValueError, '永久占用'):
            nc.sync_database(self.source, self.db, self.policy)
        self.assertEqual(nc.resolve(self.db, '11')['selection_ids'], ['U11'])

    def test_invalid_roles_do_not_mutate_existing_database(self):
        before = self.db.read_bytes()
        self.policy.write_text('{"recipes":{"U11":{"optional_codes":["unknown"]}}}', encoding='utf8')
        with self.assertRaises(ValueError): nc.sync_database(self.source, self.db, self.policy)
        self.assertEqual(before, self.db.read_bytes())

    def test_readonly_select_no_writes(self):
        before = self.db.read_bytes()
        nc.resolve(self.db, '11号、12号')
        self.assertEqual(before, self.db.read_bytes())


if __name__ == '__main__':
    unittest.main()
