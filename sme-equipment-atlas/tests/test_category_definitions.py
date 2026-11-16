"""Every category must say what it means, so an assignment can be audited.

A bare {category_id, parent, name} record leaves an extraction agent classifying against a
name alone, which is how two agents silently file different things under one node. The atlas
reached 12,000 observations with 76 of 107 categories undefined; these tests stop that
returning.
"""
import unittest
from atlas.core import load

class CategoryDefinitionTests(unittest.TestCase):
    def setUp(self):
        self.data=load()
        self.categories=self.data['categories']

    def test_every_category_has_a_definition(self):
        missing=sorted(cid for cid,c in self.categories.items()
                       if not (c.get('definition') or '').strip())
        self.assertEqual(missing,[],f'categories without a definition: {missing}')

    def test_definitions_say_something(self):
        """A one-line restatement of the name is not a definition."""
        for cid,c in self.categories.items():
            definition=(c.get('definition') or '').strip()
            with self.subTest(category=cid):
                self.assertGreater(len(definition),60)
                self.assertNotEqual(definition.rstrip('.').lower(),(c.get('name') or '').strip().lower())

    def test_no_two_categories_share_a_definition(self):
        seen={}
        for cid,c in sorted(self.categories.items()):
            key=(c.get('definition') or '').strip()
            self.assertNotIn(key,seen,f'{cid} duplicates the definition of {seen.get(key)}')
            seen[key]=cid

    def test_every_populated_category_is_defined(self):
        """The nodes carrying evidence are the ones an analyst will read."""
        used={o.get('category_id') for o in self.data['observations'].values() if o.get('category_id')}
        for cid in sorted(used):
            with self.subTest(category=cid):
                self.assertIn(cid,self.categories)
                self.assertTrue((self.categories[cid].get('definition') or '').strip())
