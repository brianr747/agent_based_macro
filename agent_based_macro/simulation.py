"""

Core simulation class.

Just does the minimum of operations: holds the event queue, manages the simulation time axis. After that, simulation
behaviour is driven by reaction to events.

The BaseSimulation object in base_simulation.py (might be renamed) implements most of the interesting behaviour.
However, design decisions that change the relationships between agents might require changing that class.

Events are dispatched to a single Entity. This means that a transaction requires two (or more) events. (In some cases,
a single transaction will have one Entity on one side, and a chain of counter-parties with small orders.) This means
that we break accounting while the other events are still there to be processed. This means that if one wants to
run sanity checks, need to validate that the Event queue has no current events. Trying to ensure that transactions
are atomic makes the code too complex, since we would need the capacity to dispatch a single Event to two (+) Entity
objects.

I could rename "Entity" as "Agent,"but not all Entity objects are agents; they can be things like location or
commodity codes.

Client code is a bit of a kludge at this point. If the code migrates to a client-server model, we would need to
distinguish between a "client" on the server side, and the client-side version. All communication between the two are
messages, which is being enforced now. The Simulation events are in a different queue than operating system/network
message queues.

AI logic occurs at two levels:
(1) All agents have a behaviour within the simulation. Each type of agent will (eventually) have multiple AI rules to
work with.
(2) Strategic AI: an AI that emulates what a human player will do: make strategic decisions like changing the AI logic
for agents, or investing in new agents.

An agent can have a "do nothing" AI (easy to implement!) which allows a player to manually control the agent through
client messages. E.g., pick a planet to fly to, buy/sell at markets, etc. The client messages need to be converted to
Simulation event objects and placed into the Simulation Event queue.


"""

from bisect import insort_right
import weakref
import time

lastGID = 0
GEntityDict = weakref.WeakValueDictionary()
SIMULATIONID = None

class SimulationError(ValueError):
    """ Base class for all Simulation-thrown Exceptions"""
    pass


class Entity(object):
    def __init__(self, name='', ttype = ''):
        self.GID = AddEntity(self)
        self.Name = name
        self.Type = ttype
        # Set this to true when killing it.
        self.IsDead = False

    @staticmethod
    def GetEntity(GID):
        """
        Call this to get another entity.

        (Use this to wrap calls to look up GID's instead of directly accessing the global dict, in case it moves.)

        Throws a KeyError if the GID is not mapped, or marked as dead.

        Normally, dead entities should not be in the weakref dictionary, but the documentation says it is possible,
        so I am adding the validation.

        :param GID:
        :return:
        """
        global GEntityDict
        out = GEntityDict[GID]
        if out.IsDead:
            raise KeyError(f'Entity [{GID}] is marked as dead')
        return out


def AddEntity(entity):
    global lastGID
    global GEntityDict
    gid = lastGID
    GEntityDict[gid] = entity
    lastGID += 1
    return gid


def ResetEntities():
    """
    Called by Simulation initialisation
    :return:
    """
    global lastGID
    global GEntityDict
    global SIMULATIONID
    SIMULATIONID = None
    lastGID = 0
    GEntityDict = weakref.WeakValueDictionary()

class Event(object):
    """
    Event object.

    Queued based on calltime, and will be popped from queue once that time is hit.

    Once popped, the entity with GID will have its method event_{Action}(args) called.
    """
    def __int__(self, gid, action, calltime, repeat, args):
        self.GID = gid
        self.Action = action
        self.CallTime = calltime
        # If None, does not repeat. Otherwise, framework will reinsert with the CallTime incremented by Repeat.
        # I.e., if repeat = 1, repeat daily.
        self.Repeat = repeat
        self.args = args

    def __lt__(self, other):
        return self.CallTime < other.CallTime

    def __call__(self):
        try:
            entity = Entity.GetEntity(self.GID)
        except KeyError:
            # Entity is gone baby gone
            return
        meth = getattr(entity, f'event_{self.Action}')
        args = self.args
        return meth(*args)

def PostEvent(event):
    """
    Insert an Event object into the (global) event queue.

    (See the notes within Simulation about the event queue; we assume that there is only a single Simulation object
    within the process.)
    :param event: Event
    :return:
    """
    insort_right(Simulation.EventList, event)

class Client(object):
    last_ID = 0
    def __init__(self, simulation=None):
        self.ClientID = Client.last_ID
        Client.last_ID += 1
        self.Simulation = simulation

    def SendCommand(self, cmd):
        """
        :param cmd: ClientServerMsg
        :return:
        """
        cmd.ClientID = self.ClientID
        self.Simulation.ClientCommands.append(cmd)







class Simulation(Entity):
    """
    Simulation object, to be run by server (or main loop)

    Base class handles low level processing, and control of time. The entities within the simulation do all the work...
    """

    # Sorted list of simulation events
    # We assume that there is only a single Simulation object in existence. It is emptied when a new Simulation
    # object is created.
    # The only way to allow multiple simulations is to embed a reference to the simulation within each Entity, so
    # that it knows what Simulation to send events to. This can pose circular include issues that I want to avoid.
    EventList = []

    def __init__(self):
        # TimeMode can either be 'sim' or 'realtime'
        ResetEntities()
        super().__init__('simulation', 'simulation')
        global SIMULATIONID
        SIMULATIONID = self.GID
        self.TimeMode = 'sim'
        # Is the simulation paused (only matters for 'realtime' mode
        self.IsPaused = True
        # Simulation time, with 1.0 interval equalling 1 day.
        # In real time mode, updated at irregular intervals.
        self.Time = 0.
        # The # of seconds in a simulation day
        self.DayLength = 20.
        # Base time for time.monotonic(). Only set once TimeStart() command is given
        self.MonotonicBase = None
        # Dict of clients
        self.ClientDict = {}
        # Queue for commands from clients
        self.ClientCommands = []
        # Queue for messages to clients
        self.ClientMessages = []
        # List of entities in existence
        self.EntityList = []
        # Clear the "global" event Queue
        Simulation.EventList = []
        # Add ourselves to the list
        self.AddEntity(self)


    def AddEntity(self, entity):
        self.EntityList.append(entity)

    def GetEntity(self, GID):
        """
        Convenience function for callbacks that have the handle to the simulation
        :param GID:
        :return:
        """
        global GEntityDict
        return GEntityDict[GID]

    def Process(self):
        """
        Run a processing step. Only does one thing
        :return: bool
        """
        if len(self.ClientCommands) > 0:
            self.ProcessCommand()
            return True
        if len(self.ClientMessages) > 0:
            self.ProcessClientMessageQueue()
            return True
        # Process events...

        # Return False if nothing happened.
        return False

    def ProcessCommand(self):
        obj = self.ClientCommands.pop(0)
        if len(obj.args) == 0:
            obj.ServerCommand(self)
        else:
            obj.ServerCommand(self, *obj.args)

    def IncrementTime(self):
        """
        To be called by an external process that makes sures the calls are slightly staggered, so that we are not
        calling time.monotonic() for every single event.
        :return:
        """
        if self.TimeMode == 'realtime':
            if self.IsPaused:
                return
            if len(Simulation.EventList) > 0:
                first_event = Simulation.EventList[0].CallTime
                if self.Time >= first_event:
                    # If we have a current event, do not allow time to increment.
                    return
                new_base = time.monotonic()
                new_time = self.Time + (new_base - self.MonotonicBase) / self.DayLength
                if new_time < first_event:
                    self.Time = new_time
                    self.MonotonicBase = new_base
                else:
                    # Only step up to the first event.
                    self.Time = first_event
                    # For now, rebase to the current time. This means that the game clock slows down
                    # versus where it is supposed to be if processing had flowed smoothly.
                    # Possibly attempt to catch up - move the base backwards?
                    self.MonotonicBase = new_base
            else:
                oldbase = self.MonotonicBase
                self.MonotonicBase = time.monotonic()
                self.Time += (self.MonotonicBase - oldbase) / self.DayLength

        else:
            raise ValueError('Cannot call IncrementTime() in "sim" mode')

    def QueueMessage(self, msg):
        self.ClientMessages.append((msg.ClientID, msg))

    def ProcessClientMessageQueue(self):
        """ This would be replaced by client-server code."""
        clientID, msg = self.ClientMessages.pop()
        if len(msg.args) == 0:
            msg.ClientMessage(self.ClientDict[clientID])
        else:
            msg.ClientMessage(self.ClientDict[clientID], *msg.args)









