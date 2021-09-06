"""
Module that holds the Order handling: buy/sell order classes, OrderQueue.
"""

import bisect
import enum
import weakref
from abc import ABC, abstractmethod

# Order ID: all negative, so we don't repeat Entity IDs.
GLastOrderID = -1
# Another lookup
GOrderDict = weakref.WeakValueDictionary()


class OrderType(enum.Enum):
    BUY = 0
    SELL = 1


class OrderQueue(object):
    def __init__(self):
        self.Orders = []

    def __getitem__(self, item):
        return self.Orders[item]

    def __len__(self):
        return len(self.Orders)

    def check_empty(self):
        """
        If the front order has an Amount of 0, pop it. Since the quantity has been reduced to zero,
        no accounting issues.
        :return:
        """
        if len(self.Orders) > 0:
            if self.Orders[0].Amount == 0:
                self.Orders.pop(0)

    def insert_order(self, order):
        bisect.insort_right(self.Orders, order)

    def remove_order(self, order_id):
        """

        Returns the removed order, or None if it does not exist.

        :param order_id:
        :return: BaseOrder
        """
        found = None
        for order in self.Orders:
            if order.OrderID == order_id:
                found = order
                break
        if found is not None:
            self.Orders.remove(found)
            return found
        else:
            return None


class BaseOrder(ABC):
    def __init__(self, price, amount, firm_gid):
        if amount <= 0:
            raise ValueError('Amount must be strictly positive')
        global GLastOrderID
        global GOrderDict
        self.Price = int(price)
        self.Amount = int(amount)
        self.OrderID = GLastOrderID
        self.FirmGID = firm_gid
        self.KeepInQueue = True
        GOrderDict[GLastOrderID] = self
        GLastOrderID -= 1

    @staticmethod
    def get_order(order_id):
        global GOrderDict
        return GOrderDict[order_id]

    @abstractmethod # pragma: no cover
    def __lt__(self, other):
        """
        :param other: BaseOrder
        :return: bool
        """
        pass


class BuyOrder(BaseOrder):
    def __lt__(self, other):
        """Comparison order for insertion into OrderQueue"""
        return self.Price > other.Price


class SellOrder(BaseOrder):
    def __lt__(self, other):
        return self.Price < other.Price


class MarketBase(object):
    """
    Base class for markets. Markets in simulations will need to fill in some
    missing pieces. For example, not a Entity.
    """

    def __init__(self):
        self.BuyList = OrderQueue()
        self.SellList = OrderQueue()
        self.LastPrice = None
        self.LastTime = None

    def get_time(self):
        """
        Subclasses will need to deal with getting the simulation time of the
        transaction. This class always returns 0.

        :return: float
        """
        return 0.

    def do_accounting(self, firm_gid, order_type, operation, amount, price):
        """
        Do the accounting operations associated with an order.
        Not passing in the BuyOrder/SellOrder itself since we may only have partial
        fill of an order.

        Rather than create a new enum, the "operation" is a string which is one of
        the following: 'add', 'fill', 'remove' (i.e., without filling).

        Subclass markets will have to implement the accounting operations.
        (I have split this out to make unit testing easier: this class handles the
        market logic, and other methods will handle the accounting, which will vary
        based on the simulation.)

        :param firm_gid: int
        :param order_type: OrderType
        :param operation: str
        :param amount: int
        :param price: int
        :return:
        """
        pass

    def add_buy(self, buy_order):
        """
        Add a BuyOrder to the market, determining whether transactions occur.

        The effect of transactions is handled by do_accounting(), which is implemented
        in subclasses. This class only really handles what is happening to the order
        queues.

        For now, add_buy and add_sell are separate methods. It could be converted
        to a single method which flips logic based on whether it is a buy or sell,
        but I will keep the code mirrored for now.

        :param buy_order: BuyOrder
        :return:
        """
        if not isinstance(buy_order, BuyOrder):
            raise ValueError('must pass a BuyOrder to add_buy()')
        self.do_accounting(buy_order.FirmGID, OrderType.BUY, 'add', buy_order.Amount,
                           buy_order.Price)
        # If the buy price is less than the ask, we insert into BuyList
        # Otherwise, we transact until either the buy order is completely filled, or
        # the ask has risen past the new order's bid
        while True:
            try:
                ask = self.SellList[0].Price
            except IndexError:
                ask = None
            if (ask is None) or (buy_order.Price < ask):
                # Bid price is below ask, so add to BuyList
                if buy_order.KeepInQueue:
                    self.BuyList.insert_order(buy_order)
                else:
                    self.do_accounting(buy_order.FirmGID, OrderType.BUY, 'remove', buy_order.Amount,
                                       buy_order.Price)
                return
            else:
                # Transaction!
                self.LastPrice = ask
                self.LastTime = self.get_time()
                amount = min(self.SellList[0].Amount, buy_order.Amount)
                self.do_accounting(firm_gid=buy_order.FirmGID, order_type=OrderType.BUY,
                                   operation='fill', amount=amount, price=ask)
                self.do_accounting(firm_gid=self.SellList[0].FirmGID, order_type=OrderType.SELL,
                                   operation='fill', amount=amount, price=ask)
                # Then, decrease both order sizes by the fill amount.
                buy_order.Amount -= amount
                self.SellList[0].Amount -= amount
                # Remove the front of the sell list if empty.
                self.SellList.check_empty()
                if buy_order.Amount == 0:
                    # Order has been cleared out, quit processing.
                    return

    def add_sell(self, sell_order):
        """
        Add a SellOrder to the market, determining whether transactions occur.

        The effect of transactions is handled by do_accounting(), which is implemented
        in subclasses. This class only really handles what is happening to the order
        queues.

        For now, add_buy and add_sell are separate methods. It could be converted
        to a single method which flips logic based on whether it is a buy or sell,
        but I will keep the code mirrored for now.

        :param sell_order: BuyOrder
        :return:
        """
        if not isinstance(sell_order, SellOrder):
            raise ValueError('must pass a SellOrder to sell_order()')
        self.do_accounting(sell_order.FirmGID, OrderType.SELL, 'add', sell_order.Amount,
                           sell_order.Price)
        # If the buy price is less than the ask, we insert into BuyList
        # Otherwise, we transact until either the buy order is completely filled, or
        # the ask has risen past the new order's bid
        while True:
            try:
                bid = self.BuyList[0].Price
            except IndexError:
                bid = None
            if (bid is None) or (sell_order.Price > bid):
                # No transaction
                if sell_order.KeepInQueue:
                    self.SellList.insert_order(sell_order)
                else:
                    self.do_accounting(sell_order.FirmGID, OrderType.SELL, 'remove', sell_order.Amount,
                                       sell_order.Price)
                return
            else:
                # Transaction!
                self.LastPrice = bid
                self.LastTime = self.get_time()
                amount = min(self.BuyList[0].Amount, sell_order.Amount)
                self.do_accounting(firm_gid=sell_order.FirmGID, order_type=OrderType.SELL,
                                   operation='fill', amount=amount, price=bid)
                self.do_accounting(firm_gid=self.BuyList[0].FirmGID, order_type=OrderType.BUY,
                                   operation='fill', amount=amount, price=bid)
                # Then, decrease both order sizes by the fill amount.
                sell_order.Amount -= amount
                self.BuyList[0].Amount -= amount
                # Remove the front of the sell list if empty.
                self.BuyList.check_empty()
                if sell_order.Amount == 0:
                    # Order has been cleared out, quit processing.
                    return

    def remove_order(self, order_id):
        """
        Remove an order (and invoke the accounting).

        Unlike the add orders, will work on either type.

        Does not throw an exception if the order is not in the Market. The assumption is that
        the order_id is out of date, and we quietly eat it.

        :param order_id: int
        :return:
        """
        try:
            order = BaseOrder.get_order(order_id)
        except KeyError:
            return
        # Switch to match in Python 3.10 <?>
        if isinstance(order, BuyOrder):
            queue = self.BuyList
            order_type = OrderType.BUY
        else:
            queue = self.SellList
            order_type = OrderType.SELL
        found : BaseOrder = queue.remove_order(order_id)
        if found is not None:
            self.do_accounting(firm_gid=found.FirmGID, order_type=order_type, operation='remove',
                               amount=found.Amount, price=found.Price)

