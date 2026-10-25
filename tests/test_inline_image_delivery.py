"""All card routes share the same inline final-answer contract."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'skills/mcd-hidden-explorer/scripts'))
import discover
import image_delivery
import session_state
import test_presentation_cards as fixtures


class InlineImageDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.PresentationCardTests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.db=self.fixture.db
        self.session=self.fixture.root/'session.json';session_state.init_session(self.session)

    def assert_inline(self,result,key='methods'):
        methods=result[key]
        self.assertTrue(methods)
        self.assertEqual(result['inline_image_count'],len(methods))
        for method in methods:
            self.assertIn('![',method['image_markdown'])
            self.assertIn('](local-file:///',method['image_markdown'])
            self.assertIn(method['id']+'.png',method['image_markdown'])
            self.assertIn(method['image_markdown'],result['response_markdown'])
            self.assertNotIn('old.webp',method['image_markdown'])

    def test_direct_card_lookup(self):
        self.assert_inline(fixtures.nc.cards(self.db,['U11','U23']),key='cards')

    def test_random(self):
        self.assert_inline(discover.random_entry(self.db,self.session,limit=2,seed=11))

    def test_by_product(self):
        self.assert_inline(discover.product_entry(self.db,self.session,'玉米',limit=2))

    def test_coupon_and_supplementary_images(self):
        # This input is synthetic local coupon text, not an account or claim operation.
        r=discover.coupon_entry(self.db,self.session,{'title':'玉米杯','products':[{'productName':'玉米杯'}]},limit=2)
        methods=r.get('methods',[])+r.get('supplementary',[])
        self.assertTrue(methods)
        self.assertEqual(r['inline_image_count'],len(methods))
        for m in methods:self.assertIn(m['image_markdown'],r['response_markdown'])

    def test_title_only_coupon_supplementary(self):
        r=discover.coupon_entry(self.db,self.session,{'title':'薯条买一送一'},limit=2)
        self.assertTrue(r['supplementary'])
        self.assertEqual(r['inline_image_count'],len(r['supplementary']))
        for m in r['supplementary']:
            self.assertIn('](local-file:///',m['image_markdown'])
            self.assertIn(m['image_markdown'],r['response_markdown'])

    def test_selected_list_and_add_selection(self):
        self.assert_inline(discover.select(self.db,self.session,['U11']))
        self.assert_inline(discover.selection_view(self.db,self.session))

    def test_missing_image_is_not_faked(self):
        self.fixture.catalog.unlink()
        r=fixtures.nc.cards(self.db,['U11'])
        self.assertEqual(r['inline_image_count'],0)
        self.assertEqual(r['response_markdown'],'')
        self.assertEqual(r['cards'][0]['image_markdown'],'')

    def test_shared_result_covers_supplementary_and_escapes_path(self):
        with tempfile.TemporaryDirectory(prefix='image path ') as tmp:
            image=Path(tmp)/'配图(11)#.png';image.write_bytes(b'png')
            a={'id':'U11','display_number':'11号','card_title':'菜[名]',
               'hero_image_absolute_path':str(image),'images_ready':True}
            r=image_delivery.inline_response({'methods':[],'supplementary':[a]})
            self.assertEqual(r['inline_image_count'],1)
            self.assertIn('菜\\[名\\]',a['image_markdown'])
            self.assertIn('](local-file:///',a['image_markdown'])
            self.assertIn('image%20path%20',a['image_markdown'])
            self.assertNotIn('(<',a['image_markdown'])
            self.assertIn('%E9%85%8D%E5%9B%BE%2811%29%23.png',a['image_markdown'])


if __name__=='__main__':unittest.main()
