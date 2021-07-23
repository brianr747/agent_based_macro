from unittest import TestCase

import agent_based_macro.utils as utils


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
        self.assertEqual(obj.Data, [0.]*utils.TimeSeries.ChunkSize)

    def test_init_2(self):
        obj = utils.TimeSeries(freq=1., fill= None)
        # Should initialise with two entries
        self.assertEqual(obj.Data, [None]*utils.TimeSeries.ChunkSize)

