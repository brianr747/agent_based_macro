"""
File for client commands/messages.

Use the same object for both legs: keeps the command/response code logically organised.

In some cases, there is no response, which is fine.

The only subclasses in this file are for the base Simulation class, which relate to time management.

Copyright 2021 Brian Romanchuk

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
"""

import time
from agent_based_macro.utils import KwargManager


class InvalidMessageArguments(ValueError):
    pass


class Server(object):
    """
    Server class. Embeds a simulation, and handles client communication
    """
    def __init__(self):
        self.Simulation = None
        self.ClientIDList = []
        self.SimulationMessages = set()
        # These variables have clunky names, but want to underline which are going out/in.
        self.IncomingClientMessages = []
        self.OutgoingServerMessages = []

    def add_simulation(self, sim):
        if self.Simulation is not None:
            raise ValueError('Cannot replace a simulation')
        self.Simulation = sim

    def register_message_type(self, is_simulation_message, message_type, handler, required, docstring=''):
        """
        Add a new ServerMessage type.
        Although standard when compared to other KwargManager subclass registry calls, is_simulation_message
        is a new parameter for this type. Since messages can either be handled by the server or passed on
        to the simulation, we need to mark which one to dispatch to.

        :param message_type: str
        :param handler: function
        :param is_simulation_message: bool
        :param required: tuple
        :param docstring: str
        :return:
        """
        obj = ServerMessage()
        obj.register_entry(message_type, handler, required, docstring)
        if is_simulation_message:
            self.SimulationMessages.add(message_type)

    def add_message(self, client_id, msg):
        """
        Add a message to the outgoing message queue. Insert the client_id as a parameter.
        :param client_id: int
        :param msg: ServerMessage
        :return:
        """
        msg.client_id = client_id
        self.OutgoingServerMessages.append(msg)


class ServerMessage(KwargManager):
    """
    Messages *sent by the server*.
    """
    GRequired = {}
    GKey = 'message_type'
    GDocstrings = {}
    GHandler = {}
    ErrorType = InvalidMessageArguments

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # This is set by the Server.add_message() call.
        self.client_id = None


class ClientServerMsg(object):
    """
    This class is deprecated
    """
    def __init__(self, **kwargs):
        """
        Create the object with the arguments to be passed to the callback.
        :param args: whatever...
        """
        self.KWArgs = kwargs
        self.ClientID = None

    def server_command(self, server, **kwargs):
        """The server will call this to execute the command"""
        pass

    def client_message(self, client, **kwargs):
        """The client will call this to get the message payload."""
        pass


class MsgPause(ClientServerMsg):
    def server_command(self, server, **kwargs):
        server.IsPaused = True


class MsgUnpause(ClientServerMsg):
    def server_command(self, server, **kwargs):
        # Do nothing if unpaused
        if not server.IsPaused:
            return
        server.MonotonicBase = time.monotonic()
        server.IsPaused = False


class MsgTimeQuery(ClientServerMsg):
    def server_command(self, server, **kwargs):
        response = MsgTimeQuery(is_paused=server.IsPaused, ttime=server.Time)
        response.ClientID = self.ClientID
        server.queue_message(response)

    def client_message(self, client, **kwargs):
        # ispaused, ttime = self.args
        client.IsPaused = kwargs['is_paused']
        client.Time = kwargs['ttime']
        client.LastResponseMonotonic = time.monotonic()
