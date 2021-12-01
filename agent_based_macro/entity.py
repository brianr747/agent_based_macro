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

    def add_action(self, **kwargs):
        """
        Add an Action to the ActionQueue
        :param args:
        :return:
        """
        action_type=kwargs['action_type']
        if action_type == 'DataRequest':
            self.ActionQueue.append(ActionDataRequest(**kwargs))
        elif action_type == 'Callback':
            self.ActionQueue.append(ActionCallback(**kwargs))
        elif (action_type == 'QueueEventWithDelay') or (action_type=='QueueActionEventWithDelay'):
            if action_type == 'QueueActionEventWithDelay':
                print('DEPRECATED QueueActionEventWithDelay')
            # Create an ActionEVent that is delayed.
            call_back = kwargs.pop('call_back')
            delay = kwargs.pop('delay')
            if 'input_data_dict' in kwargs:
                input_data_dict = kwargs.pop('input_data_dict')
            else:
                input_data_dict = {}
            self.ActionQueue.append(ActionQueueEventWithDelay(call_back, delay, input_data_dict,
                                                              **kwargs))
        else:
            # Generic Action to be handled by the Simulation subclass
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
    """
    def __init__(self, **kwargs):
        self.KWArgs = kwargs

    def do_action(self, sim, agent):
        """
        A method that may be overridden by subclasses to implement actions.

        If not overridden, the Simulation class has to have a handler for the Action.args.

        For simpler simulations, it may be easier to have the Simulation deal with the
        action implementation. However, as the number of Action types rises, pushing the
        code to subclasses of Action will be more modular. It will also allow users to
        more easily hook modifications into existing classes, since they just create
        a new Action and handler, and do not need to touch the core classes.

        :param sim: Simulation
        :param agent: Agent
        :return:
        """
        raise NotImplementedError('do_action() not implemented in this class')


class ActionDataRequest(Action):
    """
    Request data for the Entity (for later Actions
    """
    def __init__(self, name, **kwargs):
        super().__init__(**kwargs)
        self.Name = name


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