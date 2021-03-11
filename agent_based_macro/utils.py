

"""
Miscellaneous functions

"""


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

