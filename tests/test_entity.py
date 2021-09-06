from unittest import TestCase

import agent_based_macro.entity as entity

class TestEntity(TestCase):
    def test_get_representation(self):
        obj = entity.Entity(name='name', ttype='ttype')
        rep = obj.get_representation()
        self.assertEqual(obj.GID, rep['GID'])
        self.assertEqual('name', rep['Name'])
        self.assertEqual('ttype', rep['Type'])
