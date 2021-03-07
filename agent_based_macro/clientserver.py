"""
File for client commands/messages.

Use the same object for both legs: keeps the command/response code logically organised.

In some cases, there is no response, which is fine.

The only sublcasses in this file are for the base Simulation class, which relate to time management.
"""

import time

class ClientServerMsg(object):
    def __init__(self, *args):
        """
        Create the object with the arguments to be passed to the callback.
        :param args: whatever...
        """
        self.args = args
        self.ClientID = None

    def ServerCommand(self, server, *args):
        'The server will call this to execute the command'
        pass

    def ClientMessage(self, client, *args):
        'The client will call this to get the message payload.'
        pass


class MsgPause(ClientServerMsg):
    def ServerCommand(self, server, *args):
        server.IsPaused = True


class MsgUnpause(ClientServerMsg):
    def ServerCommand(self, server, *args):
        # Do nothing if unpaused
        if not server.IsPaused:
            return
        server.MonotonicBase = time.monotonic()
        server.IsPaused = False


class MsgTimeQuery(ClientServerMsg):
    def ServerCommand(self, server, *args):
        response = MsgTimeQuery(server.IsPaused, server.Time)
        response.ClientID = self.ClientID
        server.QueueMessage(response)

    def ClientMessage(self, client, ispaused, ttime):
        # ispaused, ttime = self.args
        client.IsPaused = ispaused
        client.Time = ttime