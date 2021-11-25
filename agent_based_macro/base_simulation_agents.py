import math

import agent_based_macro.entity
from agent_based_macro import simulation as simulation
from agent_based_macro.base_simulation import ProductionAgent, Inventory, Agent


class ProducerLabour(ProductionAgent):
    """
    A firm that produces output solely based on labour input.

    Eventually will have producers with commodity inputs. May migrate code to a base class

    Eventually, need to create AI classes that take over the decision logic, while things
    like production and wage paying are fixed.
    """

    def __init__(self, name, money_balance, location_id, commodity_id):
        super().__init__(name, money_balance, location_id)
        self.OutputID = commodity_id
        # Subclasses can override these values...
        # Penalty multiplier for firing. Fixed by law.
        self.WagePenalty = 5
        # This is a technological limit
        self.WorkersMax = 40
        # This is set by decision routines
        self.WorkersTarget = 0

        self.WorkersNextDay = 0
        # Inventory manager
        self.Inventory = Inventory()
        # Wages are not expensed, they are capitalised into inventory cost.
        # Once units are produced, balance from CapitalisedWages is transferred to InventoryCost.
        self.CapitalisedWages = 0
        self.IsEmployer = True

    def register_events(self):
        hiring_event = simulation.ActionEvent(self.GID, self.event_hiring, .05, 1.)
        hiring_event.add_data_request('JG_Wage', ('JG_Wage',))
        production_event = simulation.ActionEvent(self.GID, self.event_production, .5, 1.)
        return [(hiring_event, (0., 0.2)),
                (production_event, (.21, .99))]

    def event_hiring(self, *args):
        JG_wage = self.ActionData['JG_Wage']
        self.Wage = math.floor(1.1*JG_wage)
        self.TargetWorkers = math.floor((self.Money - self.ReserveMoney) / (5*self.Wage))
        self.TargetWorkers = min(self.TargetWorkers, self.WorkersMax)


    def event_production(self, *args):
        pass


class TravellingAgent(Agent):
    NoLocationID = None

    def __init__(self, name, coords, start_id, travelling_to_id, speed=2.):
        super().__init__(name)
        self.StartCoordinates = coords
        self.StartLocID = start_id
        self.StartTime = 0.
        self.Speed = speed
        self.TargetLocID = travelling_to_id
        target = agent_based_macro.entity.Entity.get_entity(travelling_to_id)
        self.TargetCoordinates = target.Coordinates
        self.ArrivalTime = 0.
        if self.StartCoordinates == target.Coordinates:
            # Already there
            self.StartLocID = travelling_to_id
        else:
            raise NotImplementedError('No support for spawning ship away from planet')

    def get_coordinates(self, ttime):
        """
        For now, the server will calculate all locations and update upon request.

        :param ttime: float
        :return:
        """
        if self.StartLocID == self.TargetLocID:
            return self.StartCoordinates
        else:
            if ttime > self.ArrivalTime:
                # TODO: Add an arrival event.
                # For now, just force the location data to update
                self.StartLocID = self.TargetLocID
                self.LocationID = self.TargetLocID
                self.StartCoordinates = self.TargetCoordinates
                return self.TargetCoordinates
            else:
                # progess is in [0,1]
                progress = (ttime - self.StartTime) / (self.ArrivalTime - self.StartTime)
                # Support N-dimensional spaces
                out = [s + progress * (t - s) for s, t in zip(self.StartCoordinates, self.TargetCoordinates)]
                return tuple(out)

    def start_moving(self, new_target, ttime):
        """
        Move to a new target (always a location, not an arbitrary point.
        :param new_target:
        :param ttime:
        :return:
        """
        coords = self.get_coordinates(ttime)
        self.StartLocID = self.LocationID
        self.StartTime = ttime
        self.StartCoordinates = coords
        self.LocationID = TravellingAgent.NoLocationID
        self.TargetLocID = new_target
        target_loc = agent_based_macro.entity.Entity.get_entity(new_target)
        self.TargetCoordinates = target_loc.Coordinates
        # Calculate distance
        dist = 0.
        for x1, x2 in zip(self.StartCoordinates, self.TargetCoordinates):
            dist += pow(x1 - x2, 2)
        dist = math.sqrt(dist)
        self.ArrivalTime = ttime + dist / self.Speed

    def get_representation(self):
        info = super().get_representation()
        if self.StartLocID == self.TargetLocID:
            # Easy case: not moving.
            coords = self.StartCoordinates
            location = self.StartLocID
        else:
            sim = simulation.get_simulation()
            ttime = sim.Time
            coords = self.get_coordinates(ttime)
            location = self.LocationID
        info['Coordinates'] = coords
        info['Location'] = location
        info['TravellingTo'] = self.TargetLocID
        return info