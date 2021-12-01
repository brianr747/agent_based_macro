"""
File for client commands/messages.

Use the same object for both legs: keeps the command/response code logically organised.

In some cases, there is no response, which is fine.

The only subclasses in this file are for the base Simulation class, which relate to time management.
"""

import time


class ClientServerMsg(object):
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
