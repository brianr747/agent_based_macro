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

"""
import weakref
import enum
import math

import agent_based_macro.entity
from agent_based_macro.entity import Entity
from agent_based_macro.orders import SellOrder, BuyOrder, MarketBase, OrderType
from agent_based_macro.simulation import SimulationError
import agent_based_macro.simulation as simulation


class NoMoneyError(SimulationError):
    pass


class NoFreeMoneyError(SimulationError):
    """Attempting to spend beyond free money capacity"""
    pass


class ReserveError(SimulationError):
    """ Attempting to reduce reserve to a negative amount"""
    pass


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
            raise ValueError('Attempting to reserve more than exists')
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


class Agent(agent_based_macro.entity.Entity):
    """
    An agent is an entity that can do transactions, and thus has money accounts.

    ParentID = immediate owner
    TopParentID = top of ownership hierarchy (= "faction")
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
            # Otherwise, goes through.
            self.Money -= amount
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
            self.change_reserves(amount*price, reserve_type=ReserveType.ORDERS)
        elif operation == 'fill':
            self.buy_goods(commodity_id, amount, amount*price)
        elif operation == 'remove':
            self.change_reserves(-amount*price, reserve_type=ReserveType.ORDERS)
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
            self.sell_goods(commodity_id, amount, amount*price)
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


class ProducerLabour(Agent):
    """
    A firm that produces output solely based on labour input.

    Eventually will have producers with commodity inputs. May migrate code to a base class

    Note: I started this class, but it's not been used, and the code may be out of date.
    """

    def __init__(self, name, money_balance, location_id, commodity_id):
        super().__init__(name, money_balance, location_id)
        self.OutputID = commodity_id
        # Subclasses can override these values...
        # Penalty multiplier for firing. Fixed by law.
        self.WagePenalty = 5
        # This is the multiplier used to determine reserve for wages. Must be greater than WagePenalty
        self.WageMultiplier = 15
        # This is a technological limit
        self.WorkersMax = 40
        # This is set by decision routines
        self.WorkersTarget = 0
        # What is daily wage per worker. Set by decision routines
        self.Wage = 0
        # How many workers are working for the day?
        # Note that workers are paid up front
        self.WorkersActual = 0
        # When does wage payment/worker rollover happen (offset in interval (0.1, 1)?
        self.DayOffset = 0.1
        # Number of workers on the next day, determined by worker migration step
        # Worker migration done in (0, .1) interval.
        self.WorkersNextDay = 0
        # Inventory manager
        self.Inventory = Inventory()
        # Production level = float, updated during production events. Once > 1.0, add integer part to Inventory
        self.Production = 0.0
        # Wages are not expensed, they are capitalised into inventory cost.
        # Once units are produced, balance from CapitalisedWages is transferred to InventoryCost.
        self.CapitalisedWages = 0
        # Linear production factor
        self.LinearProduction = 15.
        self.Employer = True

    def daily_production(self):
        """
        Production function on a daily basis. Returns a float. The time between production events is the inverse
        of this value.
        :return: float
        """
        return self.LinearProduction * float(self.WorkersActual)

    def unit_cost(self):
        """
        Unit Cost of production (float).

        If production remains linear, we could just base this on wages, but we might allow for
        nonlinearities, so we need to calculate the daily production
        :return: float
        """
        return self.daily_production() / float(self.WorkersActual * self.Wage)


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


class JobGuarantee(Agent):
    """
    Although ech planet has its own agent, transactions use the central government money account.
    """

    def __init__(self, location_id, central_gov_id, job_guarantee_wage, num_workers=0):
        super().__init__(money_balance=0, name='JobGuarantee', location_id=location_id)
        self.CentralGovID = central_gov_id
        self.WorkersActual = num_workers
        self.Employer = True
        self.Inventory = Inventory()
        self.JobGuaranteeWage = job_guarantee_wage
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
        payment_event = simulation.ActionEvent(self.GID, self.event_production, 0., 1.)
        return [(payment_event, (0., 0.1))]

    def event_production(self, *args):
        sim = agent_based_macro.entity.Entity.get_simulation()
        if self.HouseholdGID is None:
            try:
                self.HouseholdGID = sim.Households[self.LocationID]
            except KeyError:
                raise ValueError('Did not add the Household to the simulation.')
        # Since the HouseholdSector and central government are indestructible (I hope), this transfer will always
        # be valid. (Normally, need to validate existence of all entities.)

        payment = self.WorkersActual * self.JobGuaranteeWage
        self.add_action('PayWages', payment)
        # JG Production
        self.add_action('ProductionLabour', 'Fud', self.WorkersActual, payment)
        # food_id = sim.get_commodity_by_name('Fud')
        # loc = agent_based_macro.entity.Entity.get_entity(self.LocationID)
        # production = self.WorkersActual * loc.ProductivityDict[food_id]
        # self.Inventory[food_id].add_inventory(production, payment)
        sim.queue_event_delay(self.GID, self.event_set_orders, .1)

    def event_set_orders(self):
        """
        Set up buy/sell orders.

        Keep it as simple as possible, to allow the loop to close.

        May create a simpler interface for these orders.
        :return:
        """
        sim = agent_based_macro.entity.Entity.get_simulation()
        food_id = sim.get_commodity_by_name('Fud')
        location = agent_based_macro.entity.Entity.get_entity(self.LocationID)
        market = sim.get_market(self.LocationID, food_id)
        production_price = self.JobGuaranteeWage / location.ProductivityDict[food_id]
        # Create a floor price
        buyorder = BuyOrder(production_price * .95, 300, self.GID)
        market.add_named_buy(agent=self, name='floor', order=buyorder)
        # Sell production
        amount = self.Inventory[food_id].Amount - self.Inventory[food_id].Reserved
        sellorder = SellOrder(production_price * 1.1, amount, self.GID)
        market.add_named_sell(agent=self, name='production', order=sellorder)


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
        daily_spend = 0.7 * self.DailyEarnings + 0.01 * self.Money
        # Increase TargetMoney by the implied daily savings - possibly negative
        self.TargetMoney += (self.DailyEarnings - daily_spend)
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
            amount = math.floor(targ_spend / bid_price)
            if amount > 0:
                order = BuyOrder(bid_price, amount, self.GID)
                market.add_named_buy(agent=self, name='DailyBid', order=order)
        # Then add an event for a market order
        sim.queue_event_delay(self.GID, self.event_market_order, .6)
        # Need to reset daily Earnings. Could be done as a seperate event, but will need a time series
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
        market.add_named_buy(agent=self, name='"MarketOrder"', order=order)


class Market(agent_based_macro.entity.Entity, MarketBase):
    def __init__(self, name, location_id, commodity_id):
        agent_based_macro.entity.Entity.__init__(self, name, ttype='market')
        MarketBase.__init__(self)
        self.LocationID = location_id
        self.CommodityID = commodity_id

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
        agent : Agent = Entity.get_entity(firm_gid)
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

    def add_buy_deprecated(self, buyorder):
        """
        Add a buy order.

        Note: if for some reason the new order hits a sell order from the same firm (?),
        the firm transacts against itself.

        Since the buy will release reserved inventory, it does have the effect of adding to free inventory.

        This should be changed to just releasing inventory, as transacting against itself allows an Agent to
        play games with inventory costs, and it generates taxable income.

        :param buyorder:
        :return:
        """
        raise DeprecationWarning('about to be deleted')
        buyer = agent_based_macro.entity.Entity.get_entity(buyorder.FirmGID)
        buyer.change_reserves(buyorder.Amount * buyorder.Price, ReserveType.ORDERS)
        # If the buy price is less than the ask, we insert into BuyList
        # Otherwise, we transact until either the buy order is completely filled, or
        # the ask has risen past the new order's bid
        while True:
            if len(self.SellList) == 0:
                # No sellers, so automatically add to BuyList
                self.BuyList.insert_order(buyorder)
                return
            ask = self.SellList[0].Price
            if buyorder.Price < ask:
                self.BuyList.insert_order(buyorder)
                return
            else:
                # Transaction!
                self.LastPrice = ask
                self.LastTime = simulation.get_simulation().Time
                amount = min(self.SellList[0].Amount, buyorder.Amount)
                seller = agent_based_macro.entity.Entity.get_entity(self.SellList[0].FirmGID)
                payment = amount * ask
                #
                buyer.spend_money(payment, from_reserve=ReserveType.ORDERS)
                seller.receive_money(payment)
                buyer.Inventory[self.CommodityID].add_inventory(amount, payment)
                cogs = seller.Inventory[self.CommodityID].remove_inventory(amount, from_reserve=True)
                # TODO: Register loss from COGS
                # Then, remove orders as needed.
                buyorder.Amount -= amount
                self.SellList[0].Amount -= amount
                # Remove the front of the sell list if empty.
                self.SellList.check_empty()
                if buyorder.Amount == 0:
                    # Order has been cleared out, quit processing.
                    return

    def add_sell_deprecated(self, sellorder):
        """
        Add a sell order.

        Note: if for some reason the new order hits a sell order from the same firm (?),
        the firm transacts against itself.

        Since the buy will release reserved inventory, it does have the effect of adding to free inventory.

        This should be changed to just releasing inventory, as transacting against itself allows an Agent to
        play games with inventory costs, and it generates taxable income.

        :param sellorder: SellOrder
        :return:
        """
        # Note: I have essentially just mirrored code, which is probably bad, but at least it is
        # easy to follow.
        raise DeprecationWarning('about to be deleted')
        seller = agent_based_macro.entity.Entity.get_entity(sellorder.FirmGID)
        seller.Inventory[self.CommodityID].change_reserves(sellorder.Amount)

        # If the sell price is greater than the bid, we insert into SellList
        # Otherwise, we transact until either the order is completely filled, or
        # the bid drops the new order's ask
        while True:
            if len(self.BuyList) == 0:
                # No sellers, so automatically add to BuyList
                self.SellList.insert_order(sellorder)
                return
            bid = self.BuyList[0].Price
            if sellorder.Price > bid:
                self.SellList.insert_order(sellorder)
                return
            else:
                # Transaction!
                self.LastPrice = bid
                self.LastTime = simulation.get_simulation().Time
                amount = min(self.BuyList[0].Amount, sellorder.Amount)
                buyer = agent_based_macro.entity.Entity.get_entity(self.BuyList[0].FirmGID)

                payment = amount * bid
                #
                buyer.spend_money(payment, from_reserve=ReserveType.ORDERS)
                seller.receive_money(payment)
                buyer.Inventory[self.CommodityID].add_inventory(amount, payment)
                cogs = seller.Inventory[self.CommodityID].remove_inventory(amount, from_reserve=True)
                # TODO: Register loss from COGS
                # Clear out empty orders as needed
                self.BuyList[0].Amount -= amount
                sellorder.Amount -= amount
                self.BuyList.check_empty()
                if sellorder.Amount == 0:
                    # Order has been completely filled, quit processing
                    return

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
        else:
            info['BidPrice'] = None
        if len(self.SellList) > 0:
            info['AskPrice'] = self.SellList[0].Price
        else:
            info['AskPrice'] = None
        info['LastPrice'] = self.LastPrice
        info['LastTime'] = self.LastTime
        return info


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
        gov = CentralGovernment()
        self.add_entity(gov)
        self.CentralGovernmentID = gov.GID
        # A location that is not really a location -- off the logical grid.
        self.NonLocationID = None

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

    def get_action_data(self, agent, *args):
        raise NotImplementedError('need GetActionData')

    def process_action(self, agent, action):
        """
        Handle custom actions (not data or callback actions)

        For now, not creating custom Action subclasses, instead just parse the arguments.

        Supported generic Action arguments:

        'PayWages', <amount>


        :param agent: Agent
        :param action: Action
        :return:
        """
        # Switch to match for Python 3.10
        if action.args[0] == 'PayWages':
            # We assume that there is only a single aggregated Household to get all wages.
            household_id = self.Households[agent.LocationID]
            household: HouseholdSector = agent_based_macro.entity.Entity.get_entity(household_id)
            if len(action.args) == 0:
                raise ValueError('PayWages Action: Need to specify amount as second parameter')
            else:
                amount = int(action.args[1])
            agent.spend_money(amount=amount)
            household.receive_wages(amount=amount)
        elif action.args[0] == 'ProductionLabour':
            commodity = action.args[1]
            num_workers = action.args[2]
            payment = action.args[3]
            self.action_production_labour(agent, commodity, num_workers, payment)
        else:
            raise ValueError(f'Unknown Action arguments: {action.args}')

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
            commodity_id = self.get_commodity_by_name('Fud')
        else:
            commodity_id = commodity
        loc = agent_based_macro.entity.Entity.get_entity(agent.LocationID)
        production = num_workers * loc.ProductivityDict[commodity_id]
        agent.Inventory[commodity_id].add_inventory(production, payment)
