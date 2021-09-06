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
import time
import math
from abc import ABC, abstractmethod

import agent_based_macro.entity
import agent_based_macro.utils as utils
from agent_based_macro.entity import EntityDoesNotExist, EntityDead, Entity, reset_entities, ActionDataRequest, \
    ActionCallback, ActionQueueEventWithDelay

GSimulation = None


def get_simulation():
    """
    We only allow a single Simulation object to exist.
    :return:
    """
    global GSimulation
    return GSimulation


class SimulationError(ValueError):
    """ Base class for all Simulation-thrown Exceptions"""
    pass


class Event(object):
    """
    Event object.

    Queued based on calltime, and will be popped from queue once that time is hit.

    Once popped, the entity with GID will have its method event_{Callback}(args) called.
    """
    def __init__(self, gid, callback, calltime, repeat, *args):
        self.GID = gid
        self.Callback = callback
        self.CallTime = calltime
        # If None, does not repeat. Otherwise, framework will reinsert with the CallTime incremented by Repeat.
        # I.e., if repeat = 1, repeat daily.
        self.Repeat = repeat
        self.args = args

    def __lt__(self, other):
        return self.CallTime < other.CallTime

    def __call__(self):
        # This might throw an error, if the entity is gone. Calling Simulation will eat this.
        # It needs to know so that the Event is not put back in the queue if it's a repeater...
        entity = Entity.get_entity(self.GID)
        # meth = getattr(entity, f'event_{self.Action}')
        # args = self.args
        return self.Callback(*self.args)


def queue_event(event):
    """
    Insert an Event object into the (global) event queue.

    (See the notes within Simulation about the event queue; we assume that there is only a single Simulation object
    within the process.)
    :param event: Event
    :return:
    """
    insort_right(Simulation.EventList, event)


class ActionEvent(Event):
    """
    An ActionEvent is a type of Event that is treated specially.

    (1) A list of requested data is specified in the ActionEvent. The simulation will
    fetch the requested data.
    (2) The action

    """
    def __init__(self, gid, callback, calltime, repeat, *args):
        super().__init__(gid, callback, calltime, repeat, args)
        self.DataRequests = []

    def add_data_request(self, name, *args):
        """
        Add a data request that will have data stored under "name"
        :param name: str
        :param args:
        :return:
        """
        self.DataRequests.append((name, *args))


class Client(object):
    last_ID = 0

    def __init__(self, simulation=None):
        self.ClientID = Client.last_ID
        Client.last_ID += 1
        self.Simulation = simulation
        self.Time = None
        self.DayLength = 0.
        # When did the client last get a time response (as per time.monotonic()). Used to estimate time.
        self.LastResponseMonotonic = 0.

    def send_command(self, cmd):
        """
        :param cmd: ClientServerMsg
        :return:
        """
        cmd.ClientID = self.ClientID
        self.Simulation.ClientCommands.append(cmd)


class Simulation(ABC, Entity):
    """
    Simulation object, to be run by server (or main loop)

    This is an abstract base class. Subclasses must override the @abstractmethod

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
        reset_entities()
        super().__init__('simulation', 'simulation')
        agent_based_macro.entity.SIMULATION_ID = self.GID
        self.TimeMode = 'sim'
        # Is the simulation paused (only matters for 'realtime' mode
        self.IsPaused = True
        # Simulation time, with 1.0 interval equalling 1 day.
        # In real time mode, updated at irregular intervals.
        self.Time = 0.
        # The # of seconds in a simulation day
        self.DayLength = 8.
        # Base time for time.monotonic(). Only set once TimeStart() command is given
        self.MonotonicBase = None
        # Reset the jitter so that the simulation creation is "deterministic"
        utils.reset_jitter()
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
        self.add_entity(self)
        # Set the global GSimulation reference to point to this simulation
        global GSimulation
        GSimulation = self
        # How many Actions can be processed?
        self.MaxActionLimit = 100

    def add_entity(self, entity):
        """
        Add an Entity to the simulation, and register events

        :param entity: Entity
        :return:
        """
        self.EntityList.append(entity)
        try:
            event_list = entity.register_events()
        except AttributeError:
            # Doesn't have a register_events() method
            return
        for (event, first_time) in event_list:
            # first time is a range for the first event; use the jitter_time() function to
            # put it at a "semi-random" point within the interval. This way we do not have a huge spike of
            # events during the day. All actions for an entity are done at the same simulation time, in
            # specified order. This way Entities can ensure a phased logic.
            actual_time = utils.jitter_time(first_time)
            if actual_time < self.Time:
                actual_time += math.floor(self.Time)
                # Corner case
                if actual_time < self.Time:
                    actual_time += 1.
            event.CallTime = actual_time
            queue_event(event)

    def queue_event_delay(self, gid, action, delay, *args):
        """
        Queue an event with a delay versus current time. Does not repeat.
        :param gid: int
        :param action:
        :param delay: int
        :param args:
        :return:
        """
        event = Event(gid, action, self.Time + delay, None, *args)
        queue_event(event)

    def queue_action_event_delay(self, gid, callback, delay, data_dict):
        event = ActionEvent(gid, callback, self.Time + delay, repeat=None)
        for k,v in data_dict.items():
            event.add_data_request(k, v)
        queue_event(event)

    def get_entity(self, gid):
        """
        Convenience function for callbacks that have the handle to the simulation
        :param gid:
        :return:
        """
        return agent_based_macro.entity.GEntityDict[gid]

    def process(self):
        """
        Run a processing step. Only does one thing
        :return: bool
        """
        if len(self.ClientCommands) > 0:
            self.process_command()
            return True
        if len(self.ClientMessages) > 0:
            self.process_client_message_queue()
            return True
        # Process events...
        if len(self.EventList) > 0:
            if self.Time >= self.EventList[0].CallTime:
                event = self.EventList.pop(0)
                try:
                    if isinstance(event, ActionEvent):
                        self.process_action_event(event)
                    else:
                        event()
                except EntityDoesNotExist:
                    # The Entity disappeared. Do nothing (so is no longer REPEATed).
                    # Return True, since we did have an Event in the queue.
                    return True
                except EntityDead:
                    # Not entirely sure whether we should allow dead entities.
                    # Only reason I see is to hold information to display to clients.
                    raise NotImplementedError('Dead entity handling not implemented')
                if event.Repeat is not None:
                    if event.Repeat < 0.01:
                        raise ValueError('Cannot have so close a repeat value!')
                    event.CallTime = event.CallTime + event.Repeat
                    queue_event(event)

                return True
        # Return False if nothing happened.
        return False

    def process_action_event(self, action_event):
        """
        Special processing for an ActionEvent.

        ActionEvents are handled differently that regular events.

        (1) The ActionEvent specifies data to be gathered before calling the callback
        (2) The callback is called.
        (3) During the callback, the entity uses the gathered data, and fills in a queue of Actions
            (e.g,, transactions) that are to be undertaken.
        (4) The list of actions is then processed, with the processing handled by simulation subclasses.
        (5) The Entity can do multi-stage actions by adding ActionDataRequests (that add/overwrite data)
            and new ActionCallbacks. Those callbacks are then called. This can repeat up until
            self.MAxActionLimit Actions are performed (at which point, the assumption is that there is an error).

        :param action_event: ActionEvent
        :return:
        """
        # This can throw an error if the entity no longer exists, but it needs to be caught by Process() method.
        ent: Entity = self.get_entity(action_event.GID)
        # Clear the action data members
        # Data that is requested before the callback
        ent.ActionData = {}
        # Actions requested by the Entity
        ent.ActionQueue = []
        for name, data_args in action_event.DataRequests:
            ent.ActionData[name] = self.get_action_data(ent, data_args)
        # Run the callback
        action_event.Callback(action_event.args)
        # Then, do the requested actions.
        cnt = 0
        while len(ent.ActionQueue) > 0:
            cnt += 1
            if cnt == self.MaxActionLimit:
                # Enforce a limit in case an infinite recursion is hit
                raise ValueError(f'Entity spawned more than {self.MaxActionLimit} Actions!')
            action = ent.ActionQueue.pop(0)
            try:
                action.do_action(self, ent)
            except NotImplementedError:
                # Simulation-level action handlers for data, or whatever else.
                if isinstance(action, ActionDataRequest):
                    ent.ActionData[action.Name] = self.get_action_data(ent, action.args)
                else:
                    self.process_action(ent, action)

    @abstractmethod
    def process_action(self, agent, action):
        """
        Subclass simulations need to deal with simulation-specific actions.

        :param action: Action
        :param agent: Agent
        :return:
        """
        pass

    @abstractmethod
    def get_action_data(self, agent, *args):
        """
        Function that needs to be overriden by subclasses to do data fetching. Each simulation will
        have to work out its own protocol.

        :param agent: Agent
        :param args:
        :return: object
        """
        pass

    def process_command(self):
        obj = self.ClientCommands.pop(0)
        if len(obj.args) == 0:
            obj.server_command(self)
        else:
            obj.server_command(self, *obj.args)

    def increment_time(self):
        """
        To be called by an external process that makes sures the calls are slightly staggered, so that we are not
        calling time.monotonic() for every single event.

        Note: must increment the static time member for the TimeSeries class to keep in sync
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
                old_base = self.MonotonicBase
                self.MonotonicBase = time.monotonic()
                self.Time += (self.MonotonicBase - old_base) / self.DayLength
            # Keep the TimeSeries time sync'd to this time.
            utils.TimeSeries.Time = self.Time
        else:
            raise ValueError('Cannot call IncrementTime() in "sim" mode')

    def queue_message(self, msg):
        self.ClientMessages.append((msg.ClientID, msg))

    def process_client_message_queue(self):
        """ This would be replaced by client-server code."""
        client_id, msg = self.ClientMessages.pop()
        if len(msg.args) == 0:
            msg.client_message(self.ClientDict[client_id])
        else:
            msg.client_message(self.ClientDict[client_id], *msg.args)
