"""
Miscellaneous functions and classes

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


import math
from typing import Type

G_LAST_JITTER = 0
# Create the jitter matrix. Done once on import
G_JITTER = []

for i in range(0, 10):
    G_JITTER.append(float(i) / 20.)
    G_JITTER.append(0.5 + float(i) / 20.)
G_JITTER.append(1.)


def reset_jitter():
    """
    Reset the jitter sequence. Only needed to ensure deterministic sequences (unit tests).
    :return: None
    """
    global G_LAST_JITTER
    G_LAST_JITTER = 0


def jitter_time(time_range):
    """
    Calculate a "jittered" time from a range. Used to spread out scheduled events.
    :param time_range: tuple
    :return: float
    """
    global G_LAST_JITTER
    global G_JITTER
    G_LAST_JITTER += 1
    if G_LAST_JITTER == len(G_JITTER):
        G_LAST_JITTER = 0
    return time_range[0] + G_JITTER[G_LAST_JITTER] * (time_range[1] - time_range[0])


class TimeSeries(object):
    """
    A time series class that is hopefully efficient in a world where time updates are somewhat random.

    For now, allow the time series to grow without limit. At some point, may need to cap memory usage.

    Keep the data as a list, and grow as needed.

    Note: assumes the time axis starts at 0., and throws an error for negative time. Why? A negative list index
    starts counting from end of list, messing everything up.

    If unbounded memory usage every became a worry, switch to keeping two chunks of data in the series, and
    whenever it would grow to a third, drop the first chunk, and then add a new empty chunk. Add an offset
    variable so that the index points to the truncated data list.
    """
    ChunkSize = 1024

    # TheSimulation has to keep the Time in sync with itself
    Time = 0.

    def __init__(self, freq=1., fill=None):
        self.Data = [fill] * TimeSeries.ChunkSize
        self.Frequency = freq
        self.FillValue = fill

    def get_index_and_grow(self, t, grow=True):
        """
        Return the index associated with time t.

        If grow=True, will grow the Data list to match where the index is.
        :param t: float
        :param grow: bool
        :return: int
        """
        res = math.floor(t / self.Frequency)
        if res < 0.:
            raise ValueError('TimeSeries does not support negative time')
        if grow and res >= len(self.Data):
            numchunks = math.ceil((1 + res - len(self.Data))/TimeSeries.ChunkSize)
            self.Data = self.Data + [self.FillValue]*TimeSeries.ChunkSize*numchunks
        return res

    def set(self, val, time=None):
        """
        Set the value of the TimeSeries at the index defined by the time.
        If the time value is not supplied, uses TimeSeries.Time
        :param val: float
        :param time: float
        :return:
        """
        if time is None:
            time = TimeSeries.Time
        idx = self.get_index_and_grow(time, grow=True)
        self.Data[idx] = val

    def add(self, val, time=None):
        """
        Add to the entry associated with the given time.

        If entry is None, effectively switches the fill value to 0., and then adds.

        :param val: float
        :param time: float
        :return: TimeSeries
        """
        if time is None:
            time = TimeSeries.Time
        idx = self.get_index_and_grow(time, grow=True)
        if self.Data[idx] is None:
            # Unset entry, treat as 0.
            self.Data[idx] = val
        else:
            self.Data[idx] += val
        return self

    def __iadd__(self, val):
        """
        Overload of the += operator. Uses TimeSeries.Time to index.
        :param val: float
        :return: TimeSeries
        """
        return self.add(val, time=TimeSeries.Time)

    def __isub__(self, val):
        """
        Overload of the -= operator. Uses TimeSeries.Time to index.
        :param val: float
        :return: TimeSeries
        """
        return self.add(-val, time=TimeSeries.Time)

    def get(self, time=None):
        """
        Get value from a time. If time is None, uses TimeSeries.Time

        Does not grow the series - if you attempt to access beyond the Data member, returns the FillValue.

        Throws an error on negative time.

        :param time: float
        :return: float
        """
        if time is None:
            time = TimeSeries.Time
        idx = self.get_index_and_grow(time, grow=False)
        if idx >= len(self.Data):
            return self.FillValue
        else:
            return self.Data[idx]


class BadKeywordError(ValueError):
    pass


class KwargManager(object):
    """
    A base class for classes that manage objects that use **kwargs - Actions, Events, Messages.

    For these classes, they have certain "types" of messages/actions/events/..., each with its own
    keyword parameters. Each class has its own list.

    The KwargManager creates a global list of accepted "types" and their associated arguments. The object
    will throw an exception if arguments are missing.

    The list of accepted "types" is registered during program startup. Extensions just make their additions
    after the base code registers its entries.

    The advantage of doing it this way:
    1) Errors immediately thrown if objects are created with missing arguments. Since this would normally
    only be found out when the object is unpacked, it is a lot easier to find the code that created the
    problem.
    2) Global registry of actions that can be compared to the non-existent documentation.
    3) Can identify if the same keyword is used twice.

    Note: subclasses need their own copies of the static class members. Methods access the correct
    static members by using type(self).<member>
    """
    GRequired = {}
    GKey = 'type'
    GDocstrings = {}
    GHandler = {}
    ErrorType = BadKeywordError

    def __init__(self, **kwargs):
        try:
            self.ObjectType = kwargs.pop(type(self).GKey)
        except KeyError:
            # Allow empty objects; they would blow up on processing, but whatever
            # Note: we need empty objects to not throw an exception so that we can add entries!
            if len(kwargs.keys()) == 0:
                self.ObjectType = None
                self.KWArgs = {}
                return
            else:
                raise type(self).ErrorType(f'Missing {type(self).GKey} in keywords: {kwargs}')
        try:
            for req in type(self).GRequired[self.ObjectType]:
                if req not in kwargs:
                    raise type(self).ErrorType(f'Missing required field {req} in {kwargs}')
        except KeyError:
            raise type(self).ErrorType(f'Unknown type {self.ObjectType}')

        self.KWArgs = kwargs

    def register_entry(self, key_name, handler, required, docstring=''):
        """
        Register a new type of entry. Need to do this on an object, so we know what class to insert the
        new entry into.

        :param key_name: str
        :param required: tuple
        :param docstring: str
        :return:
        """
        if key_name in type(self).GRequired:
            raise ValueError(f'key name {key_name} already registered for this class')
        type(self).GHandler[key_name] = handler
        type(self).GRequired[key_name] = required
        type(self).GDocstrings[key_name] = docstring

    def get(self):
        return self.ObjectType, self.KWArgs

    def run(self, *args):
        """
        Run the handler. Positional args are objects that are passed to the handler (Simulation...)
        :param args:
        :param kwargs:
        :return:
        """
        return type(self).GHandler[self.ObjectType](*args, self.ObjectType,  **self.KWArgs)


    def dump_registered(self): # pragma:no cover
        """
        Dump all the information registered in the subclass associated with the object.
        :return:
        """
        mytype: Type[KwargManager] = type(self)
        print(f'Type identifier: "{mytype.GKey}"')
        print('Registered Entries:')
        for key in mytype.GRequired:
            print(key, mytype.GRequired[key], mytype.GDocstrings[key])


