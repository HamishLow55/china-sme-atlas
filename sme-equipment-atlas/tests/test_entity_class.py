"""Every entity declares which side of the indigenisation comparison it sits on.

Reconciliations in this repository name their inputs explicitly, so the atlas itself cannot
silently total a foreign incumbent into a domestic figure. The analysis layer does group by
category, and there the mistake is one line of pandas away. `entity_class` is what makes the split
machine-readable rather than a convention buried in free-text notes.
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLASSES = {
    'china_supply_base',   # counted in the domestic Chinese equipment supply base
    'foreign_incumbent',   # international incumbent, registered for comparison
    'equipment_buyer',     # chip maker or OSAT: demand side, never an equipment revenue total
    'disclosure_only',     # registered because another party's filing discloses it
    'reference_aggregate', # not a firm at all
}


def entities():
    rows = {}
    for path in sorted((ROOT / 'data/entities').glob('*.json')):
        for record in json.loads(path.read_text(encoding='utf-8')):
            rows[record['entity_id']] = record
    return rows


class EntityClassTests(unittest.TestCase):
    def setUp(self):
        self.entities = entities()

    def test_every_entity_declares_a_class(self):
        missing = sorted(e for e, r in self.entities.items() if not r.get('entity_class'))
        self.assertEqual(missing, [], f'entities without entity_class: {missing}')

    def test_every_class_is_one_of_the_declared_values(self):
        bad = sorted({r['entity_class'] for r in self.entities.values()} - CLASSES)
        self.assertEqual(bad, [], f'undeclared entity_class values: {bad}')

    def test_a_subsidiary_of_a_china_group_is_not_a_foreign_incumbent(self):
        """Group attribution beats domicile. Secote's Japanese subsidiary and Yitang's US one
        consolidate into Chinese parents, so they count on the domestic side however they are
        incorporated; a record claiming otherwise would double-count against its own parent."""
        for eid, record in sorted(self.entities.items()):
            parent = record.get('parent_entity_id')
            if not parent:
                continue
            with self.subTest(entity=eid):
                self.assertIn(parent, self.entities, f'{eid}: unknown parent {parent}')
                if self.entities[parent].get('entity_class') == 'china_supply_base':
                    self.assertNotEqual(
                        record['entity_class'], 'foreign_incumbent',
                        f'{eid} consolidates into Chinese-controlled {parent}; it cannot be a foreign incumbent')

    def test_a_foreign_incumbent_carries_a_note_saying_why_it_is_registered(self):
        """A comparator entity is the one kind a reader is most likely to misread as domestic
        supply, so it must say in its own record what it is there for."""
        for eid, record in sorted(self.entities.items()):
            if record.get('entity_class') != 'foreign_incumbent':
                continue
            with self.subTest(entity=eid):
                self.assertGreater(len((record.get('notes') or '').strip()), 120,
                                   f'{eid}: a foreign incumbent needs a note stating its comparator role')


if __name__ == '__main__':
    unittest.main()
