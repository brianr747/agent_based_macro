from unittest import TestCase
import agent_based_macro.simulation as simulation


class Test(TestCase):
    def test_add_entity(self):
        # Create an Entity, see that it is in the dictionary
        obj = simulation.Entity()
        gid = obj.GID
        self.assertEqual(obj, simulation.GEntityDict[obj.GID])
        # Now: delete it, and it should be dropped from the weak reference dictionary,
        del obj
        self.assertNotIn(gid, simulation.GEntityDict)


class TestEntity(TestCase):
    def test_get_entity(self):
        obj = simulation.Entity()
        gid = obj.GID
        self.assertEqual(obj, simulation.Entity.GetEntity(gid))
