"""
Module that holds the Order handling: buy/sell order classes, OrderQueue.
"""


import bisect
import weakref


# Order ID: all negative, so we don't repeat Entity IDs.
GLastOrderID = -1
# Another lookup
GOrderDict = weakref.WeakValueDictionary()


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


class BaseOrder(object):
    def __init__(self, price, amount, firm_gid):
        if amount <= 0:
            raise ValueError('Amount must be strictly positive')
        global GLastOrderID
        global GOrderDict
        self.Price = int(price)
        self.Amount = int(amount)
        self.OrderID = GLastOrderID
        self.FirmGID = firm_gid
        GOrderDict[GLastOrderID] = self
        GLastOrderID -= 1

    @staticmethod
    def get_order(order_id):
        global GOrderDict
        return GOrderDict[order_id]

    def __lt__(self, other):
        """Comparison order for insertion into OrderQueue"""
        raise NotImplementedError('Should not instantiate a BaseOrder')


class BuyOrder(BaseOrder):
    """
    Just create a
    """
    def __lt__(self, other):
        """Comparison order for insertion into OrderQueue"""
        return self.Price > other.Price


class SellOrder(BuyOrder):
    def __lt__(self, other):
        return self.Price < other.Price
