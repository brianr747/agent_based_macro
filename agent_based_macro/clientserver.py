"""
File for client commands/messages.

Use the same object for both legs: keeps the command/response code logically organised.

In some cases, there is no response, which is fine.

The only subclasses in this file are for the base Simulation class, which relate to time management.
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

    def server_command(self, server, *args):
        """The server will call this to execute the command"""
        pass

    def client_message(self, client, *args):
        """The client will call this to get the message payload."""
        pass


class MsgPause(ClientServerMsg):
    def server_command(self, server, *args):
        server.IsPaused = True


class MsgUnpause(ClientServerMsg):
    def server_command(self, server, *args):
        # Do nothing if unpaused
        if not server.IsPaused:
            return
        server.MonotonicBase = time.monotonic()
        server.IsPaused = False


class MsgTimeQuery(ClientServerMsg):
    def server_command(self, server, *args):
        response = MsgTimeQuery(server.IsPaused, server.Time)
        response.ClientID = self.ClientID
        server.queue_message(response)

    def client_message(self, client, ispaused, ttime):
        # ispaused, ttime = self.args
        client.IsPaused = ispaused
        client.Time = ttime
        client.LastResponseMonotonic = time.monotonic()
