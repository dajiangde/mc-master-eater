import copy
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / "skills/mcd-hidden-explorer/scripts/explore.py"
spec = importlib.util.spec_from_file_location("explore", PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.row = dict(id="X01", aliases=["T01"], name="TEST ONLY <script>alert(1)</script>",
                        recipe_status="cover_only", source_url="https://example.com/source",
                        observation="<b>synthetic test fixture</b>", ingredients=[], steps=[])
        self.data = dict(schema_version=1, entries=[self.row])

    def test_empty(self):
        self.assertEqual(m.validate(dict(schema_version=1, entries=[]))["entries"], [])
        self.assertIn("0 条", m.render(dict(schema_version=1, entries=[])))

    def test_lookup(self):
        self.assertEqual(m.lookup(m.validate(self.data), " t01 ")["canonical_id"], "X01")

    def test_unknown(self):
        with self.assertRaises(ValueError):
            m.lookup(self.data, "X99")

    def test_escape(self):
        page = m.render(m.validate(self.data))
        self.assertNotIn("<script>alert", page)
        self.assertIn("&lt;script&gt;", page)

    def test_duplicate(self):
        self.data["entries"].append(copy.deepcopy(self.row))
        with self.assertRaises(ValueError):
            m.validate(self.data)

    def test_cover_recipe(self):
        self.row["steps"] = ["invented"]
        with self.assertRaises(ValueError):
            m.validate(self.data)

    def test_negative_quantity(self):
        self.row.update(recipe_status="reported_recipe", ingredients=[dict(name="test", quantity=-1)])
        with self.assertRaises(ValueError):
            m.validate(self.data)

    def test_unknown_quantity(self):
        self.row.update(recipe_status="reported_recipe", ingredients=[dict(name="test", quantity=None)])
        m.validate(self.data)

    def test_unsafe_url(self):
        self.row["source_url"] = "javascript:alert(1)"
        with self.assertRaises(ValueError):
            m.validate(self.data)

    def test_images_rejected(self):
        self.row["assets"] = ["unlicensed.webp"]
        with self.assertRaises(ValueError):
            m.validate(self.data)


if __name__ == "__main__":
    unittest.main()
