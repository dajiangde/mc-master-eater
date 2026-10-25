"""CLI contract tests use synthetic research data, never private recipes or photos."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT / 'skills/mcd-hidden-explorer/scripts/research.py'
PUBLIC = PROJECT / 'skills/mcd-hidden-explorer/references/catalog.json'
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jvO0AAAAASUVORK5CYII=')


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'images').mkdir()
        (self.root / 'images/sample.png').write_bytes(PNG)
        self.source = self.root / 'mapping.json'
        self.photo = dict(image_id='P01', path='images/sample.png', sha256=hashlib.sha256(PNG).hexdigest(),
                          record_id='R01', image_source_url='https://example.com/photo', rights='未确认公开使用',
                          photo_verification_status='待核', image_kind='过程图', creator='fixture-author')
        self.row = dict(record_id='R01', dish_name='合成测试组合', evidence_status='reported_recipe',
                        needed_products_as_reported=['薯饼（来源称谓）', '冰品（份量不明）'],
                        method_as_reported='来源给出的组装方法', quantity_evidence='买两份，实际用量未给',
                        image_ids=['P01'], recipe_sources=[dict(url='https://example.com/recipe', title='fixture')],
                        product_name_mappings=[dict(source_name='薯饼（来源称谓）', mainland_display_name='脆薯饼',
                                                    mainland_canonical_name='脆薯饼', mapping_status='name_verified')],
                        collection_status='needs_evidence', eligible_for_actionable_pool=False,
                        blocking_gaps=['实拍待核', '非时令待核'], recipe_pending_items=['用量待核'],
                        menu_verification=dict(status='main_found', queried_at='historical-fixture-time', stock_confirmed=False),
                        nonseasonal_verification=dict(status='unknown'), future_evidence={'keep': ['unchanged']})
        self.cover = dict(record_id='X01', dish_name='待识别：合成线索', evidence_status='cover_only',
                          needed_products_as_reported=[], method_as_reported=None, quantity_evidence=None,
                          image_ids=[], recipe_sources=[dict(url='https://example.com/cover')],
                          eligible_for_actionable_pool=False, collection_status='lead')
        self.data = dict(schema_version=3, scope='synthetic local research', entries=[self.row, self.cover], images=[self.photo])
        self.save()

    def save(self):
        self.source.write_text(json.dumps(self.data, ensure_ascii=False), encoding='utf-8')

    def run_cli(self, *args, code=0, source=None, script=SCRIPT, cwd=None):
        result = subprocess.run([sys.executable, '-B', str(script), '--source', str(source or self.source), *map(str, args)],
                                capture_output=True, text=True, cwd=cwd)
        self.assertEqual(result.returncode, code, result.stderr)
        return json.loads(result.stdout) if code == 0 else result.stderr

    def test_research_list_and_validation(self):
        result = self.run_cli('list')
        self.assertEqual(result['mode'], 'local_research')
        self.assertEqual(result['count'], 2)
        check = self.run_cli('validate')
        self.assertEqual((check['count'], check['images'], check['actionable_count']), (2, 1, 0))

    def test_lookup_preserves_all_original_evidence_without_promotion(self):
        result = self.run_cli('lookup', ' r01 ')
        self.assertEqual(result['entry']['research_evidence'], self.row)
        self.assertEqual(result['entry']['quantity_evidence'], self.row['quantity_evidence'])
        self.assertEqual(result['entry']['associated_meals'][0]['name'], '脆薯饼')
        self.assertNotIn('quantity', result['entry']['associated_meals'][0])
        self.assertFalse(result['entry']['eligible_for_actionable_pool'])
        self.assertEqual(result['next_action'], 'review_research_evidence')
        self.assertEqual(result['entry']['sources'], self.row['recipe_sources'])

    def test_image_metadata_and_local_absolute_path(self):
        photo = self.run_cli('lookup', 'R01')['entry']['images'][0]
        for key, value in self.photo.items():
            self.assertEqual(photo[key], value)
        self.assertEqual(photo['absolute_path'], str((self.root / 'images/sample.png').resolve()))
        self.assertEqual(photo['mime_type'], 'image/png')

    def test_search_uses_display_names_and_source_terms(self):
        self.assertEqual(self.run_cli('search', '脆薯饼')['entries'][0]['id'], 'R01')
        self.assertEqual(self.run_cli('search', '薯饼（来源称谓）')['count'], 1)
        self.assertEqual(self.run_cli('search', '薯饼 冰品')['count'], 1)
        self.assertEqual(self.run_cli('search', '不存在的商品')['count'], 0)
        self.run_cli('search', '  ', code=2)

    def test_cover_lead_does_not_acquire_recipe(self):
        row = self.run_cli('lookup', 'X01')['entry']
        self.assertEqual(row['associated_meals'], [])
        self.assertIsNone(row['method_as_reported'])
        self.assertFalse(row['eligible_for_actionable_pool'])
        self.cover['method_as_reported'] = 'invented method'
        self.save()
        self.assertIn('Cover-only', self.run_cli('validate', code=2))

    def test_batch_selection_and_dataset_binding(self):
        batch = self.root / 'batch.json'
        self.run_cli('batch', 'X01', 'R01', '--output', batch)
        result = self.run_cli('lookup', '第二个', '--batch', batch)
        self.assertEqual(result['canonical_id'], 'R01')
        self.assertEqual(result['batch_position'], 2)
        self.run_cli('lookup', '第一个', code=2)
        self.run_cli('lookup', '第三个', '--batch', batch, code=2)
        self.row['dish_name'] = 'changed batch dataset'
        self.save()
        self.assertIn('stale', self.run_cli('lookup', '第二个', '--batch', batch, code=2))

    def test_public_or_malformed_batch_is_rejected(self):
        batch = self.root / 'public-batch.json'
        batch.write_text(json.dumps(dict(ids=['R01'])))
        self.assertIn('Wrong-mode', self.run_cli('lookup', '第一个', '--batch', batch, code=2))

    def test_existing_batch_is_not_overwritten(self):
        batch = self.root / 'batch.json'
        batch.write_text('keep-me')
        self.run_cli('batch', 'R01', '--output', batch, code=2)
        self.assertEqual(batch.read_text(), 'keep-me')
        self.run_cli('batch', 'R01', 'R01', '--output', self.root / 'new.json', code=2)

    def test_missing_or_public_source_never_falls_back(self):
        self.assertIn('No fallback', self.run_cli('list', source=self.root / 'missing.json', code=2))
        public = self.root / 'public.json'
        public.write_text(json.dumps(dict(schema_version=1, entries=[])))
        self.assertIn('schema 3', self.run_cli('list', source=public, code=2))

    def test_source_and_public_catalog_remain_byte_identical(self):
        original = self.source.read_bytes()
        public = PUBLIC.read_bytes()
        for command in [('validate',), ('list',), ('search', '薯饼'), ('lookup', 'R01')]:
            self.run_cli(*command)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(PUBLIC.read_bytes(), public)

    def test_image_integrity_and_association_failures(self):
        original = copy.deepcopy(self.data)
        cases = [
            ('path', '../outside.png'), ('path', '/tmp/outside.png'),
            ('path', 'images/missing.png'), ('sha256', '0' * 64),
            ('record_id', 'R99'), ('record_id', 'X01'),
        ]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                self.data = copy.deepcopy(original)
                self.data['images'][0][key] = value
                self.save()
                self.run_cli('validate', code=2)

    def test_image_symlink_escape_is_rejected(self):
        outside = self.root / 'outside.png'
        outside.write_bytes(PNG)
        link = self.root / 'images/link.png'
        link.symlink_to(outside)
        self.photo['path'] = 'images/link.png'
        self.save()
        self.run_cli('validate', code=2)

    def test_duplicate_and_dangling_ids_rejected(self):
        self.data['entries'].append(copy.deepcopy(self.row))
        self.save()
        self.run_cli('validate', code=2)
        self.data['entries'].pop()
        self.row['image_ids'] = ['missing-image']
        self.save()
        self.run_cli('validate', code=2)

    def test_relocated_helper_and_source(self):
        relocated = self.root / 'elsewhere/scripts'
        relocated.mkdir(parents=True)
        shutil.copy2(SCRIPT, relocated / 'research.py')
        shutil.copy2(SCRIPT.parent / 'explore.py', relocated / 'explore.py')
        result = self.run_cli('lookup', '合成测试组合', script=relocated / 'research.py', cwd='/')
        self.assertEqual(result['canonical_id'], 'R01')


if __name__ == '__main__':
    unittest.main()
