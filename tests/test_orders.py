from unittest import TestCase

import agent_based_macro.orders
import agent_based_macro.orders as orders
from agent_based_macro import base_simulation as base_simulation
from agent_based_macro.orders import OrderType


class MockMarket(orders.MarketBase):
    """
    Create a BaseMarket class that can be tested. Add a member that holds all the accounting
    operations that are implied by test operations, and we can test that they were triggered
    properly.

    We can then test the content of accounting operations as they are implemented.
    """

    def __init__(self):
        super().__init__()
        self.Accounting = []

    def do_accounting(self, firm_gid, order_type, operation, amount, price):
        self.Accounting.append((firm_gid, order_type, operation, amount, price))


class TestMarketBase(TestCase):
    def test_get_time(self):
        obj = orders.MarketBase()
        obj.LastTime = None
        # Base class function always returns 0.
        self.assertEqual(0., obj.get_time())

    def test_do_accounting(self):
        obj = orders.MarketBase()
        # Method does nothing, so nothing to test.
        obj.do_accounting(1, orders.OrderType.BUY, 'add', 10, 10)

    def test_add_buy_1(self):
        obj = MockMarket()
        order = orders.BuyOrder(price=10, amount=10, firm_gid=1)
        obj.add_buy(order)
        # Since both queues are empty, no possible transactions
        self.assertEqual(1, len(obj.BuyList))
        self.assertEqual(0, len(obj.SellList))
        self.assertEqual(order, obj.BuyList[0])
        self.assertEqual([(1, orders.OrderType.BUY, 'add', 10, 10)], obj.Accounting)
        # Add a buy at a lower price - goes to back of queue
        order2 = orders.BuyOrder(price=8, amount=2, firm_gid=2)
        obj.add_buy(order2)
        self.assertEqual(2, len(obj.BuyList))
        self.assertEqual(order2, obj.BuyList[1])
        self.assertEqual(obj.Accounting[1], (2, orders.OrderType.BUY, 'add', 2, 8))
        # Add another buy at a middle price
        order3 = orders.BuyOrder(price=9, amount=1, firm_gid=3)
        obj.add_buy(order3)
        self.assertEqual(3, len(obj.BuyList))
        self.assertEqual(order3, obj.BuyList[1])
        self.assertEqual(obj.Accounting[2], (3, orders.OrderType.BUY, 'add', 1, 9))

    def test_add_sell_1(self):
        obj = MockMarket()
        order = orders.SellOrder(price=10, amount=10, firm_gid=1)
        obj.add_sell(order)
        # Since both queues are empty, no possible transactions
        self.assertEqual(1, len(obj.SellList))
        self.assertEqual(0, len(obj.BuyList))
        self.assertEqual(order, obj.SellList[0])
        self.assertEqual([(1, orders.OrderType.SELL, 'add', 10, 10)], obj.Accounting)
        # Add a sell at a higher price - goes to back of queue
        order2 = orders.SellOrder(price=12, amount=2, firm_gid=2)
        obj.add_sell(order2)
        self.assertEqual(2, len(obj.SellList))
        self.assertEqual(order2, obj.SellList[1])
        self.assertEqual(obj.Accounting[1], (2, orders.OrderType.SELL, 'add', 2, 12))
        # Add another sell at a middle price
        order3 = orders.SellOrder(price=11, amount=1, firm_gid=3)
        obj.add_sell(order3)
        self.assertEqual(3, len(obj.SellList))
        self.assertEqual(order3, obj.SellList[1])
        self.assertEqual(obj.Accounting[2], (3, orders.OrderType.SELL, 'add', 1, 11))

    def test_add_buy_below_offer(self):
        obj = MockMarket()
        # Set up sell orders: overlaps earlier test, so should be OK
        # We could directly insert into the queue, but that poses problems if things change
        order = orders.SellOrder(price=10, amount=10, firm_gid=1)
        obj.add_sell(order)
        order2 = orders.SellOrder(price=12, amount=10, firm_gid=2)
        obj.add_sell(order2)
        # clear accounting
        obj.Accounting = []
        order3 = orders.BuyOrder(price=9, amount=10, firm_gid=3)
        obj.add_buy(order3)
        self.assertEqual(obj.Accounting, [(3, OrderType.BUY, 'add', 10, 9)])
        self.assertEqual(obj.BuyList[0], order3)

    def test_add_buy_transact(self):
        obj = MockMarket()
        # Set up sell orders: overlaps earlier test, so should be OK
        # We could directly insert into the queue, but that poses problems if things change
        order = orders.SellOrder(price=10, amount=10, firm_gid=1)
        obj.add_sell(order)
        order2 = orders.SellOrder(price=12, amount=10, firm_gid=2)
        obj.add_sell(order2)
        # clear accounting
        obj.Accounting = []
        order3 = orders.BuyOrder(price=11, amount=15, firm_gid=3)
        obj.add_buy(order3)
        self.assertEqual(3, len(obj.Accounting))
        self.assertEqual(obj.Accounting[0], (3, OrderType.BUY, 'add', 15, 11))
        # No guarantees on the order of the transaction accounting
        obj.Accounting.pop(0)
        obj.Accounting.sort()
        self.assertEqual(obj.Accounting[0], (1, OrderType.SELL, 'fill', 10, 10))
        self.assertEqual(obj.Accounting[1], (3, OrderType.BUY, 'fill', 10, 10))
        self.assertEqual(obj.BuyList[0], order3)
        # Amount is reduced by fill amount
        self.assertEqual(5, order3.Amount)

    def test_add_buy_fill_all(self):
        obj = MockMarket()
        # Set up sell orders: overlaps earlier test, so should be OK
        # We could directly insert into the queue, but that poses problems if things change
        order = orders.SellOrder(price=10, amount=15, firm_gid=1)
        obj.add_sell(order)
        # clear accounting
        obj.Accounting = []
        order3 = orders.BuyOrder(price=11, amount=10, firm_gid=3)
        obj.add_buy(order3)
        self.assertEqual(3, len(obj.Accounting))
        self.assertEqual(obj.Accounting[0], (3, OrderType.BUY, 'add', 10, 11))
        # No guarantees on the order of the transaction accounting
        obj.Accounting.pop(0)
        obj.Accounting.sort()
        self.assertEqual(obj.Accounting[0], (1, OrderType.SELL, 'fill', 10, 10))
        self.assertEqual(obj.Accounting[1], (3, OrderType.BUY, 'fill', 10, 10))
        self.assertEqual(len(obj.BuyList), 0)
        # Amount is reduced by fill amount
        self.assertEqual(5, obj.SellList[0].Amount)

    def test_add_sell_transact(self):
        obj = MockMarket()
        # Set up buy orders: overlaps earlier test, so should be OK
        # We could directly insert into the queue, but that poses problems if things change
        order = orders.BuyOrder(price=10, amount=10, firm_gid=1)
        obj.add_buy(order)
        order2 = orders.BuyOrder(price=8, amount=10, firm_gid=2)
        obj.add_buy(order2)
        # clear accounting
        obj.Accounting = []
        order3 = orders.SellOrder(price=9, amount=15, firm_gid=3)
        obj.add_sell(order3)
        self.assertEqual(3, len(obj.Accounting))
        self.assertEqual(obj.Accounting[0], (3, OrderType.SELL, 'add', 15, 9))
        obj.Accounting.pop(0)
        # No guarantees on the order of the transaction accounting
        obj.Accounting.sort()
        self.assertEqual(obj.Accounting[0], (1, OrderType.BUY, 'fill', 10, 10))
        self.assertEqual(obj.Accounting[1], (3, OrderType.SELL, 'fill', 10, 10))
        self.assertEqual(obj.SellList[0], order3)
        # Amount is reduced by fill amount
        self.assertEqual(5, order3.Amount)

    def test_add_sell_fill_all(self):
        obj = MockMarket()
        # Set up sell orders: overlaps earlier test, so should be OK
        # We could directly insert into the queue, but that poses problems if things change
        order = orders.BuyOrder(price=10, amount=15, firm_gid=1)
        obj.add_buy(order)
        # clear accounting
        obj.Accounting = []
        order3 = orders.SellOrder(price=9, amount=10, firm_gid=3)
        obj.add_sell(order3)
        self.assertEqual(3, len(obj.Accounting))
        self.assertEqual(obj.Accounting[0], (3, OrderType.SELL, 'add', 10, 9))
        # No guarantees on the order of the transaction accounting
        obj.Accounting.pop(0)
        obj.Accounting.sort()
        self.assertEqual(obj.Accounting[0], (1, OrderType.BUY, 'fill', 10, 10))
        self.assertEqual(obj.Accounting[1], (3, OrderType.SELL, 'fill', 10, 10))
        self.assertEqual(len(obj.SellList), 0)
        # Amount is reduced by fill amount
        self.assertEqual(5, obj.BuyList[0].Amount)

    def test_not_KeepInQueue(self):
        obj = MockMarket()
        order = orders.BuyOrder(price=10, amount=10, firm_gid=1)
        obj.add_buy(order)
        obj.Accounting = []
        order2 = orders.SellOrder(price=10, amount=15, firm_gid=2)
        order2.KeepInQueue = False
        obj.add_sell(order2)
        self.assertEqual(4, len(obj.Accounting))
        obj.Accounting.sort()
        self.assertEqual(obj.Accounting[0], (1, OrderType.BUY, 'fill', 10, 10))
        self.assertEqual(obj.Accounting[1], (2, OrderType.SELL, 'add', 15, 10))
        self.assertEqual(obj.Accounting[2], (2, OrderType.SELL, 'fill', 10, 10))
        self.assertEqual(obj.Accounting[3], (2, OrderType.SELL, 'remove', 5, 10))

    def test_not_KeepInQueue_buy(self):
        obj = MockMarket()
        order = orders.SellOrder(price=10, amount=10, firm_gid=1)
        obj.add_sell(order)
        obj.Accounting = []
        order2 = orders.BuyOrder(price=10, amount=15, firm_gid=2)
        order2.KeepInQueue = False
        obj.add_buy(order2)
        self.assertEqual(4, len(obj.Accounting))
        obj.Accounting.sort()
        self.assertEqual(obj.Accounting[0], (1, OrderType.SELL, 'fill', 10, 10))
        self.assertEqual(obj.Accounting[1], (2, OrderType.BUY, 'add', 15, 10))
        self.assertEqual(obj.Accounting[2], (2, OrderType.BUY, 'fill', 10, 10))
        self.assertEqual(obj.Accounting[3], (2, OrderType.BUY, 'remove', 5, 10))

    def test_remove(self):
        obj = MockMarket()
        # Nothing should happen...
        # Order ID's are negative, so we are asking to remove a non-existent order. This
        # should be fine. Nothing to test, since nothing is supposed to happen.
        obj.remove_order(1)
        order = orders.BuyOrder(price=10, amount=15, firm_gid=1)
        obj.add_buy(order)
        self.assertEqual(1, len(obj.BuyList))
        obj.Accounting = []
        obj.remove_order(order.OrderID)
        self.assertEqual(0, len(obj.BuyList))
        self.assertEqual(0, len(obj.SellList))
        self.assertEqual([(1, OrderType.BUY, 'remove', 15, 10)], obj.Accounting)

    def test_remove_sell(self):
        obj = MockMarket()
        order2 = orders.SellOrder(price=10, amount=15, firm_gid=2)
        obj.add_sell(order2)
        self.assertEqual(1, len(obj.SellList))
        obj.Accounting = []
        obj.remove_order(order2.OrderID)
        self.assertEqual(0, len(obj.SellList))
        self.assertEqual([(2, OrderType.SELL, 'remove', 15, 10)], obj.Accounting)

    def test_order_mismatch(self):
        obj = MockMarket()
        self.assertRaises(ValueError, obj.add_sell, orders.BuyOrder(1, 1, 1))
        self.assertRaises(ValueError, obj.add_buy, orders.SellOrder(1, 1, 1))



class TestBaseOrder(TestCase):
    def test_get_order(self):
        order = orders.BuyOrder(1, 1, 1)
        self.assertEqual(order, orders.BaseOrder.get_order(order.OrderID))

    def test_amount_positive(self):
        # Create a dummy function that should blow up since amount=0
        def f():
            orders.BuyOrder(price=1, amount=0, firm_gid=0)
        self.assertRaises(ValueError, f)


class TestOrderQueue(TestCase):
    def test_insert_order(self):
        ord0 = agent_based_macro.orders.BuyOrder(21, 1, 0)
        ord1 = agent_based_macro.orders.BuyOrder(22, 1, 1)
        market = base_simulation.Market('market', 1, 1)
        market.BuyList.insert_order(ord0)
        self.assertEqual(market.BuyList[0].FirmGID, 0)
        market.BuyList.insert_order(ord1)
        self.assertEqual(market.BuyList[0].FirmGID, 1)
        ord2 = agent_based_macro.orders.BuyOrder(22, 2, 2)
        market.BuyList.insert_order(ord2)
        self.assertEqual(market.BuyList[0].FirmGID, 1)
        ord0 = agent_based_macro.orders.BuyOrder(21, 1, 3)
        market.BuyList.insert_order(ord2)
        ord3 = agent_based_macro.orders.SellOrder(22, 1, 1)
        ord4 = agent_based_macro.orders.SellOrder(22, 2, 2)
        market.SellList.insert_order(ord3)
        market.SellList.insert_order(ord4)
        self.assertEqual(market.SellList[0].FirmGID, 1)
        ord5 = agent_based_macro.orders.SellOrder(21, 2, 5)
        market.SellList.insert_order(ord5)
        self.assertEqual(market.SellList[0].FirmGID, 5)

    def test_remove(self):
        ord0 = agent_based_macro.orders.BuyOrder(21, 1, 0)
        id_ord0 = ord0.OrderID
        obj = orders.OrderQueue()
        obj.insert_order(ord0)
        self.assertIsNone(obj.remove_order(id_ord0 + 1))
        self.assertEqual(1, len(obj))
        out = obj.remove_order(id_ord0)
        self.assertEqual(out, ord0)
        self.assertEqual(0, len(obj))
