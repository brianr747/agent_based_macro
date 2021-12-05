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

from agent_based_macro.errors import InvalidActionArguments
from agent_based_macro.utils import KwargManager

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


class Action(KwargManager):
    """
    Actions that are requested by Entities during the processing loop.

    For a generic Action, need to specify arguments as KeyWord arguments, with action_type used to handle the
    callback.
    """
    GRequired = {}
    GKey = 'action_type'
    GDocstrings = {}
    GHandler = {}
    ErrorType = InvalidActionArguments

    @staticmethod
    def add_action_type(action_type, handler, required, docstring=''):
        """

        :param action_type: str
        :param handler: function
        :param required: str
        :param docstring: str
        :return:
        """
        obj = Action()
        obj.register_entry(action_type, handler, required, docstring)

