"""
OK, this file is badly named.


This file defines the core of a possible simulation structure. If you want to change this structure, will need to figure
out how to extend it in the direction desired.

There are a number of entities that are always in the simulation.

- CentralGovernment: Defines the monetary unit, has a monetary balance that is the negative of the money holdings
of all other entities. Imposes taxes. Note: monetary unit is integer. Can divide by 100 for display purposes if desired.
- Locations: Most entities are tied to a specific location, and that limits what they can interact with.
- Commodities: A type of good.
- Markets: Where transactions happen. Has buy/sell queues. For a particular good at a particular location.
- Firm: a business that usually has a parent. Normally tied to a location, but some are mobile.
A HQ is a firm without a parent, it pays a dividend to a home location.
- Households: Household sector that lives at a location. Does an aggregated purchase of consumption goods. (Currently
directly from markets, but would be retailers if they are created as a class).

I am not going to worry about making this too abstract to handle other potential configurations.

Within this base class, all transactions occur within the same location. Need extensions to allow transport of goods
between locations.

Note: Agent subclasses are meant to be moved to base_simulation_agents.py

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
import enum
import math

import agent_based_macro.entity
from agent_based_macro import errors
from agent_based_macro.entity import Entity, Action
from agent_based_macro.orders import SellOrder, BuyOrder, MarketBase, OrderType
from agent_based_macro.errors import NoMoneyError, NoFreeMoneyError, ReserveError
import agent_based_macro.simulation as simulation
from agent_based_macro.data_requests import ActionDataRequestHolder


class Location(agent_based_macro.entity.Entity):
    def __init__(self, name):
        super().__init__(name=name, ttype='location')
        # Duh!
        self.LocationID = self.GID
        self.EntityList = []
        self.MarketList = []

    def initialise(self):
        """
        Set up the entity list for the location. Meant to be called near the end of
        the simulation initialisation step. Once dynamic agent creation is allowed, will need to maintain
        as changes made.
        :return:
        """
        self.EntityList = []
        sim = agent_based_macro.entity.Entity.get_entity(agent_based_macro.entity.SIMULATION_ID)
        # For simplicity, do this in a loop
        for ent in sim.EntityList:
            if ent.GID == self.GID:
                continue
            if ent.IsDead:
                continue
            if hasattr(ent, 'LocationID') and ent.LocationID == self.LocationID:
                self.EntityList.append(ent.GID)

    def generate_market_list(self):
        self.MarketList = []
        for entID in self.EntityList:
            ent = self.get_entity(entID)
            if ent.Type == 'market':
                self.MarketList.append(entID)

    def get_representation(self):
        info = super().get_representation()
        if len(self.MarketList) == 0:
            self.generate_market_list()
        info['MarketList'] = self.MarketList
        return info


class Planet(Location):
    def __init__(self, name, coords):
        super().__init__(name)
        self.Coordinates = coords
        self.ProductivityDict = {}

    def get_representation(self):
        info = super().get_representation()
        info['Coordinates'] = self.Coordinates
        return info


class ReserveType(enum.Enum):
    NONE = 0
    ORDERS = 1
    TAX = 2
    WAGES = 3


class InventoryInfo(object):
    def __init__(self, commodity_id):
        self.CommodityID = commodity_id
        self.Amount = 0
        self.Cost = 0
        self.Reserved = 0

    def add_inventory(self, amount, cost):
        """
        Add to inventory.

        Although it seems like an unusual use, allow for amount=0 and a non-zero cost. Allows valuation adjustments,

        :param amount: int
        :param cost: int
        :return:
        """
        if amount < 0:
            raise ValueError('Cannot add negative amounts! to inventory')
        self.Amount += amount
        self.Cost += cost

    def change_reserves(self, amount):
        """
        Change the reserved amount. May be positive or negative.
        :param amount: int
        :return:
        """
        if amount + self.Reserved > self.Amount:
            raise errors.CommodityReserveError('Attempting to reserve more than exists')
        self.Reserved += amount
        if self.Reserved < 0:
            raise ValueError('Attempting to set negative reserves')

    def remove_inventory(self, amount, from_reserve=False):
        """
        Remove inventory units, returns the Cost Of Goods Sold (cogs)

        Throws a ValueError if attempt to remove more than exists, or more than unreserved inventory
        :param amount: int
        :param from_reserve: bool
        :return: int
        """
        if amount < 0:
            raise ValueError('Cannot remove negative amounts from inventory')
        if amount > self.Amount:
            raise ValueError('Attempting to remove more than exists')
        if not from_reserve:
            if amount > self.Amount - self.Reserved:
                raise ValueError('Attempting to remove reserved inventory')
        else:
            if amount > self.Reserved:
                raise ValueError('Attempting to remove more than reserved')
            self.Reserved -= amount
        # cogs = COGS = standard acronym for "cost of goods sold"
        if amount == self.Amount:
            cogs = self.Cost
        else:
            cogs = round(float(self.Cost * amount) / float(self.Amount))
        self.Cost -= cogs
        self.Amount -= amount
        return cogs


class Inventory(object):
    """
    Container object to hold all inventory information.
    Not an Entity, since will always be embedded in an Entity.
    """

    def __init__(self):
        # We can have multiple commodities in inventory, store all information
        # on a per-commodity basis.
        self.Commodities = {}

    def __getitem__(self, item):
        """
        Get the commodity info
        :param item: int
        :return: InventoryInfo
        """
        if item not in self.Commodities:
            # If we were cautious, validate that "item" is a commodityID
            self.Commodities[item] = InventoryInfo(item)
        return self.Commodities[item]

    def get_representation_info(self):
        out = [(x, y.Amount, y.Cost) for x, y in self.Commodities.items()]
        return out


class Agent(agent_based_macro.entity.Entity):
    """
    An agent is an entity that can do transactions, and thus has money accounts.

    ParentID = immediate owner
    TopParentID = top of ownership hierarchy (= "faction")

    TODO: Add connections for switchable AI decision events. Each decision rule has a name, and the
    selected one is called during the decision event associated with that rule. Events that do not make
    decisions (e.g., production) are fixed. Each decision event has its associated named rule, their might be
    high level "personalities" that choose a particular mix.

    I think the way to add decision rules is to make them separate functions with a standard calling syntax,
    and then the decision code returns the Actions to be taken. The decision function can use a type hint
    to fill in the Agent subclass, so that the decision rule can then use code completion in an development
    environment that supports them (in my case, PyCharm).

    Making the decision rules functions will make it easy for people to muck around with Agent behaviour without
    having to know too much about object-oriented coding (they will need to access data members, but that is natural).
    """

    def __init__(self, name, money_balance=0, location_id=None):
        super().__init__(name, 'agent')
        self.Money = money_balance
        self.LocationID = location_id
        self.ReserveMoney = 0
        self.ReserveWages = 0
        self.ReserveTax = 0
        self.ReserveOrders = 0
        self.ParentID = self.GID
        self.TopParentID = self.GID
        self.Employer = False
        self.Inventory = Inventory()
        self.NamedOrders = {}
        # We allow central government entities to run negative money balances, because MMT
        self.IsCentralGovernment = False
        self.SeriesBase = f'{name}@{location_id}'
        self.RegisteredSeries = dict()
        # Worker management
        self.IsEmployer = False
        self.WorkersActual = 0
        self.TargetWorkers = 0
        self.WorkersNextPeriod = 0
        self.Wage = 0

    def register_series(self, series_name):
        """
        Register a series associated with the agent. The agent's SeriesBase string is prepended
        :param series_name: str
        :return:
        """
        full_name = f'{self.SeriesBase}|{series_name}'
        simulation.get_simulation().register_time_series(full_name)
        self.RegisteredSeries[series_name] = full_name

    def time_series_set(self, name, value):
        try:
            full_name = self.RegisteredSeries[name]
        except KeyError:
            # Not registered, do nothing
            return
        simulation.get_simulation().time_series_set(full_name, value)

    def receive_money(self, amount):
        """
        Always OK, unless negative amount (!).
        :param amount: int
        :return:
        """
        if amount < 0:
            self.spend_money(-amount)
            return
        self.Money += amount

    def spend_money(self, amount, from_reserve=ReserveType.NONE):
        """
        Attempt to spend money. Can throw exceptions, in which case nothing happens.

        Currently, if spending from a reserve, the reserves have to be there. We could relax this, but
        it indicates something went wrong with reserve rules.

        All involuntary spending is reserved against, which should prevent hard liquidity events.
        - Can always pay for buy orders in markets.
        - Wages are reserved against, and if not enough money to meet reserves, forced firing.
        - Tax liabilities are reserved against, and since profits are created by cash events, there is an
          inflow to meet the liability.

        :param amount: int
        :param from_reserve: ReserveType
        :return:
        """
        if amount < 0:
            if not ReserveType.NONE == from_reserve:
                raise ValueError('Attempting to spend negative amount from a reserve - huh?')
            self.receive_money(-amount)
            return
        if amount > self.Money:
            raise NoMoneyError(f'Too much money: [{self.GID}] ${amount}')
        if ReserveType.NONE == from_reserve:
            if amount + self.ReserveMoney > self.Money:
                raise NoFreeMoneyError(f'Spending beyond reserves: [{self.GID}]')
            # Otherwise, transaction succeeds
            self.Money -= amount
            return
        elif ReserveType.ORDERS == from_reserve:
            if amount > self.ReserveOrders:
                raise NoFreeMoneyError(f'Order spend beyond reserves [{self.GID}]')
            self.ReserveOrders -= amount
        elif ReserveType.WAGES == from_reserve:
            if amount > self.ReserveWages:
                raise NoFreeMoneyError(f'Wage spend beyond reserves [{self.GID}]')
            self.ReserveWages -= amount
        elif ReserveType.TAX == from_reserve:
            if amount > self.ReserveTax:
                raise NoFreeMoneyError(f'Tax spend beyond reserves [{self.GID}]')
            self.ReserveTax -= amount
        else:
            raise ValueError('Logic error')
        self.Money -= amount
        self.ReserveMoney -= amount

    def change_reserves(self, change, reserve_type=ReserveType.ORDERS):
        """
        Change the reserve amount. May throw an error, in which case nothing happens.
        :param change: int
        :param reserve_type: ReserveType
        :return:
        """
        if change > 0:
            # Central government entities ignore money reserves.
            # TODO: override do_accounting() in the central government classes.
            if (not self.IsCentralGovernment) and (change + self.ReserveMoney > self.Money):
                raise NoFreeMoneyError(f'Attempting to set reserves beyond money [{self.GID}]')
            # OK, let's do this
            if ReserveType.ORDERS == reserve_type:
                self.ReserveOrders += change
            elif ReserveType.TAX == reserve_type:
                self.ReserveTax += change
            elif ReserveType.WAGES == reserve_type:
                self.ReserveWages += change
            else:
                raise ValueError('Must specify valid reserve type')
            self.ReserveMoney += change
        else:
            # Decrease: always possible if reserves already exist.
            if ReserveType.ORDERS == reserve_type:
                if self.ReserveOrders >= -change:
                    self.ReserveOrders += change
                else:
                    raise ReserveError(f'attempt to set negative reserves [{self.GID}]')
            elif ReserveType.WAGES == reserve_type:
                if self.ReserveWages >= -change:
                    self.ReserveWages += change
                else:
                    raise ReserveError(f'attempt to set negative reserves [{self.GID}]')
            elif ReserveType.TAX == reserve_type:
                if self.ReserveTax >= -change:
                    self.ReserveTax += change
                else:
                    raise ReserveError(f'attempt to set negative reserves [{self.GID}]')
            else:
                raise ValueError('Must specify valid reserve type')
            self.ReserveMoney += change

    def register_events(self):
        """
        Called by the simulation.

        Each Agent registers a number of repeated events that will be added to the queue
        by the Simulation.
        :return: tuple
        """
        return ()

    def do_accounting(self, order_type, operation, amount, price, commodity_id):
        """
        Accounting in response to a market order operation.

        Work is done in do_accounting_buy(), do_accounting_sell().

        I've fragmented the function so that subclasses can override these methods independently.

        :param order_type: OrderType
        :param operation: str
        :param amount: int
        :param price: int
        :param commodity_id: int
        :return:
        """
        if amount == 0:
            # Nothing can happen with a zero unit order.
            return
        if order_type == OrderType.BUY:
            self.do_accounting_buy(operation, amount, price, commodity_id)
        else:
            self.do_accounting_sell(operation, amount, price, commodity_id)

    def do_accounting_buy(self, operation, amount, price, commodity_id):
        """
        Buy order accounting.

        When we add a BuyOrder, we need to reserve cash against the purchase. We then
        release the reserves whether we cancel or fill the order. If we fill, we get the stuff
        into inventory.

        :param operation: str
        :param amount: int
        :param price: int
        :param commodity_id: int
        :return:
        """
        # Switch to match when I install Python 10...
        if operation == 'add':
            self.change_reserves(amount * price, reserve_type=ReserveType.ORDERS)
        elif operation == 'fill':
            self.buy_goods(commodity_id, amount, amount * price)
        elif operation == 'remove':
            self.change_reserves(-amount * price, reserve_type=ReserveType.ORDERS)
        else:
            raise ValueError(f'unknown operation: {operation}')

    def do_accounting_sell(self, operation, amount, price, commodity_id):
        """
        Accounting for a SellOrder.

        :param operation: str
        :param amount: int
        :param price: int
        :param commodity_id: int
        :return:
        """
        if operation == 'add':
            self.Inventory[commodity_id].change_reserves(amount)
        elif operation == 'fill':
            self.sell_goods(commodity_id, amount, amount * price)
        elif operation == 'remove':
            self.Inventory[commodity_id].change_reserves(-amount)
        else:
            raise ValueError(f'Unsupported operation {operation}')

    def buy_goods(self, commodity_id, amount, payment):
        """
        Do the operations for buying a good.

        :param commodity_id: int
        :param amount: int
        :param payment: int
        :return:
        """
        self.spend_money(payment, from_reserve=ReserveType.ORDERS)
        self.Inventory[commodity_id].add_inventory(amount, payment)

    def sell_goods(self, commodity_id, amount, payment):
        self.receive_money(payment)
        # Need to expense COGS
        cogs = self.Inventory[commodity_id].remove_inventory(amount, from_reserve=True)

    def get_info(self):
        return f'{self.GID}'


class ProductionAgent(Agent):
    """
    An agent that has production capacity
    """

    def __init__(self, name, money_balance=0, location_id=None):
        super().__init__(name, money_balance=money_balance, location_id=location_id)
        self.ProductivityMultiplier = 1.

    def get_productivity(self, commodity_id):
        """
        Get the productivity associated with a commodity.
        For now, we have a single scalar ProductivityMultiplier for all commodities.
        Might need to revise that if we have multiple outputs.

        :param commodity_id: int
        :return: float
        """
        loc = agent_based_macro.entity.Entity.get_entity(self.LocationID)
        base_productivity = loc.ProductivityDict[commodity_id]
        productivity = self.ProductivityMultiplier * base_productivity
        return productivity

    def get_daily_production(self, commodity_id):
        """
        Production function on a daily basis. Returns an int. The time between production events is the inverse
        of this value.

        Note that we need to round off production to integer values. If we want smoothly varying productivity,
        would need to make the system more complicated. We could either have a changing production period time,
        or track fractional produced units. The latter is more complicated in that we need to split the production
        cost between the quantised production and the fractional overflow.

        :return: int
        """
        productivity = self.get_productivity(commodity_id)

        return int(productivity * float(self.WorkersActual))

    def unit_cost(self, commodity_id):
        """
        Unit Cost of production (float).

        If production remains linear, we could just base this on wages, but we might allow for
        nonlinearities, so we need to calculate the daily production
        :return: float
        """
        return self.Wage / self.get_productivity(commodity_id)

    def get_daily_wage_bill(self):
        payment = self.WorkersActual * self.Wage
        return payment


class CentralGovernment(Agent):
    def __init__(self):
        super().__init__(name='CentralGovernment', money_balance=0)

    def spend_money(self, amount, from_reserve=ReserveType.NONE):
        """
        Can always spend money, reserves are ignored.

        Accounting identity: Government Money balance is negative of the sum of all other agent's money balances.

        :param amount: int
        :param from_reserve:
        :return:
        """
        self.Money -= amount


class HouseholdSector(Agent):
    def __init__(self, location_id, money_balance, target_money, name='household'):
        super().__init__(name, money_balance, location_id=location_id)
        self.TargetMoney = target_money
        self.DailyEarnings = 0

    def receive_wages(self, amount):
        """
        Receive wages, and pay taxes (boo!)
        Increases DailyEarnings, which is used in the consumption function. Other transactions might not
        feed into these earnings.
        :param amount:
        :return:
        """
        sim = agent_based_macro.entity.Entity.get_entity(agent_based_macro.entity.SIMULATION_ID)
        self.receive_money(amount)
        # Do something more sophisticated for tax payment later.
        taxes = math.floor(0.1 * amount)
        self.change_reserves(taxes, ReserveType.TAX)
        sim.pay_taxes(self.GID, taxes)
        self.DailyEarnings += (amount - taxes)

    def register_events(self):
        """

        :return: list
        """
        payment_event = simulation.Event(self.GID, self.event_calculate_spending, 0., 1.)
        return [(payment_event, (0.6, 0.7))]

    def event_calculate_spending(self):
        """
        Every day, put in a market order for available spending budget.

        Since we are using a named order, it replaces the existing order, so so we do not have to
        worry about stacking up orders.

        :return:
        """
        # Hard code parameters for now
        daily_spend = int(0.7 * self.DailyEarnings + 0.01 * self.Money)
        # Increase TargetMoney by the implied daily savings - possibly negative
        self.TargetMoney += (self.DailyEarnings - daily_spend)
        self.time_series_set('DailyEarnings', self.DailyEarnings)
        self.time_series_set('TargetMoney', self.TargetMoney)
        self.time_series_set('Money', self.Money)
        # Put in a order for 100% of available spending at a fixed offset below the ask price.
        # This will cancel any existing order, which will free up cash if the previous day's order
        # was not filled.
        sim = agent_based_macro.entity.Entity.get_simulation()
        food_id = sim.get_commodity_by_name('Fud')
        location = agent_based_macro.entity.Entity.get_entity(self.LocationID)
        market = sim.get_market(self.LocationID, food_id)
        ask = market.get_ask()

        # No ask price, no bid!
        if ask is not None:
            bid_price = int(0.95 * ask)
            # Target amount of spending is is the minimum of
            # (1) self.Money - self.TargetMoney = equals the free room for spending, which would
            #     equal daily_spend if the sector spent the "maximum" amount the day before.
            # (2) 130% of daily spend. If we spent less than the maximum in previous days, allow for
            #     a bid beyond daily spending.
            targ_spend = min(self.Money - self.TargetMoney, 1.3 * daily_spend)
            # Need to deal with a corner case: what if self.TargetMoney > self.Money (somehow).
            # This would imply negative spending.
            # Make the spending at least 50% of daily_spend.
            # Eventually, self.Money will catch up to TargetMoney.
            targ_spend = max(targ_spend, 0.5 * daily_spend)
            amount = math.floor(targ_spend / bid_price)
            self.time_series_set('DailyBid', amount * bid_price)
            if amount > 0:
                order = BuyOrder(bid_price, amount, self.GID)
                market.add_named_buy(agent=self, name='DailyBid', order=order)
        # Then add an event for a market order
        sim.queue_event_delay(self.GID, self.event_market_order, .6)
        # Need to reset daily Earnings. Could be done as a separate event, but will need a time series
        # object.
        self.DailyEarnings = 0

    def event_market_order(self):
        """
        If there is any available spending power, hit the ask.

        Only spend a certain percentage of cash earmarked for spending.

        :return:
        """
        sim = agent_based_macro.entity.Entity.get_simulation()
        food_id = sim.get_commodity_by_name('Fud')
        location = agent_based_macro.entity.Entity.get_entity(self.LocationID)
        market = sim.get_market(self.LocationID, food_id)
        ask = market.get_ask()
        if ask is None:
            # Nothing available, no market order!
            return
        available_money = self.Money - (self.TargetMoney + self.ReserveMoney)
        to_spend = available_money * 0.3
        # Since there may only be a teeny amount for sale at the ask, put a limit order with price
        # higher than the ask
        price = 1.05 * ask
        amount = math.floor(to_spend / price)
        if amount < 1:
            return
        order = BuyOrder(price, amount, self.GID)
        self.time_series_set('MarketOrder', price * amount)
        market.add_named_buy(agent=self, name='"MarketOrder"', order=order)


class Market(agent_based_macro.entity.Entity, MarketBase):
    def __init__(self, name, location_id, commodity_id):
        agent_based_macro.entity.Entity.__init__(self, name, ttype='market')
        MarketBase.__init__(self)
        self.LocationID = location_id
        self.CommodityID = commodity_id
        # Since the market will always be calling the Simulation to log transactions, embed a reference to
        # the Simulation inside the Market.
        self.Simulation = simulation.get_simulation()

    def get_time(self):
        """
        Return simulation.Time

        (Base class does not have access to the simulation, so need to override get_time().)

        :return: float
        """
        sim = Entity.get_simulation()
        return sim.Time

    def do_accounting(self, firm_gid, order_type, operation, amount, price):
        """
        Handle the accounting operations - by passing it on to the appropriate Agent

        :param firm_gid: int
        :param order_type: OrderType
        :param operation: str
        :param amount: int
        :param price: int
        :return:
        """
        agent: Agent = Entity.get_entity(firm_gid)
        agent.do_accounting(order_type, operation, amount, price, self.CommodityID)

    def add_named_buy(self, agent, name, order):
        """
        Allow agents to keep a "named" order. New orders automatically cancel order with the same name.
        :param agent: Agent
        :param name: str
        :param order: BuyOrder
        :return:
        """
        name = 'buy_' + name
        id_existing = agent.NamedOrders.get(name, None)
        if id_existing is not None:
            self.remove_order(id_existing)
        self.add_buy(order)
        agent.NamedOrders[name] = order.OrderID

    def add_named_sell(self, agent, name, order):
        """
        Allow agents to keep a "named" order. New orders automatically cancel order with the same name.
        :param agent: Agent
        :param name: str
        :param order: BuyOrder
        :return:
        """
        name = 'sel_' + name
        id_existing = agent.NamedOrders.get(name, None)
        if id_existing is not None:
            self.remove_order(id_existing)
        self.add_sell(order)
        agent.NamedOrders[name] = order.OrderID

    def get_bid(self):
        if len(self.BuyList) > 0:
            return self.BuyList[0].Price
        else:
            return None

    def get_ask(self):
        if len(self.SellList) > 0:
            return self.SellList[0].Price
        else:
            return None

    def get_representation(self):
        info = super().get_representation()
        info['Location'] = self.LocationID
        info['CommodityID'] = self.CommodityID
        if len(self.BuyList) > 0:
            info['BidPrice'] = self.BuyList[0].Price
            info['BidSize'] = self.BuyList[0].Amount
        else:
            info['BidPrice'] = None
            info['BidSize'] = None
        if len(self.SellList) > 0:
            info['AskPrice'] = self.SellList[0].Price
            info['AskSize'] = self.SellList[0].Amount
        else:
            info['AskPrice'] = None
            info['AskSize'] = None
        info['LastPrice'] = self.LastPrice
        info['LastTime'] = self.LastTime
        return info

    def log_transaction(self, buy_id, sell_id, initiated_id, amount, price):
        """
        Transaction logging. Must be implemented in a child class.
        :param buy_id: int
        :param sell_id: int
        :param initiated_id: int
        :param amount: int
        :param price: int
        :return:
        """
        # Let the simulation do the work...
        self.Simulation.log_transaction(self.GID, buy_id, sell_id, initiated_id, amount, price)


class BaseSimulation(simulation.Simulation):
    """
    Class to manage the setup of entities.
    """

    def __init__(self):
        """
        Set up data, add CentralGovernment
        """
        self.CentralGovernmentID = None
        super().__init__()
        self.Locations = []
        self.Commodities = []
        self.Markets = {}
        self.Households = {}
        # Could be a weakref, but JG will not disappear
        self.JGLookup = {}
        gov = CentralGovernment()
        self.add_entity(gov)
        self.CentralGovernmentID = gov.GID
        # A location that is not really a location -- off the logical grid.
        self.NonLocationID = None
        # For invalid actions for players, send a message to the client, otherwise throw an error.
        # Need to keep a list of Agents that are player-associated.
        self.PlayerGID = set()

    def add_entity(self, entity):
        """
        When we add an Entity that has a money balance, subtract the amount from the CentralGovernment.
        This way we ensure that CentralGovernment Money liability matches private sector Money assets
        without forcing initialisation code to remember to add that operation.

        :param entity: Entity
        :return:
        """
        super().add_entity(entity)
        if hasattr(entity, 'Money'):
            try:
                gov = agent_based_macro.entity.Entity.get_entity(self.CentralGovernmentID)
            except KeyError:
                # This will blow up when we add the CentralGovernment itself!
                return
            gov.Money -= entity.Money

    def register_actions(self):
        super(BaseSimulation, self).register_actions()
        Action.add_action_type('PayWages', BaseSimulation.process_action, ('payment',), '')
        Action.add_action_type('ProductionLabour', BaseSimulation.process_action, ('commodity', 'num_workers',
                                                                                   'payment',), '')
        Action.add_action_type('AddNamedBuy', BaseSimulation.process_action, ('name', 'commodity_id',
                                                                              'price', 'amount'), '')
        Action.add_action_type('AddNamedSell', BaseSimulation.process_action, ('name', 'commodity_id',
                                                                               'price', 'amount'), '')
        Action.add_action_type('BuyNoKeep', BaseSimulation.process_action, ('commodity_id',
                                                                            'price', 'amount'), '')
        Action.add_action_type('SellNoKeep', BaseSimulation.process_action, ('commodity_id',
                                                                             'price', 'amount'), '')

    def add_location(self, location):
        self.add_entity(location)
        self.Locations.append(location.GID)

    def add_commodity(self, commodity):
        self.add_entity(commodity)
        self.Commodities.append(commodity.GID)

    def add_household(self, household):
        """
        Add a household sector object.
        :param household: HouseholdSector
        :return: None
        """
        self.add_entity(household)
        self.Households[household.LocationID] = household.GID

    def get_market(self, loc_id, commod_id):
        return self.Markets[(loc_id, commod_id)]

    def get_commodity_by_name(self, commodity_name):
        """
        Get the commodity_ID via name.
        Needed by Agents that refer to hard-coded commodities.

        :param commodity_name: str
        :return: Entity
        """
        for c in self.Commodities:
            c_obj = agent_based_macro.entity.Entity.get_entity(c)
            if c_obj.Name == commodity_name:
                return c

    def generate_markets(self):
        """
        Call this after all locations and commodities are built, so long as you want all combinations supported
        :return:
        """
        for loc_id in self.Locations:
            loc = agent_based_macro.entity.Entity.get_entity(loc_id)
            for commod_id in self.Commodities:
                com = agent_based_macro.entity.Entity.get_entity(commod_id)
                name = f'{com.Name}@{loc.Name}'
                market = Market(name, loc_id, commod_id)
                self.add_entity(market)
                self.Markets[(loc_id, commod_id)] = market
                self.Markets[(loc_id, com.Name)] = market

    def pay_taxes(self, taxpayer_gid, amount):
        """
        Have entity pay taxes (if it exists).
        :param taxpayer_gid: int
        :param amount: int
        :return:
        """
        try:
            sucker = agent_based_macro.entity.Entity.get_entity(taxpayer_gid)
        except KeyError:
            return
        sucker.spend_money(amount, ReserveType.TAX)
        cgov = agent_based_macro.entity.Entity.get_entity(self.CentralGovernmentID)
        cgov.receive_money(amount)

    def get_action_data(self, agent, request, **kwargs):
        """
        Get requested data.
        :param agent: Agent
        :param args:
        :return:
        """
        if request == 'Productivity':
            # FORMAT: 'Productivity', <commodity name or ID> -> productivity factor for agent's location.
            if type(kwargs['commodity']) is str:
                commodity_id = self.get_commodity_by_name(kwargs['commodity'])
            else:
                commodity_id = kwargs['commodity']
            return agent.get_productivity(commodity_id)
        if request == 'CommodityID':
            # Format: 'CommodityID', <commodity_name> -> commodity ID.
            return self.get_commodity_by_name(kwargs['commodity'])
        if request == 'JG_Wage':
            loc_id = agent.LocationID
            JG = self.JGLookup[loc_id]
            return JG.Wage
        raise ValueError(f'Unhandled Data Request: {request}')

    def process_action(self, agent, action_type, **kwargs):
        """
        Handle actions associated with this class.

        This is a clumsy architecture - will split into individual handlers.

        :param agent: Agent
        :param action: Action
        :return:
        """
        # Switch to match for Python 3.10
        if action_type == 'PayWages':
            # We assume that there is only a single aggregated Household to get all wages.
            household_id = self.Households[agent.LocationID]
            household: HouseholdSector = agent_based_macro.entity.Entity.get_entity(household_id)
            amount = int(kwargs['payment'])
            agent.spend_money(amount=amount)
            household.receive_wages(amount=amount)
        elif action_type == 'ProductionLabour':
            commodity = kwargs['commodity']
            num_workers = kwargs['num_workers']
            payment = kwargs['payment']
            self.action_production_labour(agent, commodity, num_workers, payment)
        elif action_type == 'AddNamedBuy':
            name = kwargs['name']
            commodity_id = kwargs['commodity_id']
            price = kwargs['price']
            amount = kwargs['amount']
            market = self.get_market(agent.LocationID, commodity_id)
            order = BuyOrder(price, amount, agent.GID)
            market.add_named_buy(agent, name, order)
        elif action_type == 'AddNamedSell':
            name = kwargs['name']
            commodity_id = kwargs['commodity_id']
            price = kwargs['price']
            amount = kwargs['amount']
            market = self.get_market(agent.LocationID, commodity_id)
            order = SellOrder(price, amount, agent.GID)
            market.add_named_sell(agent, name, order)
        elif action_type == 'BuyNoKeep':
            commodity_id = kwargs['commodity_id']
            price = kwargs['price']
            amount = kwargs['amount']
            market = self.get_market(agent.LocationID, commodity_id)
            order = BuyOrder(price, amount, agent.GID)
            order.KeepInQueue = False
            try:
                market.add_buy(order)
            except errors.NoFreeMoneyError:
                if agent.GID in self.PlayerGID:
                    event = simulation.Event(self.GID, self.event_send_invalid_action, self.Time, None,
                                             response='NoFreeMoney')
                    simulation.queue_event(event)
                else:
                    raise
        elif action_type == 'SellNoKeep':
            commodity_id = kwargs['commodity_id']
            price = kwargs['price']
            amount = kwargs['amount']
            market = self.get_market(agent.LocationID, commodity_id)
            order = SellOrder(price, amount, agent.GID)
            order.KeepInQueue = False
            try:
                market.add_sell(order)
            except errors.CommodityReserveError:
                if agent.GID in self.PlayerGID:
                    event = simulation.Event(self.GID, self.event_send_invalid_action, self.Time, None,
                                             response='NotEnoughCommodity')
                    simulation.queue_event(event)
                else:
                    raise
        else:
            # NOTE: Should not reach this point.
            raise ValueError(f'Unknown Action arguments: {action_type}')

    def action_production_labour(self, agent, commodity, num_workers, payment):
        """
        Note: can either pass the commodity_id, or the name.

        Right now, production depends upon a productivity parameter that is location-based.
        Since we need to go into other entities to get the productivity, the simulation handles it.
        Once production functions get complex, the simulation will call back a production function
        within the Agent itself, just filling in missing data.

        :param agent: Agent
        :param commodity: int
        :param num_workers: int
        :param payment: int
        :return:
        """
        if type(commodity) is str:
            commodity_id = self.get_commodity_by_name(commodity)
        else:
            commodity_id = commodity
        production = agent.get_daily_production(commodity_id)
        agent.Inventory[commodity_id].add_inventory(production, payment)

    def log_transaction(self, market_id, buy_id, sell_id, initiated_id, amount, price):
        """
        Transaction logging. Must be implemented in a child class.
        :param buy_id: int
        :param sell_id: int
        :param initiated_id: int
        :param amount: int
        :param price: int
        :return:
        """
        if 'transactions' not in self.LogDict:
            return
        market_name = self.get_entity(market_id).Name
        buy_name = self.get_entity(buy_id).Name
        sell_name = self.get_entity(sell_id).Name
        elems = (self.Time, market_name, market_id, buy_name, buy_id, sell_name, sell_id, initiated_id, amount, price)
        elems = [str(x) for x in elems]
        msg = '\t'.join(elems)
        self.log_msg('transactions', msg)

    def event_send_invalid_action(self, *args):
        raise ValueError('bink')


def register_query(query, handler, required, docstring=''):
    """
    Utility function to register a data request to the global registry

    For now, not dealing with the doctsring
    :param query: str
    :param required: tuple
    :param docstring: str
    :return:
    """
    obj = ActionDataRequestHolder()
    obj.register_entry(query, handler, required, docstring)


# Global list of requests. More can be registered elsewhere.
info = (
    ('Productivity', BaseSimulation.get_action_data, ('commodity',), 'Get the productivity associated for a commodity'),
    ('JG_Wage', BaseSimulation.get_action_data, tuple(), 'Get the JobGuarantee wage at the Agent''s location'),
    ('CommodityID',BaseSimulation.get_action_data,  ('commodity',), 'Get the GID of a commodity by name'),
)

for q, h, r, d in info:
    register_query(q, h, r, d)