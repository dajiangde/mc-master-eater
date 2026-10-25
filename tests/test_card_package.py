"""Packaging tests use synthetic files; never add private photos to fixtures."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'skills/mcd-hidden-explorer/scripts'))
import numbered_catalog as nc
spec=importlib.util.spec_from_file_location('package_cards',ROOT/'scripts/package_cards.py')
pkg=importlib.util.module_from_spec(spec);spec.loader.exec_module(pkg)
PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jvO0AAAAASUVORK5CYII=')


class CardPackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.cards=self.root/'source-cards';self.cards.mkdir()
        for folder in ['cards','thumbnails','source-images']:(self.cards/folder).mkdir()
        for folder in ['cards','thumbnails']:(self.cards/folder/'U11.png').write_bytes(PNG)
        (self.cards/'source-images/private-original.webp').write_bytes(b'raw-private-sentinel')
        sha=hashlib.sha256(PNG).hexdigest()
        self.row={'id':'U11','title':'玉米冰品','category':'甜品','card':'cards/U11.png',
                  'thumbnail':'thumbnails/U11.png','card_sha256':sha,'thumbnail_sha256':sha,
                  'display_products':['玉米杯＋冰品'],'display_steps':['混合'],
                  'source_image':'source-images/private-original.webp',
                  'source_image_metadata':{'url':'https://example.xhscdn.com/private-original.webp?token=secret'}}
        (self.cards/'catalog.json').write_text(json.dumps({'entries':[self.row]}))
        self.db=self.root/'source.sqlite3';conn=sqlite3.connect(self.db);conn.executescript(nc.SCHEMA)
        conn.execute("INSERT INTO meta VALUES('schema_version','1')")
        payload={'category':'甜品','mapped_images':[{'path':'private-original.webp'}],
                 'mapped_sources':[{'id':'S1','title':'来源','url':'https://example.com/post?xsec_token=secret'}],
                 'original_records':[{'private':'private-original.webp'}], 'menu_scope':{},
                 'suggested_steps':['混合'],'tested_by_project':False}
        conn.execute('INSERT INTO recipes VALUES(?,?,?,?,?,?)',('U11',11,'玉米冰品','玉米冰品',1,json.dumps(payload)))
        conn.execute('INSERT INTO products VALUES(?,?,?)',(1,'玉米杯','CORN'))
        conn.execute('INSERT INTO recipe_products VALUES(?,?,?,?,?,?)',('U11',1,0,'required',None,'{}'))
        conn.commit();conn.close()
        self.out=self.root/'library'

    def test_export_uses_processed_images_without_raw_files_or_signature(self):
        pkg.export_library(self.cards,self.db,self.out)
        result=nc.cards(self.out/'numbered-catalog.sqlite3',['11'])
        self.assertTrue(result['cards'][0]['images_ready'])
        self.assertEqual(Path(result['cards'][0]['hero_image_absolute_path']),(self.out/'cards/U11.png').resolve())
        self.assertEqual(result['cards'][0]['required_products'],['玉米杯'])
        self.assertFalse((self.out/'source-images').exists())
        for p in self.out.rglob('*'):
            if p.is_file():
                self.assertNotIn(b'private-original',p.read_bytes())
                self.assertNotIn(b'xsec_token',p.read_bytes())
        archive=self.root/'library.zip';pkg.make_zip(self.out,archive)
        with zipfile.ZipFile(archive) as z:
            self.assertEqual(sum(x.startswith('cards/') for x in z.namelist()),1)
            self.assertFalse(any(x.startswith('source-images/') for x in z.namelist()))

    def test_wrong_hash_rejected_before_output(self):
        self.row['card_sha256']='0'*64
        (self.cards/'catalog.json').write_text(json.dumps({'entries':[self.row]}))
        with self.assertRaises(ValueError):pkg.export_library(self.cards,self.db,self.out)
        self.assertFalse(self.out.exists())

    def test_source_path_escape_rejected(self):
        self.row['card']='../private-original.webp'
        (self.cards/'catalog.json').write_text(json.dumps({'entries':[self.row]}))
        with self.assertRaises(ValueError):pkg.export_library(self.cards,self.db,self.out)

    def test_existing_output_not_overwritten(self):
        self.out.mkdir();marker=self.out/'keep';marker.write_text('keep')
        with self.assertRaises(ValueError):pkg.export_library(self.cards,self.db,self.out)
        self.assertEqual(marker.read_text(),'keep')


if __name__=='__main__':unittest.main()
