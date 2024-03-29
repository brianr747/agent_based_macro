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
