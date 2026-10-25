import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('gallery_site',ROOT/'scripts/build_gallery_site.py')
gallery=importlib.util.module_from_spec(spec);spec.loader.exec_module(gallery)

class GallerySiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.cards=self.root/'input';self.cards.mkdir()
        self.row={'id':'U11','card':'cards/U11.png','thumbnail':'thumbnails/U11.png'}
        for key,folder in [('card','cards'),('thumbnail','thumbnails')]:
            (self.cards/folder).mkdir();p=self.cards/self.row[key];p.write_bytes(b'processed png fixture')
            self.row[key+'_sha256']=gallery.digest(p)
        (self.cards/'source-images').mkdir();(self.cards/'source-images/private.webp').write_bytes(b'private')
        self.write_catalog()
        (self.cards/'index.html').write_text('<html><header><a href="../raw.html">原始图库</a></header><article data-search="U11 吃法"><a href="cards/U11.png">下载原图</a><img src="thumbnails/U11.png"><a href="https://www.xiaohongshu.com/explore/note?xsec_token=private">来源</a></article><footer><a href="catalog.json">数据</a><a href="all.zip">下载</a></footer></html>')
        self.out=self.root/'out'
    def write_catalog(self):
        (self.cards/'catalog.json').write_text(json.dumps({'entries':[self.row]}))
    def test_allowlist_and_safe_attribution(self):
        r=gallery.build(self.cards,self.out)
        self.assertEqual(set(r['files']),{'index.html','.nojekyll','cards/U11.png','thumbnails/U11.png'})
        html=(self.out/'index.html').read_text()
        self.assertIn('https://www.xiaohongshu.com/explore/note',html)
        for private in ('xsec_token','../raw.html','catalog.json','all.zip','source-images','下载原图'):
            self.assertNotIn(private,html)
    def test_bad_hash_rejected_before_output(self):
        (self.cards/'cards/U11.png').write_bytes(b'wrong')
        with self.assertRaisesRegex(ValueError,'hash mismatch'):gallery.build(self.cards,self.out)
        self.assertFalse(self.out.exists())
    def test_path_escape_rejected(self):
        self.row['card']='../private.png';self.write_catalog()
        with self.assertRaisesRegex(ValueError,'outside gallery'):gallery.build(self.cards,self.out)
        self.assertFalse(self.out.exists())
    def test_existing_output_is_preserved(self):
        self.out.mkdir();sentinel=self.out/'keep';sentinel.write_text('keep')
        with self.assertRaisesRegex(ValueError,'new output'):gallery.build(self.cards,self.out)
        self.assertEqual(sentinel.read_text(),'keep')

if __name__=='__main__':unittest.main()
