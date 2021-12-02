from unittest import TestCase

import agent_based_macro.entity as entity
from agent_based_macro.entity import Action
from agent_based_macro.errors import InvalidActionArguments

class TestEntity(TestCase):
    def test_get_representation(self):
        obj = entity.Entity(name='name', ttype='ttype')
        rep = obj.get_representation()
        self.assertEqual(obj.GID, rep['GID'])
        self.assertEqual('name', rep['Name'])
        self.assertEqual('ttype', rep['Type'])


class TestAction(TestCase):
    def test_init_bad(self):
        try:
            obj = Action()
            self.fail('should raise an Exception')
        except ValueError:
            pass
        try:
            obj = Action(action_type='Kabloom')
            self.fail('should raise an Exception')
        except InvalidActionArguments:
            pass

    def test_init_good(self):
        Action.add_action_type('TEST1', None, tuple(), 'doc')
        obj = Action(action_type='TEST1')

    def test_init_missing_argument(self):
        Action.add_action_type('TEST2', None, ('x',), 'doc')
        obj = Action(action_type='TEST2', x=1)
        try:
            Action(action_type='TEST2', y=1)
            self.fail('should have raised an exception')
        except InvalidActionArguments:
            pass

