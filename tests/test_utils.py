from unittest import TestCase

import agent_based_macro.utils as utils
from agent_based_macro.utils import KwargManager


class Test(TestCase):
    def test_jitter_time(self):
        utils.reset_jitter()
        valz = []
        for i in range(0, 30):
            valz.append(utils.jitter_time((0., 1.)))
        self.assertEqual(valz, [0.5,
                                0.05,
                                0.55,
                                0.1,
                                0.6,
                                0.15,
                                0.65,
                                0.2,
                                0.7,
                                0.25,
                                0.75,
                                0.3,
                                0.8,
                                0.35,
                                0.85,
                                0.4,
                                0.9,
                                0.45,
                                0.95,
                                1.0,
                                0.0,
                                0.5,
                                0.05,
                                0.55,
                                0.1,
                                0.6,
                                0.15,
                                0.65,
                                0.2,
                                0.7])

    def test_jitter_time_2(self):
        utils.reset_jitter()
        self.assertEqual(utils.jitter_time((0., .5)), 0.25)
        utils.reset_jitter()
        self.assertEqual(utils.jitter_time((0.6, .8)), 0.7)


class TestTimeSeries(TestCase):
    def test_init_1(self):
        # Basic case - should initialise with one entry.
        obj = utils.TimeSeries(freq=1., fill=0.)
        self.assertEqual(obj.Data, [0.] * utils.TimeSeries.ChunkSize)

    def test_init_2(self):
        obj = utils.TimeSeries(freq=1., fill=None)
        # Should initialise with two entries
        self.assertEqual(obj.Data, [None] * utils.TimeSeries.ChunkSize)

    def test_set_1(self):
        utils.TimeSeries.ChunkSize = 4
        obj = utils.TimeSeries()
        utils.TimeSeries.Time = 0.
        obj.set(1.)
        self.assertEqual(obj.Data, [1., None, None, None])
        obj.set(2., time=1.)
        self.assertEqual(obj.Data, [1., 2., None, None])
        utils.TimeSeries.ChunkSize = 1024

    def test_set_grow(self):
        utils.TimeSeries.ChunkSize = 4
        obj = utils.TimeSeries()
        utils.TimeSeries.Time = 4.
        # Should add one chunk
        obj.set(1.)
        self.assertEqual(obj.Data, [None, None, None, None, 1., None, None, None])
        obj.set(2., time=6.)
        self.assertEqual(obj.Data, [None, None, None, None, 1., None, 2., None])
        utils.TimeSeries.ChunkSize = 1024

    def test_big_grow(self):
        utils.TimeSeries.ChunkSize = 3
        obj = utils.TimeSeries()
        utils.TimeSeries.Time = 6.
        # Should add two chunks
        obj.set(1.)
        self.assertEqual(obj.Data, [None, None, None, None, None, None, 1., None, None])
        utils.TimeSeries.ChunkSize = 1024

    def test_add(self):
        obj = utils.TimeSeries(fill=None, freq=1.)
        self.assertEqual(obj.Data[0], None)
        # Time 0., .1, .2 all map to first entry
        obj.add(1., time=0.1)
        self.assertEqual(obj.Data[0], 1.)
        obj.add(2., time=.2)
        self.assertEqual(3., obj.Data[0])
        utils.TimeSeries.Time = 0.
        obj.add(3.)
        self.assertEqual(6., obj.Data[0])

    def test_iadd(self):
        obj = utils.TimeSeries(fill=None, freq=1.)
        utils.TimeSeries.Time = 0.
        self.assertEqual(obj.Data[0], None)
        # Time 0., .1, .2 all map to first entry
        obj += 1.
        self.assertEqual(obj.Data[0], 1.)
        utils.TimeSeries.Time = .2
        obj += 2
        self.assertEqual(3., obj.Data[0])

    def test_isub(self):
        obj = utils.TimeSeries(fill=None, freq=1.)
        utils.TimeSeries.Time = 0.
        self.assertEqual(obj.Data[0], None)
        # Time 0., .1, .2 all map to first entry
        obj -= 1.
        self.assertEqual(obj.Data[0], -1.)
        utils.TimeSeries.Time = .2
        obj -= 2.
        self.assertEqual(-3., obj.Data[0])

    def test_get_1(self):
        obj = utils.TimeSeries(fill=None, freq=1.)
        utils.TimeSeries.Time = 0.
        obj.set(1., time=0.)
        self.assertEqual(1., obj.get(time=0.1))
        self.assertEqual(1., obj.get())
        self.assertIsNone(obj.get(time=1.))
        # Check that handles Get() beyond the size of Data
        chunk = utils.TimeSeries.ChunkSize
        self.assertEqual(chunk, len(obj.Data))
        # Should return None if we go past end
        self.assertIsNone(obj.get(float(chunk + 2)))
        # Should not grow
        self.assertEqual(chunk, len(obj.Data))

    def test_negative_time(self):
        obj = utils.TimeSeries()
        # obj.Get(-1.)
        self.assertRaises(ValueError, obj.get, -.1)


# Create a dummy KwargManager subclass to run tests on.

class DummyKeywordError(utils.BadKeywordError):
    pass


class DummyKwargManager(KwargManager):
    GRequired = {}
    GKey = 'testkey'
    GDocstrings = {}
    GHandler = {}
    ErrorType = DummyKeywordError

    @staticmethod
    def reset_entries():
        'call this on unit tests to undo effect of other tests'
        DummyKwargManager.GRequired = {}
        DummyKwargManager.GDocstrings = {}
        DummyKwargManager.GKey = 'testkey'


GARGS = None
KWARGS = None


def dummy_handler(*args, **kwargs):
    global GARGS
    global KWARGS
    GARGS = args
    KWARGS = kwargs


class TestKwargManager(TestCase):
    def test_empty_init(self):
        DummyKwargManager()

    def test_bad_int(self):
        try:
            DummyKwargManager(foo='1')
            self.fail('should have thrown an exception')
        except DummyKeywordError:
            pass

    def test_missing(self):
        # If I read the docs, I think I could have the framework call reset_entries() before every test
        DummyKwargManager.reset_entries()
        try:
            DummyKwargManager(testkey='cat')
            self.fail('should have thrown an exception')
        except DummyKeywordError:
            pass

    def test_missing_argument(self):
        DummyKwargManager.reset_entries()
        obj = DummyKwargManager()
        obj.register_entry('test1', dummy_handler, ('x',))
        obj = DummyKwargManager(testkey='test1', x=2)
        self.assertEqual(obj.KWArgs, {'x': 2})
        try:
            DummyKwargManager(testkey='test1', y=3)
            self.fail('should have thrown an exception')
        except DummyKeywordError:
            pass

    def test_2(self):
        DummyKwargManager.reset_entries()
        dobj = DummyKwargManager()
        dobj.register_entry('test2', dummy_handler, ('x', 'y'))
        obj = DummyKwargManager(testkey='test2', x=1, y=2)
        self.assertDictEqual(obj.KWArgs, {'x': 1, 'y': 2})
        self.assertEqual(obj.ObjectType, 'test2')

    def test_get(self):
        DummyKwargManager.reset_entries()
        dobj = DummyKwargManager()
        dobj.register_entry('test2', dummy_handler, ('x', 'y'))
        obj = DummyKwargManager(testkey='test2', x=1, y=2)
        ttype, ddict = obj.get()
        self.assertDictEqual(ddict, {'x': 1, 'y': 2})
        self.assertEqual(ttype, 'test2')

    def test_multiple(self):
        DummyKwargManager.reset_entries()
        dobj = DummyKwargManager()
        dobj.register_entry('test2', dummy_handler, ('x', 'y'))
        self.assertRaises(ValueError, dobj.register_entry, 'test2', dummy_handler, ('z'))

    def test_call_1(self):
        DummyKwargManager.reset_entries()
        dobj = DummyKwargManager()
        dobj.register_entry('test2', dummy_handler, ('x', 'y'))
        obj = DummyKwargManager(testkey='test2', x=1, y=2)
        obj.run(1)
        global GARGS
        global KWARGS
        self.assertEqual((1, 'test2'), GARGS)
        self.assertDictEqual({'x': 1, 'y': 2}, KWARGS)






