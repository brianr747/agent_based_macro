"""
Entity management. We generally store entity ID's (GID = Global ID), and only fetch the actual entity
object when we need it. The Simulation class should only have a single reference to entity objects
within it. When that copy is deleted, the Entity disappears, freeing up memory.

The lookup dictionary is a weakref dictionary, and so if other references to the Entity object disappear,
the weak reference is not enough to prevent the cleanup.

(Since there are no entities being deleted, this memory cleanup has not really be an issue.)

I moved this class and associated helper functions to a stand alone file since many other basic objects
may want to be Entity objects. This way they can safely import the Entity class without circular import
problems (or so I hope).

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

import weakref

from agent_based_macro.data_requests import ActionDataRequestHolder
from agent_based_macro.errors import InvalidActionArguments

lastGID = 0
GEntityDict = weakref.WeakValueDictionary()
SIMULATION_ID = None


class EntityDoesNotExist(KeyError):
    pass


class EntityDead(KeyError):
    pass


class Entity(object):
    def __init__(self, name='', ttype=''):
        self.GID = add_entity(self)
        self.Name = name
        self.Type = ttype
        # Set this to true when killing it.
        self.IsDead = False
        self.ActionQueue = []
        self.ActionData = {}

    def get_representation(self):
        """
        Override to give entity specific string serialisation information.

        :return: dict
        """
        return {'GID': self.GID,
                'Name': self.Name,
                'Type': self.Type}

    def add_action(self, action_type, **kwargs):
        """

        Add an Action to the ActionQueue. Arguments must be specified as keyword arguments.

        :type action_type: str
        """
        kwargs['action_type'] = action_type
        self.ActionQueue.append(Action(**kwargs))


    @staticmethod
    def get_entity(gid):
        """
        Call this to get another entity.

        (Use this to wrap calls to look up GID's instead of directly accessing the global dict, in case it moves.)

        Throws a KeyError if the GID is not mapped, or marked as dead.

        Normally, dead entities should not be in the weakref dictionary, but the documentation says it is possible,
        so I am adding the validation.

        :param gid:
        :return: Entity
        """
        try:
            out = GEntityDict[gid]
        except KeyError:
            raise EntityDoesNotExist(f'Entity with GID={gid} does not exist')
        if out.IsDead:
            raise EntityDead(f'Entity with GID={gid} is marked as dead')
        return out

    @staticmethod
    def get_simulation():
        """
        Get the Simulation object.

        (Should not be called on "client-side" code, but is needed within the Simulation itself.)

        :return: Simulation
        """
        return Entity.get_entity(SIMULATION_ID)


def add_entity(entity):
    global lastGID
    global GEntityDict
    gid = lastGID
    GEntityDict[gid] = entity
    lastGID += 1
    return gid


def reset_entities():
    """
    Called by Simulation initialisation
    :return:
    """
    global SIMULATION_ID
    global lastGID
    global GEntityDict
    SIMULATION_ID = None
    lastGID = 0
    GEntityDict = weakref.WeakValueDictionary()


class Action(object):
    """
    Actions that are requested by Entities during the processing loop.

    For a generic Action, need to specify arguments as KeyWord arguments, with action_type used to handle the
    callback.
    """
    # List of requires fields by action_type
    GRequired = {}
    # Global holds the handlers by action_type
    GHandlers = {}
    # Docstrings for Actions
    GDocStrings = {}

    def __init__(self, **kwargs):
        self.KWArgs = kwargs
        self.check_valid()

    def do_action(self, sim, agent):
        """
        DEPRECATED. Implementation is now within the Simulation subclass (or external handlers that are
        patched in). Leaving this for now...


        :return:
        """
        raise NotImplementedError('do_action() not implemented in this class')

    def check_valid(self):
        """
        Does the Action have the required arguments?
        :return:
        """
        try:
            action_type = self.KWArgs['action_type']
        except KeyError:
            raise InvalidActionArguments('Action arguments must include action_type variable')
        try:
            required = Action.GRequired[action_type]
        except KeyError:
            raise InvalidActionArguments(f'action_type "{action_type}" is not registered')
        for arg in required:
            if arg not in self.KWArgs:
                raise InvalidActionArguments(f'missing required argument {arg} for Action {action_type}')


    @staticmethod
    def add_action_type(action_type, handler, required, docstring=''):
        """

        :param action_type: str
        :param handler: function
        :param required: str
        :param docstring: str
        :return:
        """
        show_warning = action_type in Action.GRequired
        Action.GRequired[action_type] = required
        Action.GHandlers[action_type] = handler
        Action.GDocStrings[action_type] = docstring
        if show_warning:
            # This might be upgraded to an error..
            raise Warning(f'action_type {action_type} was overwritten')



class ActionDataRequest(Action):
    """
    Request data for the Entity
    """
    def __init__(self, data_request=None, **kwargs):
        super().__init__(**kwargs)
        self.DataRequest = ActionDataRequestHolder(data_request)

    def do_action(self, sim, agent):
        raise NotImplementedError('Need to figure out how data request works')

    def check_valid(self):
        'Always valid if constructor does not blow up'
        pass


class ActionCallback(Action):
    """
    Request calling another callback (for multi-stage actions).
    """
    def __init__(self, callback, **kwargs):
        super().__init__(**kwargs)
        self.Callback = callback

    def do_action(self, sim, agent):
        """
        Call the associated callback.

        parameters = <callback>(agent, *self.args)
        :param sim:
        :param agent:
        :return:
        """
        self.Callback(agent, **self.KWArgs)

    def check_valid(self):
        'Always valid if constructor does not blow up'
        pass


class ActionQueueEventWithDelay(Action):
    """
    Put an Event with a delay into the simulation event queue.
    """
    def __init__(self, callback, delay, data_dict, **kwargs):
        super().__init__(**kwargs)
        self.callback = callback
        self.delay = delay
        self.data_dict = ActionDataRequestHolder(data_dict)
        self.KWArgs = kwargs

    def do_action(self, sim, agent):
        """
        Call the Simulation queue_event_delay()

        :param sim: Simulation
        :param agent: Agent
        :return:
        """
        sim.queue_event_delay(agent.GID, self.callback, self.delay, self.data_dict)

    def check_valid(self):
        'always valid if constructor runs'
        pass