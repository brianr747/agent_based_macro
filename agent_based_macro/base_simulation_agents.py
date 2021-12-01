"""
This file contains agents (not all of them) for the base_simulation model structure.

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
import weakref

import agent_based_macro.entity
from agent_based_macro import simulation as simulation
from agent_based_macro.base_simulation import ProductionAgent, Inventory, Agent, ReserveType


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
        hiring_event.add_data_request('JG_Wage', request='JG_Wage')
        production_event = simulation.ActionEvent(self.GID, self.event_production, .5, 1.)
        sales_event = simulation.ActionEvent(self.GID, self.event_sales, .75, 1.)
        sales_event.add_data_request('Productivity', request="Productivity", commodity='Fud')
        sales_event.add_data_request('FudID', request='CommodityID', commodity='Fud')
        return [(hiring_event, (0., 0.2)),
                (production_event, (.21, .5)),
                (sales_event, (.02, .99))]

    def event_hiring(self, *args):
        JG_wage = self.ActionData['JG_Wage']
        self.Wage = math.floor(1.1*JG_wage)
        self.TargetWorkers = math.floor((self.Money - self.ReserveMoney) / (6*self.Wage))
        self.TargetWorkers = min(self.TargetWorkers, self.WorkersMax)


    def event_production(self, *args):
        """
        This event represents automatic events - "follows economic laws" - and contains no behavioural steps.
        It possibly could be migrated to the super class.

        The two actions are: pay wages, then produce goods. The wages are capitalised into the inventory
        cost of the production.

        :param args:
        :return:
        """
        payment = self.get_daily_wage_bill()
        self.time_series_set('wage_payment', payment)
        self.add_action(action_type='PayWages', payment=payment)
        # JG Production
        self.add_action(action_type='ProductionLabour', commodity='Fud', num_workers=self.WorkersActual,
                        payment=payment)

    def event_sales(self, *args):
        # for now, just sell at fixed price...
        self.time_series_set('money', self.Money)
        fud_id = self.ActionData['FudID']
        unit_cost = self.unit_cost(fud_id)
        # Aim for a 10% profit margin
        amount = math.ceil(self.Inventory[fud_id].Amount*.99)
        if amount > 0:
            self.add_action(action_type='AddNamedSell', name='production', commodity_id=fud_id,
                            price=unit_cost * 1.1, amount=amount)


class TravellingAgent(Agent):
    NoLocationID = None

    def __init__(self, name, coords, start_id, travelling_to_id, speed=2., money_balance=0):
        super().__init__(name, money_balance=money_balance)
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
            self.LocationID = self.StartLocID
        else:
            raise NotImplementedError('No support for spawning ship away from planet')

    def get_coordinates(self, ttime):
        """
        For now, the server will calculate all locations and update upon request.

        :param ttime: float
        :return:
        """
        if self.StartLocID == self.TargetLocID:
            self.LocationID = self.StartLocID
            return self.StartCoordinates
        else:
            if ttime > self.ArrivalTime:
                # TODO: Add an arrival event.
                # For now, just force the location data to update
                self.StartLocID = self.TargetLocID
                self.LocationID = self.TargetLocID
                self.LocationID = self.StartLocID
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
        info['Money'] = self.Money
        info['Inventory'] = self.Inventory.get_representation_info()
        return info

    def event_buy(self, **kwargs):
        commodity_id = kwargs['commodity_id']
        price = kwargs['price']
        amount = kwargs['amount']
        self.add_action(action_type='BuyNoKeep', commodity_id=commodity_id, price=price, amount=amount)

    def event_sell(self, **kwargs):
        commodity_id = kwargs['commodity_id']
        price = kwargs['price']
        amount = kwargs['amount']
        self.add_action(action_type='SellNoKeep', commodity_id=commodity_id, price=price, amount=amount)


class JobGuarantee(ProductionAgent):
    """
    Although ech planet has its own agent, transactions use the central government money account.
    """

    def __init__(self, location_id, central_gov_id, job_guarantee_wage, num_workers=0):
        super().__init__(money_balance=0, name='JobGuarantee', location_id=location_id)
        self.CentralGovID = central_gov_id
        self.WorkersActual = num_workers
        self.Employer = True
        self.Inventory = Inventory()
        self.Wage = job_guarantee_wage
        self.IsCentralGovernment = True
        # Will find the HouseholdGID later...
        self.HouseholdGID = None
        self.EmployerDict = weakref.WeakValueDictionary()

    def spend_money(self, amount, from_reserve=ReserveType.NONE):
        self.get_entity(self.CentralGovID).spend_money(amount)

    def receive_money(self, amount):
        self.get_entity(self.CentralGovID).receive_money(amount)

    def find_employers(self):
        """
        Find all the employers on a location. Call during initialisation step.

        Once we can have creation/destruction of employers, will need to update live.
        :return:
        """
        self.EmployerDict = weakref.WeakValueDictionary()
        sim = self.get_entity(agent_based_macro.entity.SIMULATION_ID)
        for ent in sim.EntityList:
            if ent.GID == self.GID:
                continue
            if ent.Type == 'agent' and ent.LocationID == self.LocationID:
                if ent.IsEmployer:
                    self.EmployerDict[ent.GID] = ent

    def register_events(self):
        """

        :return: list
        """
        payment_event = simulation.ActionEvent(self.GID, self.event_production, 0.02, 1.)
        labour_event = simulation.ActionEvent(self.GID, self.event_labour_market, 0., 1.)
        return [(payment_event, (0.04, 0.1)),
                (labour_event, (0., .038)),]

    def event_labour_market(self, *args):
        """
        Labour market simulation for a planet. Tie to the Job Guarantee for simplicity, but it handles all
        movements.

        There are two strategies that could be used: aggregated, versus a per-household search model.

        The search model is actually simple: create a number of worker entities, and cycle through them. They will
        drift at random towards better jobs. The problem with that it is inherently going to be random, and it is
        easier to test a deterministic one. Instead, I will start with a deterministic drift algorithm. This should
        be more efficient if there are a very large number of "worker units."

        Note: for simplicity, do all processing inside this function, instead of using Actions.
        """
        if len(self.EmployerDict) == 0:
            self.find_employers()
        # Do in two passes.
        # 1) Handle firing, if any. Find employers looking for workers.
        # 2) If there are hiring employers, and there are workers in the Job Guarantee, then some workers will
        #    drift to the employers.
        # Need to add the possibility of workers jumping from one employer to another. Since all wages are equal for
        # now, can defer adding that.
        employers_hiring = []
        total_hires = 0
        # Calculate the total population - should not be changing!
        total_population = self.WorkersActual
        # Firing pass. Workers go to Job Guarantee immediately.
        employer: Agent
        for employer_id, employer in self.EmployerDict.items():
            total_population += employer.WorkersActual
            hires = employer.TargetWorkers -  employer.WorkersActual
            # If hires = 0, no changes.
            if hires < 0:
                if employer.TargetWorkers < 0:
                    raise ValueError('Cannot have negative workers')
                # You're fired! Since hires is negative, the JobGuarantee.WorkersActual is increasing.
                self.WorkersActual -= hires
                employer.WorkersActual = employer.TargetWorkers
            elif hires > 0:
                employers_hiring.append(employer_id)
                total_hires += hires
        # Pass two: if there are workers in the JobGuarantee, they go to private workers.
        # TODO: Add wage logic. Right now, since wages are fixed, do not need to take wages into account.
        # To slow down dynamics slightly, assume that only 1/3 of the JobGuarantee workers can be hired in a day,
        # rounded up.
        actual_hires = min(total_hires, math.ceil(float(self.WorkersActual)/3.))
        if actual_hires > 0:
            # Since not every employer can get their desired workers, be unfair and give rounded up portions to
            # employers in order. This means that employers at the end of the list will miss out if there are fractions.
            assignment_fraction = float(actual_hires)/float(total_hires)
            for employer_id in employers_hiring:
                employer = self.EmployerDict[employer_id]
                num_hired = math.ceil(assignment_fraction*(employer.TargetWorkers-employer.WorkersActual))
                # No rounding above the number of workers to be hired
                num_hired = min(num_hired, actual_hires)
                actual_hires -= num_hired
                employer.WorkersActual += num_hired
                self.WorkersActual -= num_hired
        # Calculate the unemployment rate
        unemployment = float(self.WorkersActual)/float(total_population)
        self.time_series_set('unemployment', unemployment)

    def event_production(self, *args):
        """
        Do the production operation.

        This method has been switched over to use Actions.

        Actions triggered
        (i) PayWages
        (ii) ProductionLabour
        (iii) DelayEvent - call event_set_orders() with a delay.

        (Note: Will need to create a DelayEvent as an ActionEvent.

        :param args:
        :return:
        """
        # Since the HouseholdSector and central government are indestructible (I hope), this transfer will always
        # be valid. (Normally, need to validate existence of all entities.)
        payment = self.get_daily_wage_bill()
        self.add_action(action_type='PayWages', payment=payment)
        # JG Production
        self.add_action(action_type='ProductionLabour', commodity='Fud', num_workers=self.WorkersActual,
                        payment=payment)
        # The data needed by event_set_orders: the productivity of Fud production, as well as the ID of Fud.
        # Note: Should save the FoodID in the class, since needed every time.
        data_queries = {
            'Productivity': {'request': 'Productivity', 'commodity': 'Fud'},
            'FudID': {'request': 'CommodityID', 'commodity': 'Fud'}
        }
        self.add_action(action_type='QueueActionEventWithDelay', call_back=self.event_set_orders, delay=.1,
                        input_data_dict=data_queries)

    def event_set_orders(self, *args):
        """
        Set up buy/sell orders.

        Keep it as simple as possible, to allow the loop to close.

        Currently, sets up three named orders
        (1) 'floor': A floor price bid for 300 units.
        (2) 'production': Sale of most production at 110% of production cost.
        (3) 'emergency': sale of remainder at 150% of production cost.
        :return:
        """
        food_id = self.ActionData['FudID']
        productivity = self.ActionData['Productivity']
        production_price = self.Wage / productivity
        # Create a floor
        price = production_price * .95
        amount = 300
        self.add_action(action_type='AddNamedBuy', name='floor', commodity_id=food_id, price=price, amount=amount)
        available = self.Inventory[food_id].Amount - self.Inventory[food_id].Reserved
        production_amount = int(available*0.7)
        self.add_action(action_type='AddNamedSell', name='production', commodity_id=food_id,
                        price=production_price * 1.1, amount=production_amount)
        self.time_series_set('production', production_price * 1.1 * production_amount)
        remainder = available - production_amount
        self.add_action(action_type='AddNamedSell', name='emergency', commodity_id=food_id, price=production_price * 1.5,
                        amount=remainder)
        self.time_series_set('emergency', production_price * 1.5 * remainder)