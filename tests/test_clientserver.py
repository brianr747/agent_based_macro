from unittest import TestCase

from agent_based_macro.clientserver import Server, ServerMessage
from agent_based_macro.simulation import Simulation


class TestSimulation(Simulation):
    """
    Create a dummy subclass of Simulation in case Simulation reverts to being an abstract base class.
    """
    pass


def dummy_handler(**kwargs):
    pass


class TestServer(TestCase):
    @staticmethod
    def reset_server_messages():
        ServerMessage.GRequired = {}
        ServerMessage.GHandler = {}
        ServerMessage.GDocstrings = {}

    def test_add_message_type(self):
        obj = Server()
        self.reset_server_messages()
        self.assertDictEqual({}, ServerMessage.GRequired)
        obj.register_message_type(True, 'test1', dummy_handler, ('x',))
        self.assertIn('test1', obj.SimulationMessages)
        # will fail if not registered
        ServerMessage(message_type='test1', x=1)
        obj.register_message_type(False, 'test2', dummy_handler, ('y',))
        self.assertNotIn('test2', obj.SimulationMessages)
        ServerMessage(message_type='test2', y='foo')

    def test_add_simulation(self):
        obj = Server()
        self.assertIsNone(obj.Simulation)
        # This will break if TestStimulation() does not support being created with no arguments.
        # Rather than fix this test, fix TestSimulation's __init__()
        sim = TestSimulation()
        obj.add_simulation(sim)
        self.assertEqual(sim, obj.Simulation)
        self.assertRaises(ValueError, obj.add_simulation, sim)

    def test_add_message(self):
        obj = Server()
        self.reset_server_messages()
        obj.register_message_type(True, 'test_type', dummy_handler, ('x',))
        msg = ServerMessage(message_type='test_type', x=1)
        obj.add_message(client_id=2, msg=msg)
        self.assertEqual(1, len(obj.OutgoingServerMessages))



