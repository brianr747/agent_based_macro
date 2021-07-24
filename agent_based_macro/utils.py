

"""
Miscellaneous functions and classes

"""


import math



GLastJitter = 0
# Create the jitter matrix. Done once on import
GJitter = []

for i in range(0,10):
    GJitter.append(float(i)/20.)
    GJitter.append(0.5 + float(i)/20.)
GJitter.append(1.)

def reset_jitter():
    """
    Reset the jitter sequence. Only needed to ensure deterministic sequences (unit tests).
    :return: None
    """
    global GLastJitter
    GLastJitter = 0


def jitter_time(time_range):
    """
    Calculate a "jittered" time from a range. Used to spread out scheduled events.
    :param time_range: tuple
    :return: float
    """
    global GLastJitter
    global GJitter
    GLastJitter += 1
    if GLastJitter == len(GJitter):
        GLastJitter = 0
    return  time_range[0] + GJitter[GLastJitter]*(time_range[1] - time_range[0])


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

    def GetIndexAndGrow(self, t, grow=True):
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

    def Set(self, val, time=None):
        """
        Set the value of the TimeSeries at the index defined by the time.
        If the time value is not supplied, uses TimeSeries.Time
        :param val: float
        :param time: float
        :return:
        """
        if time is None:
            time = TimeSeries.Time
        idx = self.GetIndexAndGrow(time, grow=True)
        self.Data[idx] = val

    def Add(self, val, time=None):
        """
        Add to the entry associated with the given time.

        If entry is None, effectively switches the fill value to 0., and then adds.

        :param val: float
        :param time: float
        :return: TimeSeries
        """
        if time is None:
            time = TimeSeries.Time
        idx = self.GetIndexAndGrow(time, grow=True)
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
        return self.Add(val, time=TimeSeries.Time)

    def __isub__(self, val):
        """
        Overload of the -= operator. Uses TimeSeries.Time to index.
        :param val: float
        :return: TimeSeries
        """
        return self.Add(-val, time=TimeSeries.Time)

    def Get(self, time=None):
        """
        Get value from a time. If time is None, uses TimeSeries.Time

        Does not grow the series - if you attempt to access beyond the Data member, returns the FillValue.

        Throws an error on negative time.

        :param time: float
        :return: float
        """
        if time is None:
            time = TimeSeries.Time
        idx = self.GetIndexAndGrow(time, grow=False)
        if idx >= len(self.Data):
            return self.FillValue
        else:
            return self.Data[idx]






