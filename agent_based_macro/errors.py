"""
File holding error classes
"""


class SimulationError(ValueError):
    """ Base class for all Simulation-thrown Exceptions"""
    pass


class NoMoneyError(SimulationError):
    pass


class NoFreeMoneyError(SimulationError):
    """Attempting to spend beyond free money capacity"""
    pass


class ReserveError(SimulationError):
    """ Attempting to reduce reserve to a negative amount"""
    pass

class CommodityReserveError(SimulationError):
    """
    Attempting to reserve more commodity than exists
    """
    pass