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
import bisect
import weakref
import enum
import math

from agent_based_macro.simulation import SimulationError
import agent_based_macro.simulation as simulation

# Order ID: all negative, so we don't re-use Entity IDs.
GLastOrderID = -1
# Another lookup
GOrderDict = weakref.WeakValueDictionary()


class NoMoneyError(SimulationError):
    pass


class NoFreeMoneyError(SimulationError):
    """Attempting to spend beyond free money capacity"""
    pass


class ReserveError(SimulationError):
    """ Attempting to reduce reserve to a negative amount"""
    pass

class Location(simulation.Entity):
    def __init__(self,name):
        super().__init__(name=name, ttype='location')
        # Duh!
        self.LocationID = self.GID
        self.EntityList = []

    def Init(self):
        """
        Set up the entity list for the location. Meant to be called near the end of
        the simulation initialisation step. Once dynamic agent creation is allowed, will need to maintain
        as changes made.
        :return:
        """
        self.EntityList = []
        sim = simulation.Entity.GetEntity(simulation.SIMULATIONID)
        # For simplicity, do this in a loop
        for ent in sim.EntityList:
            if ent.GID == self.GID:
                continue
            if ent.IsDead:
                continue
            if hasattr(ent, 'LocationID') and ent.LocationID == self.LocationID:
                self.EntityList.append(ent.GID)

class BuyOrder(object):
    def __init__(self, price, amount, firm_gid):
        if amount <= 0:
            raise ValueError('Amount must be strictly positive')
        global GLastOrderID
        global GOrderDict
        self.Price = price
        self.Amount = amount
        self.OrderID = GLastOrderID
        self.FirmGID = firm_gid
        GOrderDict[GLastOrderID] = self
        GLastOrderID -= 1

    @staticmethod
    def GetOrder(orderID):
        global GOrderDict
        return GOrderDict[orderID]

    def __lt__(self, other):
        """Comparison order for insertion into OrderQueue"""
        return self.Price > other.Price


class SellOrder(BuyOrder):
    def __lt__(self, other):
        return self.Price < other.Price


class OrderQueue(object):
    def __init__(self):
        self.Orders = []

    def __getitem__(self, item):
        return self.Orders[item]

    def InsertOrder(self, order):
        bisect.insort_right(self.Orders, order)


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

    def AddInventory(self, amount, cost):
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
            COGS = round(float(self.Cost*amount)/float(self.Amount))
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


class Agent(simulation.Entity):
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
            if change + self.ReserveMoney > self.Money:
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
            if ReserveType.WAGES == reserve_type:
                if self.ReserveWages >= -change:
                    self.ReserveWages += change
                else:
                    raise ReserveError(f'attempt to set negative reserves [{self.GID}]')
            if ReserveType.TAX == reserve_type:
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

        (This might migrate to Entity.)



        These include:
        Events that define the "economic rules" for the Agent - no behavioral input.
        - Wage payment cycle. (pay workers, workers start working.)
        - The JobGuarantee worker migration step.
        - Tax payment step
        - Household sector consumption step.

        Production events - some might be scheduled (just before decision events), others generated
        dynamically based on when units are produced (?).

        Behavioural Events
        - Daily planning event (e.g., set target workforce, wages, market orders, etc.)
        - Liquidity management event before wage/tax payments. (Do we need to raise cash?)
        - Events set by the "behavioral AI logic": market orders being filled, reaction to production,
          periodic ticks to look at market pricing to adjust orders, etc.


        Possible protocol:
        ((action1, ... actionN), (first_start, first_end), repeat)
        actions = list of actions, will be called in order.
        (first_start, first_end) = range of times for first call. Once we have a lot of entities, spread out
                                   the events for a class across the range.
                                   (If we have all the events at the exact same time, time will freeze in realtime
                                   mode.)
        repeat = repeat period (typically 1. (daily) or 10. (monthly). Event will be re-inserted with the CallTime
        incremented by the repeat value.

        (The GID will be filled in by the Simulation.)

        :return: tuple
        """
        return ()


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
        return (self.LinearProduction)*float(self.WorkersActual)

    def UnitCost(self):
        """
        Unit Cost of production (float).

        If production remains linear, we could just base this on wages, but we might allow for
        nonlinearities, so we need to calculate the daily production
        :return: float
        """
        return self.DailyProduction()/float(self.WorkersActual*self.Wage)


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
        # Will find the HouseholdGID later...
        self.HouseholdGID = None
        self.EmployerDict = weakref.WeakValueDictionary()

    def SpendMoney(self, amount, from_reserve=ReserveType.NONE):
        self.GetEntity(self.CentralGovID).SpendMoney(amount)

    def ReceiveMoney(self, amount):
        self.GetEntity(self.CentralGovID).ReceiveMoney(amount)

    def FindEmployers(self):
        """
        Find all the employers on a location. Call during initialisation step.

        Once we can have creation/destruction of employers, will need to update live.
        :return:
        """
        self.EmployerDict = weakref.WeakValueDictionary()
        sim = self.GetEntity(simulation.SIMULATIONID)
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
        payment_event = simulation.Event(self.GID, self.event_Payment, 0., 1.)
        return [(payment_event, (0., 0.1))]

    def event_Payment(self):
        sim = simulation.Entity.GetSimulation()
        if self.HouseholdGID is None:
            try:
                self.HouseholdGID = sim.Households[self.LocationID]
            except KeyError:
                raise ValueError('Did not add the Household to the simulation.')
        # Since the HouseholdSector and central government are indestructible (I hope), this transfer will always
        # be valid. (Normally, need to validate existence of all entities.)
        payment = self.WorkersActual * self.JobGuaranteeWage
        self.SpendMoney(payment)
        HH = simulation.Entity.GetEntity(self.HouseholdGID)
        HH.ReceiveWages(payment)
        # JG Production
        food_id = sim.GetCommodityByName('Fud')
        production = self.WorkersActual * 15
        self.Inventory[food_id].AddInventory(production, payment)
        sim.QueueEventDelay(self.GID, self.event_SetOrders, .1)

    def event_SetOrders(self):
        print('Orders!')


class HouseholdSector(Agent):
    def __init__(self, location_id, money_balance, target_money, name='household'):
        super().__init__(name, money_balance, location_ID=location_id)
        self.TargetMoney = target_money
        self.DailyEarnings = 0

    def ReceiveWages(self, amount):
        """
        Receive wages, and pay taxes (boo!)
        Increases DailyEarnings, which is used in the consumption function. Other transactions might not
        feed into these earnings.
        :param amount:
        :return:
        """
        sim = simulation.Entity.GetEntity(simulation.SIMULATIONID)
        self.ReceiveMoney(amount)
        # Do something more sophisticated for tax payment later.
        taxes = math.floor(0.1 * amount)
        self.ChangeReserves(taxes, ReserveType.TAX)
        sim.PayTaxes(self.GID, taxes)
        self.DailyEarnings += (amount - taxes)


class Market(simulation.Entity):
    def __init__(self, name, locationID, commodityID):
        super().__init__(name, ttype='market')
        self.LocationID = locationID
        self.CommodityID = commodityID
        self.BuyList = OrderQueue()
        self.SellList = OrderQueue()


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
                gov = simulation.Entity.GetEntity(self.CentralGovernmentID)
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
            c_obj = simulation.Entity.GetEntity(c)
            if c_obj.Name == commodity_name:
                return c

    def GenerateMarkets(self):
        """
        Call this after all locations and commodities are built, so long as you want all combinations supported
        :return:
        """
        for loc_id in self.Locations:
            loc = simulation.Entity.GetEntity(loc_id)
            for commod_id in self.Commodities:
                com = simulation.Entity.GetEntity(commod_id)
                name = f'{com.Name}@{loc.Name}'
                market = Market(name, loc_id, commod_id)
                self.AddEntity(market)
                self.Markets[(loc_id, commod_id)] = market

    def PayTaxes(self, taxpayer_GID, amount):
        """
        Have entity pay taxes (if it exists).
        :param taxpayer_GID: int
        :param amount: int
        :return:
        """
        try:
            sucker = simulation.Entity.GetEntity(taxpayer_GID)
        except KeyError:
            return
        sucker.SpendMoney(amount, ReserveType.TAX)
        cgov = simulation.Entity.GetEntity(self.CentralGovernmentID)
        cgov.ReceiveMoney(amount)







