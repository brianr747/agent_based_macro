from unittest import TestCase

import agent_based_macro.entity
import agent_based_macro.simulation as simulation


class Test(TestCase):
    def test_add_entity(self):
        # Create an Entity, see that it is in the dictionary
        obj = agent_based_macro.entity.Entity()
        gid = obj.GID
        self.assertEqual(obj, agent_based_macro.entity.GEntityDict[obj.GID])
        # Now: delete it, and it should be dropped from the weak reference dictionary,
        del obj
        self.assertNotIn(gid, agent_based_macro.entity.GEntityDict)


class TestEntity(TestCase):
    def test_get_entity(self):
        obj = agent_based_macro.entity.Entity()
        gid = obj.GID
        self.assertEqual(obj, agent_based_macro.entity.Entity.get_entity(gid))
