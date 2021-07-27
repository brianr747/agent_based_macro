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
from agent_based_macro.orders import OrderQueue, SellOrder, BuyOrder
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
    def __init__(self, commodity_ID):
        self.CommodityID = commodity_ID
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

    def ChangeReserves(self, amount):
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

    def RemoveInventory(self, amount, from_reserve=False):
        """
        Remove inventory units, returns the Cost Of Goods Sold (COGS)

        Throws a ValueError if attempt to remove more than exists, or more than unreserved inventory
        :param amount: int
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
        if amount == self.Amount:
            COGS = self.Cost
        else:
            COGS = round(float(self.Cost * amount) / float(self.Amount))
        self.Cost -= COGS
        self.Amount -= amount
        return COGS


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

    def __init__(self, name, money_balance=0, location_ID=None):
        super().__init__(name, 'agent')
        self.Money = money_balance
        self.LocationID = location_ID
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

    def ReceiveMoney(self, amount):
        """
        Always OK, unless negative amount (!).
        :param amount: int
        :return:
        """
        if amount < 0:
            self.SpendMoney(-amount)
            return
        self.Money += amount

    def SpendMoney(self, amount, from_reserve=ReserveType.NONE):
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
            self.ReceiveMoney(-amount)
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

    def ChangeReserves(self, change, reserve_type=ReserveType.ORDERS):
        """
        Change the reserve amount. May throw an error, in which case nothing happens.
        :param change: int
        :param reserve_type: ReserveType
        :return:
        """
        if change > 0:
            # Central government entities ignore money reserves.
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

    def RegisterEvents(self):
        """
        Called by the simulation.

        Each Agent registers a number of repeated events that will be added to the queue
        by the Simulation.
        :return: tuple
        """
        return ()

    def BuyGoods(self, commodity_ID, amount, payment):
        """
        Do the operations for buying a good.

        :param commodity_ID: int
        :param amount: int
        :param payment: int
        :return:
        """
        self.SpendMoney(payment, from_reserve=ReserveType.ORDERS)
        self.Inventory[commodity_ID].add_inventory(amount, payment)

    def SellGoods(self, commodity_ID, amount, payment):
        self.ReceiveMoney(payment)
        # Need to expense COGS
        COGS = self.Inventory[commodity_ID].RemoveInventory(amount, from_reserve=True)

    def GetInfo(self):
        return f'{self.GID}'


class ProducerLabour(Agent):
    """
    A firm that produces output solely based on labour input.

    Eventually will have producers with commodity inputs. May migrate code to a base class
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

    def DailyProduction(self):
        """
        Production function on a daily basis. Returns a float. The time between production events is the inverse
        of this value.
        :return: float
        """
        return (self.LinearProduction) * float(self.WorkersActual)

    def UnitCost(self):
        """
        Unit Cost of production (float).

        If production remains linear, we could just base this on wages, but we might allow for
        nonlinearities, so we need to calculate the daily production
        :return: float
        """
        return self.DailyProduction() / float(self.WorkersActual * self.Wage)


class CentralGovernment(Agent):
    def __init__(self):
        super().__init__(name='CentralGovernment', money_balance=0)

    def SpendMoney(self, amount, from_reserve=ReserveType.NONE):
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

    def __init__(self, location_id, central_gov_ID, job_guarantee_wage, num_workers=0):
        super().__init__(money_balance=0, name='JobGuarantee', location_ID=location_id)
        self.CentralGovID = central_gov_ID
        self.WorkersActual = num_workers
        self.Employer = True
        self.Inventory = Inventory()
        self.JobGuaranteeWage = job_guarantee_wage
        self.IsCentralGovernment = True
        # Will find the HouseholdGID later...
        self.HouseholdGID = None
        self.EmployerDict = weakref.WeakValueDictionary()

    def SpendMoney(self, amount, from_reserve=ReserveType.NONE):
        self.get_entity(self.CentralGovID).SpendMoney(amount)

    def ReceiveMoney(self, amount):
        self.get_entity(self.CentralGovID).ReceiveMoney(amount)

    def FindEmployers(self):
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

    def RegisterEvents(self):
        """

        :return: list
        """
        payment_event = simulation.ActionEvent(self.GID, self.event_Production, 0., 1.)
        return [(payment_event, (0., 0.1))]

    def event_Production(self, *args):
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
        # self.SpendMoney(payment)
        # HH = agent_based_macro.entity.Entity.GetEntity(self.HouseholdGID)
        # HH.ReceiveWages(payment)
        # JG Production
        food_id = sim.GetCommodityByName('Fud')
        loc = agent_based_macro.entity.Entity.get_entity(self.LocationID)
        production = self.WorkersActual * loc.ProductivityDict[food_id]
        self.Inventory[food_id].add_inventory(production, payment)
        sim.QueueEventDelay(self.GID, self.event_SetOrders, .1)

    def event_SetOrders(self):
        """
        Set up buy/sell orders.

        Keep it as simple as possible, to allow the loop to close.

        May create a simpler interface for these orders.
        :return:
        """
        sim = agent_based_macro.entity.Entity.get_simulation()
        food_id = sim.GetCommodityByName('Fud')
        location = agent_based_macro.entity.Entity.get_entity(self.LocationID)
        market = sim.GetMarket(self.LocationID, food_id)
        production_price = self.JobGuaranteeWage / location.ProductivityDict[food_id]
        # Create a floor price
        buyorder = BuyOrder(production_price * .95, 300, self.GID)
        market.AddNamedBuy(agent=self, name='floor', order=buyorder)
        # Sell production
        amount = self.Inventory[food_id].Amount - self.Inventory[food_id].Reserved
        sellorder = SellOrder(production_price * 1.1, amount, self.GID)
        market.AddNamedSell(agent=self, name='production', order=sellorder)


class HouseholdSector(Agent):
    def __init__(self, location_id, money_balance, target_money, name='household'):
        super().__init__(name, money_balance, location_ID=location_id)
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
        self.ReceiveMoney(amount)
        # Do something more sophisticated for tax payment later.
        taxes = math.floor(0.1 * amount)
        self.ChangeReserves(taxes, ReserveType.TAX)
        sim.PayTaxes(self.GID, taxes)
        self.DailyEarnings += (amount - taxes)

    def RegisterEvents(self):
        """

        :return: list
        """
        payment_event = simulation.Event(self.GID, self.event_CalculateSpending, 0., 1.)
        return [(payment_event, (0.6, 0.7))]

    def event_CalculateSpending(self):
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
        food_id = sim.GetCommodityByName('Fud')
        location = agent_based_macro.entity.Entity.get_entity(self.LocationID)
        market = sim.GetMarket(self.LocationID, food_id)
        ask = market.GetAsk()
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
                market.AddNamedBuy(agent=self, name='DailyBid', order=order)
        # Then add an event for a market order
        sim.QueueEventDelay(self.GID, self.event_MarketOrder, .6)
        # Need to reset daily Earnings. Could be done as a seperate event, but will need a time series
        # object.
        self.DailyEarnings = 0

    def event_MarketOrder(self):
        """
        If there is any available spending power, hit the ask.

        Only spend a certain percentage of cash earmarked for spending.

        :return:
        """
        sim = agent_based_macro.entity.Entity.get_simulation()
        food_id = sim.GetCommodityByName('Fud')
        location = agent_based_macro.entity.Entity.get_entity(self.LocationID)
        market = sim.GetMarket(self.LocationID, food_id)
        ask = market.GetAsk()
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
        market.AddNamedBuy(agent=self, name='"MarketOrder"', order=order)


class Market(agent_based_macro.entity.Entity):
    def __init__(self, name, locationID, commodityID):
        super().__init__(name, ttype='market')
        self.LocationID = locationID
        self.CommodityID = commodityID
        self.BuyList = OrderQueue()
        self.SellList = OrderQueue()
        self.LastPrice = None
        self.LastTime = 0.

    def AddNamedBuy(self, agent, name, order):
        """
        Allow agents to keep a "named" order. New orders automatically cancel order with the same name.
        :param agent: Agent
        :param name: str
        :param order: BuyOrder
        :return:
        """
        name = 'buy_' + name
        ID_existing = agent.NamedOrders.get(name, None)
        if ID_existing is not None:
            self.RemoveBuy(agent, ID_existing)
        self.AddBuy(order)
        agent.NamedOrders[name] = order.OrderID

    def RemoveBuy(self, agent, orderID):
        order = self.BuyList.RemoveOrder(orderID)
        if order is not None:
            value = order.Price * order.Amount
            agent.ChangeReserves(-value, ReserveType.ORDERS)

    def AddNamedSell(self, agent, name, order):
        """
        Allow agents to keep a "named" order. New orders automatically cancel order with the same name.
        :param agent: Agent
        :param name: str
        :param order: BuyOrder
        :return:
        """
        name = 'sel_' + name
        ID_existing = agent.NamedOrders.get(name, None)
        if ID_existing is not None:
            self.RemoveSell(agent, ID_existing)
        self.AddSell(order)
        agent.NamedOrders[name] = order.OrderID

    def RemoveSell(self, agent, orderID):
        order = self.SellList.RemoveOrder(orderID)
        if order is not None:
            agent.Inventory[self.CommodityID].ChangeReserves(-order.Amount)

    def AddBuy(self, buyorder):
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
        buyer = agent_based_macro.entity.Entity.get_entity(buyorder.FirmGID)
        buyer.ChangeReserves(buyorder.Amount * buyorder.Price, ReserveType.ORDERS)
        # If the buy price is less than the ask, we insert into BuyList
        # Otherwise, we transact until either the buy order is completely filled, or
        # the ask has risen past the new order's bid
        while True:
            if len(self.SellList) == 0:
                # No sellers, so automatically add to BuyList
                self.BuyList.InsertOrder(buyorder)
                return
            ask = self.SellList[0].Price
            if buyorder.Price < ask:
                self.BuyList.InsertOrder(buyorder)
                return
            else:
                # Transaction!
                self.LastPrice = ask
                self.LastTime = simulation.GetSimulation().Time
                amount = min(self.SellList[0].Amount, buyorder.Amount)
                seller = agent_based_macro.entity.Entity.get_entity(self.SellList[0].FirmGID)
                payment = amount * ask
                #
                buyer.SpendMoney(payment, from_reserve=ReserveType.ORDERS)
                seller.ReceiveMoney(payment)
                buyer.Inventory[self.CommodityID].add_inventory(amount, payment)
                COGS = seller.Inventory[self.CommodityID].RemoveInventory(amount, from_reserve=True)
                # TODO: Register loss from COGS
                # Then, remove orders as needed.
                buyorder.Amount -= amount
                self.SellList[0].Amount -= amount
                # Remove the front of the sell list if empty.
                self.SellList.CheckEmpty()
                if buyorder.Amount == 0:
                    # Order has been cleared out, quit processing.
                    return

    def AddSell(self, sellorder):
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
        seller = agent_based_macro.entity.Entity.get_entity(sellorder.FirmGID)
        seller.Inventory[self.CommodityID].ChangeReserves(sellorder.Amount)

        # If the sell price is greater than the bid, we insert into SellList
        # Otherwise, we transact until either the order is completely filled, or
        # the bid drops the new order's ask
        while True:
            if len(self.BuyList) == 0:
                # No sellers, so automatically add to BuyList
                self.SellList.InsertOrder(sellorder)
                return
            bid = self.BuyList[0].Price
            if sellorder.Price > bid:
                self.SellList.InsertOrder(sellorder)
                return
            else:
                # Transaction!
                self.LastPrice = bid
                self.LastTime = simulation.GetSimulation().Time
                amount = min(self.BuyList[0].Amount, sellorder.Amount)
                buyer = agent_based_macro.entity.Entity.get_entity(self.BuyList[0].FirmGID)

                payment = amount * bid
                #
                buyer.SpendMoney(payment, from_reserve=ReserveType.ORDERS)
                seller.ReceiveMoney(payment)
                buyer.Inventory[self.CommodityID].add_inventory(amount, payment)
                COGS = seller.Inventory[self.CommodityID].RemoveInventory(amount, from_reserve=True)
                # TODO: Register loss from COGS
                # Clear out empty orders as needed
                self.BuyList[0].Amount -= amount
                sellorder.Amount -= amount
                self.BuyList.CheckEmpty()
                if sellorder.Amount == 0:
                    # Order has been completely filled, quit processing
                    return

    def GetBid(self):
        if len(self.BuyList) > 0:
            return self.BuyList[0].Price
        else:
            return None

    def GetAsk(self):
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

    def __init__(self, name, coords, start_ID, travelling_to_ID, speed=2.):
        super().__init__(name)
        self.StartCoordinates = coords
        self.StartLocID = start_ID
        self.StartTime = 0.
        self.Speed = speed
        self.TargetLocID = travelling_to_ID
        target = agent_based_macro.entity.Entity.get_entity(travelling_to_ID)
        self.TargetCoordinates = target.Coordinates
        self.ArrivalTime = 0.
        if self.StartCoordinates == target.Coordinates:
            # Already there
            self.StartLocID = travelling_to_ID
        else:
            raise NotImplementedError('No support for spawning ship away from planet')

    def GetCoordinate(self, ttime):
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

    def StartMoving(self, new_Target, ttime):
        """
        Move to a new target (always a location, not an arbitrary point.
        :param new_Target:
        :param ttime:
        :return:
        """
        coords = self.GetCoordinate(ttime)
        self.StartLocID = self.LocationID
        self.StartTime = ttime
        self.StartCoordinates = coords
        self.LocationID = TravellingAgent.NoLocationID
        self.TargetLocID = new_Target
        target_loc = agent_based_macro.entity.Entity.get_entity(new_Target)
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
            sim = simulation.GetSimulation()
            ttime = sim.Time
            coords = self.GetCoordinate(ttime)
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
        self.AddEntity(gov)
        self.CentralGovernmentID = gov.GID
        # A location that is not really a location -- off the logical grid.
        self.NonLocationID = None

    def AddEntity(self, entity):
        """
        When we add an Entity that has a money balance, subtract the amount from the CentralGovernment.
        This way we ensure that CentralGovernment Money liability matches private sector Money assets
        without forcing initialisation code to remember to add that operation.

        :param entity: Entity
        :return:
        """
        super().AddEntity(entity)
        if hasattr(entity, 'Money'):
            try:
                gov = agent_based_macro.entity.Entity.get_entity(self.CentralGovernmentID)
            except KeyError:
                # This will blow up when we add the CentralGovernment itself!
                return
            gov.Money -= entity.Money

    def AddLocation(self, location):
        self.AddEntity(location)
        self.Locations.append(location.GID)

    def AddCommodity(self, commodity):
        self.AddEntity(commodity)
        self.Commodities.append(commodity.GID)

    def AddHousehold(self, household):
        """
        Add a household sector object.
        :param household: HouseholdSector
        :return: None
        """
        self.AddEntity(household)
        self.Households[household.LocationID] = household.GID

    def GetMarket(self, loc_id, commod_id):
        return self.Markets[(loc_id, commod_id)]

    def GetCommodityByName(self, commodity_name):
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

    def GenerateMarkets(self):
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
                self.AddEntity(market)
                self.Markets[(loc_id, commod_id)] = market
                self.Markets[(loc_id, com.Name)] = market

    def PayTaxes(self, taxpayer_GID, amount):
        """
        Have entity pay taxes (if it exists).
        :param taxpayer_GID: int
        :param amount: int
        :return:
        """
        try:
            sucker = agent_based_macro.entity.Entity.get_entity(taxpayer_GID)
        except KeyError:
            return
        sucker.SpendMoney(amount, ReserveType.TAX)
        cgov = agent_based_macro.entity.Entity.get_entity(self.CentralGovernmentID)
        cgov.ReceiveMoney(amount)

    def GetActionData(self, agent, *args):
        raise NotImplementedError('need GetActionData')

    def ProcessAction(self, agent, action):
        """
        Handle custom actions (not data or callback actions)

        For now, not creating custom Action subclasses, instead just parse the arguments.

        Supported generic Action arguments:

        'PayWages', <amount>


        :param agent: Agent
        :param action: Action
        :return:
        """
        if action.args[0] == 'PayWages':
            # We assume that there is only a single aggregated Household to get all wages.
            household_id = self.Households[agent.LocationID]
            household: HouseholdSector = agent_based_macro.entity.Entity.get_entity(household_id)
            if len(action.args) == 0:
                raise ValueError('PayWages Action: Need to specify amount as second parameter')
            else:
                amount = int(action.args[1])
            agent.SpendMoney(amount=amount)
            household.receive_wages(amount=amount)
        else:
            raise ValueError(f'Unknown Action arguments: {action.args}')
