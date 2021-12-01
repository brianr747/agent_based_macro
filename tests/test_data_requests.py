from unittest import TestCase
from agent_based_macro.data_requests import ActionDataRequestHolder, ActionDataParameterError, register_query

class TestActionDataRequestHolder(TestCase):
    def test_assert_valid_empty(self):
        obj = ActionDataRequestHolder({})
        obj2 = ActionDataRequestHolder(obj)
        obj3 = ActionDataRequestHolder()

    def test_add_request(self):
        register_query('Test1', ('x',))
        obj = ActionDataRequestHolder({})
        obj.add_request('foo', {'request': 'Test1', 'x': 1})
        obj2 = ActionDataRequestHolder({'foo': {'request': 'Test1', 'x': 1}})

    def test_bad_ctor(self):
        # Not sure how to set up a constructor call, so do it "manually"
        try:
            obj = ActionDataRequestHolder(1)
        except ValueError:
            return
        self.assertTrue(False)

    def test_add_bad(self):
        register_query('Test2', ('y',))
        obj = ActionDataRequestHolder({})
        # Does not include the required 'y'
        self.assertRaises(ActionDataParameterError, obj.add_request, 'foo', {'request': 'Test2', 'x': 1})

    def test_not_exist(self):
        obj = ActionDataRequestHolder({})
        # Does not include the required 'y'
        self.assertRaises(ActionDataParameterError, obj.add_request, 'foo',
                          {'request': 'NONEXISTENT_REQUEST', 'x': 1})

    def test_no_request(self):
        obj = ActionDataRequestHolder({})
        # Does not include the required 'y'
        self.assertRaises(ActionDataParameterError, obj.add_request, 'foo',
                      {'x': 1})


