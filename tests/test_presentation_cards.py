import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('png_cards', ROOT/'skills/mcd-hidden-explorer/scripts/numbered_catalog.py')
nc=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(nc)


class PresentationCardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/'unified-v2').mkdir()
        self.db=self.root/'unified-v2/numbers.sqlite';self.source=self.root/'source.json';self.roles=self.root/'roles.json'
        rows=[{'id':'U11','title':'玉米冰淇淋','products':[{'name':'玉米杯','code':'corn'},{'name':'麦旋风','code':'ice'},{'name':'薯条','code':'fries'}], 'image_ids':['old'], 'source_ids':[]},
              {'id':'U23','title':'鸡翅薯条夹心','products':[{'name':'鸡翅','code':'wing'},{'name':'薯条','code':'fries'}], 'image_ids':['old'], 'source_ids':[]}]
        self.source.write_text(json.dumps({'entries':rows,'images':[{'id':'old','path':'old.webp'}],'sources':[]}))
        self.roles.write_text('{"recipes":{"U11":{"optional_codes":["fries"]}}}')
        nc.sync_database(self.source,self.db,self.roles)
        (self.root/'unified-v2/old.webp').write_bytes(b'old original photograph')
        self.catalog=self.root/'base-cards-v1/catalog.json';self.catalog.parent.mkdir()
        (self.catalog.parent/'cards').mkdir()
        self.data={'schema_version':1,'source_catalog_sha256':hashlib.sha256(self.source.read_bytes()).hexdigest(),'entries':[]}
        for r in rows:
            image=self.catalog.parent/'cards'/f'{r["id"]}.png';image.write_bytes(b'\x89PNG\r\n\x1a\n'+r['id'].encode())
            self.data['entries'].append({'id':r['id'],'source_title':r['title'],'title':r['title'],
              'card':f'cards/{r["id"]}.png','card_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),
              'display_products':['玉米杯 ＋ 麦旋风'] if r['id']=='U11' else ['鸡翅 ＋ 薯条']})
        self.save()

    def save(self):self.catalog.write_text(json.dumps(self.data,ensure_ascii=False))

    def test_delivers_numbered_png_not_source_photo(self):
        before=self.db.read_bytes();answer=nc.cards(self.db,['U11','U23'])
        for card in answer['cards']:
            self.assertTrue(card['images_ready']);self.assertTrue(card['hero_image_absolute_path'].endswith(card['id']+'.png'))
            self.assertEqual(card['images'][0]['kind'],'presentation_card')
            self.assertTrue(card['source_images'][0]['absolute_path'].endswith('old.webp'))
        self.assertEqual(before,self.db.read_bytes())
        self.assertNotIn('薯条',answer['cards'][0]['caption'])

    def test_no_catalog_does_not_fallback_to_photo(self):
        self.catalog.unlink();r=nc.cards(self.db,['U11'])['cards'][0]
        self.assertFalse(r['images_ready']);self.assertIsNone(r['hero_image_absolute_path'])

    def test_missing_png_does_not_fallback_to_photo(self):
        (self.catalog.parent/'cards/U11.png').unlink();r=nc.cards(self.db,['U11'])['cards'][0]
        self.assertFalse(r['images_ready']);self.assertEqual(r['images'],[])

    def test_corrupt_png_rejected(self):
        (self.catalog.parent/'cards/U11.png').write_bytes(b'wrong')
        with self.assertRaisesRegex(ValueError,'哈希'):nc.cards(self.db,['U11'])

    def test_stale_catalog_rejected(self):
        self.data['source_catalog_sha256']='0'*64;self.save()
        with self.assertRaisesRegex(ValueError,'版本不一致'):nc.cards(self.db,['U11'])

    def test_path_escape_rejected(self):
        self.data['entries'][0]['card']='../U11.png';self.save()
        with self.assertRaisesRegex(ValueError,'越出'):nc.cards(self.db,['U11'])

    def test_wrong_number_file_rejected(self):
        self.data['entries'][0]['card']='cards/U23.png';self.save()
        with self.assertRaisesRegex(ValueError,'编号'):nc.cards(self.db,['U11'])

    def test_relocated_bundle_remains_usable(self):
        relocated=self.root/'elsewhere';shutil.copytree(self.root/'base-cards-v1',relocated/'base-cards-v1');shutil.copytree(self.root/'unified-v2',relocated/'unified-v2')
        answer=nc.cards(relocated/'unified-v2/numbers.sqlite',['U23'])['cards'][0]
        self.assertTrue(answer['images_ready']);self.assertTrue(Path(answer['hero_image_absolute_path']).is_relative_to(relocated.resolve()))

    def test_retired_id_stays_rejected(self):
        with sqlite3.connect(self.db) as c:c.execute("UPDATE recipes SET active=0 WHERE id='U23'")
        with self.assertRaisesRegex(ValueError,'U23'):nc.cards(self.db,['U11','U23'])


if __name__=='__main__':unittest.main()
