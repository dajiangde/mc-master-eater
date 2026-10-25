"""Synthetic-only contribution -> processed images -> clean installed Skill tests."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills/mcd-hidden-explorer'
sys.path.insert(0, str(SKILL / 'scripts'))
import content_pipeline as cp
import numbered_catalog as nc
import basket


def png(path, size, colour=40):
    """A genuine synthetic PNG, no private photos or copyrighted fixtures."""
    def chunk(kind, payload):
        return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload))
    width, height = size
    payload = zlib.compress((b'\x00' + bytes([colour]) * width) * height)
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 0, 0, 0, 0)) +
                     chunk(b'IDAT', payload) + chunk(b'IEND', b''))


def submission(key='synthetic-one'):
    return {'schema_version': 1, 'key': key, 'title': '合成测试配方 ' + key, 'category': '测试',
            'products': [{'name': '合成餐品甲', 'code': 'SYNTHETIC-A', 'time': '合成测试', 'evidence': '合成测试，非真实商品'}],
            'configuration': {'optional_codes': [], 'choice_groups': [], 'purchase_quantities': {
                'SYNTHETIC-A': {'quantity': 2, 'status': 'purchase_suggestion', 'basis': '合成测试建议，未试做'}}},
            'steps': ['合成测试步骤'], 'step_basis': 'project_suggestion', 'tested_by_project': False,
            'optional': '', 'differences': '仅用于测试，不能发布为真实吃法',
            'sources': [{'url': 'https://example.invalid/synthetic', 'author': '测试夹具', 'published_at': None,
                         'captured_at': '2026-10-25', 'region': '合成环境', 'read_status': '合成资料'}],
            'menu_scope': {'store_code': 'SYNTHETIC', 'channel': '离线测试', 'checked_at': '2026-10-25', 'serving_time': '合成时段'},
            'image': {'kind': 'finished', 'author': '测试夹具', 'source_url': 'https://example.invalid/synthetic',
                      'published_at': None, 'captured_at': '2026-10-25', 'region': '合成环境',
                      'photo_evidence': '仅合成测试图片，非餐品实拍', 'rights': {'status': 'owned', 'basis': '代码生成的测试像素'}},
            'display': {'products': ['合成餐品甲'], 'steps': ['合成测试步骤']}}


class ContentPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.content = self.root / 'content'; self.content.mkdir()
        shutil.copyfile(SKILL / 'content/catalog.json', self.content / 'catalog.json')
        # Independent from a maintainer's future real additions.
        cp.write(self.content / 'catalog.json', {'schema_version': 1, 'reserved_through': 23,
            'retired': [{'id': 'U12', 'number': 12, 'title': '旧版', 'note': '已停用'}], 'recipes': []})
        self.card = self.root / 'card.png'; self.thumb = self.root / 'thumb.png'
        png(self.card, (1080, 1440)); png(self.thumb, (360, 480))
        self.row = submission()

    def add(self, row=None):
        return cp.add(self.content, row or self.row, None, 'synthetic-reviewer', card=self.card, thumbnail=self.thumb)

    def build(self):
        output = self.root / 'built'; archive = self.root / 'skill.zip'
        cp.bundle(self.content, SKILL, output, archive)
        return output, archive

    def test_empty_catalogue_valid_but_never_ships_empty_skill(self):
        self.assertEqual(cp.validate_catalog(self.content)['recipes'], [])
        with self.assertRaisesRegex(ValueError, '暂无'):
            self.build()

    def test_local_add_reserves_old_numbers_and_preserves_evidence(self):
        self.assertEqual(self.add()['id'], 'U24')
        data = cp.validate_catalog(self.content)
        self.assertEqual(data['recipes'][0]['configuration']['purchase_quantities']['SYNTHETIC-A']['quantity'], 2)
        self.assertEqual(data['recipes'][0]['sources'], self.row['sources'])
        self.assertEqual(data['retired'][0]['number'], 12)

    def test_issue_and_local_use_same_schema_and_importer(self):
        extra = {k: v for k, v in self.row.items() if k not in ('key', 'schema_version')}
        issue = {'number': 109, 'body': '### 吃法名称\n\n投稿测试\n\n### 维护者配置（可留空）\n\n```json\n' +
                 json.dumps(extra, ensure_ascii=False) + '\n```'}
        prepared = cp.issue_submission(issue)
        cp.validate_submission(prepared)
        result = self.add(prepared)
        self.assertEqual(result['key'], 'issue-109'); self.assertEqual(result['id'], 'U24')
        self.assertNotIn('photo_url', cp.read(self.content / 'catalog.json')['recipes'][0])

    def test_ordinary_issue_stays_pending_until_product_mapping_reviewed(self):
        draft = cp.issue_submission({'number': 1, 'body': '### 吃法名称\n\n待审图文\n\n### 做法\n\n未知'})
        self.assertNotIn('id', draft)
        with self.assertRaises(ValueError):
            self.add(draft)
        self.assertEqual(cp.read(self.content / 'catalog.json')['recipes'], [])

    def test_rights_unknown_rejected_before_writing_any_asset(self):
        self.row['image']['rights']['status'] = 'unknown'
        with self.assertRaisesRegex(ValueError, '公开使用依据'):
            self.add()
        self.assertFalse((self.content / 'cards').exists())

    def test_cover_only_cannot_be_used_as_finished_photo(self):
        self.row['image']['kind'] = 'cover_only'
        with self.assertRaisesRegex(ValueError, '实拍'):
            self.add()

    def test_signed_source_url_rejected(self):
        self.row['sources'][0]['url'] += '?xsec_token=private'
        with self.assertRaisesRegex(ValueError, '无签名'):
            self.add()

    def test_raw_payload_and_unknown_product_fields_rejected(self):
        self.row['products'][0]['cookie'] = 'never-ship'
        with self.assertRaisesRegex(ValueError, '未知字段'):
            self.add()

    def test_reference_menu_and_quantities_required(self):
        del self.row['configuration']['purchase_quantities']['SYNTHETIC-A']
        with self.assertRaisesRegex(ValueError, '购买份数'):
            self.add()

    def test_duplicate_issue_key_gets_no_second_number(self):
        self.add()
        with self.assertRaisesRegex(ValueError, '已收录'):
            self.add()
        self.assertEqual(len(cp.validate_catalog(self.content)['recipes']), 1)

    def test_duplicate_recipe_or_image_rolls_back_assets(self):
        self.add()
        row = deepcopy(self.row); row['key'] = 'new-key'
        with self.assertRaisesRegex(ValueError, '重复收录'):
            self.add(row)
        self.assertFalse((self.content / 'cards/U25.png').exists())
        cp.validate_catalog(self.content)

    def test_corrupt_or_missing_image_blocks_bundle(self):
        self.add(); (self.content / 'cards/U24.png').write_bytes(b'broken')
        with self.assertRaises(ValueError):
            self.build()
        self.assertFalse((self.root / 'built').exists())

    def test_image_traversal_and_symlink_rejected(self):
        self.add(); data = cp.read(self.content / 'catalog.json')
        data['recipes'][0]['card']['path'] = '../card.png'; cp.write(self.content / 'catalog.json', data)
        with self.assertRaisesRegex(ValueError, '路径'):
            cp.validate_catalog(self.content)

    def test_withdrawn_number_cannot_be_reused_or_disappear(self):
        self.add(); baseline = self.root / 'baseline.json'
        shutil.copyfile(self.content / 'catalog.json', baseline)
        data = cp.read(baseline); data['recipes'] = []; cp.write(self.content / 'catalog.json', data)
        shutil.rmtree(self.content / 'cards'); shutil.rmtree(self.content / 'thumbnails')
        with self.assertRaisesRegex(ValueError, '删除或重分配'):
            cp.validate_catalog(self.content, baseline)

    def test_retired_history_cannot_disappear(self):
        baseline = self.root / 'baseline.json'; shutil.copyfile(self.content / 'catalog.json', baseline)
        data = cp.read(baseline); data['retired'] = []; cp.write(self.content / 'catalog.json', data)
        with self.assertRaisesRegex(ValueError, '停用编号'):
            cp.validate_catalog(self.content, baseline)

    def test_build_and_unzip_load_actual_installed_modules_and_images(self):
        self.add(); output, archive = self.build()
        relocated = self.root / 'another machine'
        with zipfile.ZipFile(archive) as z:
            self.assertTrue(all(name.startswith(cp.skill_name(SKILL) + '/') for name in z.namelist()))
            self.assertFalse(any('/content/' in name or '/submissions/' in name or 'source-images' in name for name in z.namelist()))
            z.extractall(relocated)
        installed = relocated / cp.skill_name(SKILL)
        result = subprocess.run([sys.executable, str(installed / 'scripts/bundle_smoke.py'), '--bundle', str(installed)],
                                capture_output=True, text=True, cwd=relocated)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['active_count'], 1)
        self.assertFalse((installed / 'references/local-bundle.json').exists())
        serialized = b''.join(p.read_bytes() for p in installed.rglob('*') if p.is_file() and p.suffix in ('.sqlite3', '.json'))
        self.assertNotIn(str(self.root).encode(), serialized)

    def test_manifest_detects_missing_and_extra_assets(self):
        self.add(); output, _ = self.build()
        (output / 'data/unified-v2/cards/U24.png').unlink()
        with self.assertRaisesRegex(ValueError, '文件清单'):
            cp.verify_bundle(output)

    def test_manifest_detects_wrong_bytes(self):
        self.add(); output, _ = self.build()
        (output / 'references/product-aliases.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, '哈希'):
            cp.verify_bundle(output)

    def test_parent_option_and_purchase_quantity_survive_compilation(self):
        self.row['products'] = [{'name': '合成口味甲', 'code': 'OPTION-A', 'parent_code': 'PARENT',
              'parent_name': '合成父商品', 'time': '合成时段', 'evidence': '仅测试'},
              {'name': '合成口味乙', 'code': 'OPTION-B', 'parent_code': 'PARENT',
              'parent_name': '合成父商品', 'time': '合成时段', 'evidence': '仅测试'}]
        self.row['configuration'] = {'choice_groups': [{'name': '合成口味', 'codes': ['OPTION-A', 'OPTION-B'], 'default_code': 'OPTION-A'}],
              'purchase_quantities': {code: {'quantity': 2, 'status': 'source_reported', 'basis': '合成测试'} for code in ['OPTION-A', 'OPTION-B']}}
        self.add(); output, _ = self.build()
        database = output / 'data/unified-v2/隐藏吃法编号.sqlite3'
        methods = nc.resolve(database, '24')['methods']
        payload = basket.build_price_items(basket.build_purchase_plan(methods))
        self.assertEqual(payload['items'][0]['productCode'], 'PARENT')
        self.assertEqual(payload['items'][0]['quantity'], 2)
        self.assertEqual(payload['items'][0]['roundList'][0]['comboItemList'][0]['code'], 'OPTION-A')
        self.assertEqual(payload['items'][0]['roundList'][0]['comboItemList'][0]['quantity'], 1)

    def test_parentless_choice_group_rejected(self):
        self.row['products'] *= 2; self.row['products'][1] = {**self.row['products'][1], 'code': 'OPTION-B'}
        self.row['configuration']['choice_groups'] = [{'name': '口味', 'codes': ['SYNTHETIC-A', 'OPTION-B'], 'default_code': 'OPTION-B'}]
        self.row['configuration']['purchase_quantities']['OPTION-B'] = {'quantity': 1, 'status': 'purchase_suggestion', 'basis': '测试'}
        with self.assertRaisesRegex(ValueError, '父商品'):
            self.add()

    def test_existing_output_is_never_overwritten(self):
        self.add(); output, _ = self.build(); marker = output / 'keep'; marker.write_text('keep')
        with self.assertRaisesRegex(ValueError, '已存在'):
            cp.bundle(self.content, SKILL, output)
        self.assertEqual(marker.read_text(), 'keep')

    def test_download_never_accepts_arbitrary_hosts_or_signed_input(self):
        for url in ['http://127.0.0.1/private', 'https://example.com/p.png',
                    'https://github.com/user-attachments/assets/123?token=x']:
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, '附件地址'):
                cp.download_photo(url, self.root / 'never')
        self.assertFalse((self.root / 'never').exists())

    def test_local_concurrent_writer_is_rejected_without_overwrite(self):
        lock = self.content.parent / '.content.intake.lock'; lock.touch()
        with self.assertRaisesRegex(ValueError, '并发'):
            self.add()
        self.assertEqual(cp.read(self.content / 'catalog.json')['recipes'], [])

    def test_forged_png_with_only_header_is_rejected(self):
        self.card.write_bytes(b'\x89PNG\r\n\x1a\n' + struct.pack('>I',13) + b'IHDR' + struct.pack('>II',1080,1440))
        with self.assertRaisesRegex(ValueError, 'PNG'):
            self.add()

    def test_unregistered_original_cannot_enter_content_directory(self):
        (self.content / 'original.png').write_bytes(self.card.read_bytes())
        with self.assertRaisesRegex(ValueError, '原图'):
            cp.validate_catalog(self.content)

    @unittest.skipUnless(importlib.util.find_spec('PIL'), 'Pillow is a maintenance-only dependency')
    def test_real_renderer_reads_photo_but_only_registers_processed_pngs(self):
        raw = self.root / 'original.png'; png(raw, (800, 600), 90)
        answer = cp.add(self.content, self.row, raw, 'synthetic-reviewer')
        self.assertEqual(answer['id'], 'U24')
        cp.validate_catalog(self.content)
        self.assertNotEqual(cp.digest(raw), answer['card_sha256'])
        self.assertEqual({p.name for p in self.content.rglob('*.png')}, {'U24.png'})

    @unittest.skipUnless(importlib.util.find_spec('PIL'), 'Pillow is a maintenance-only dependency')
    def test_long_card_text_is_rejected_without_partial_import(self):
        self.row['display']['steps'] = ['长步骤' * 50] * 5
        with self.assertRaisesRegex(ValueError, '文字过长'):
            cp.add(self.content, self.row, self.card, 'synthetic-reviewer')
        self.assertEqual(cp.read(self.content / 'catalog.json')['recipes'], [])


if __name__ == '__main__':
    unittest.main()
