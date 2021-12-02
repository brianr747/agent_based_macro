"""
File holding error classes


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

class InvalidActionArguments(ValueError):
    pass