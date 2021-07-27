from unittest import TestCase
import agent_based_macro.base_simulation as base_simulation
import agent_based_macro.orders


class TestOrderQueue(TestCase):
    def test_insert_order(self):
        ord0 = agent_based_macro.orders.BuyOrder(21, 1, 0)
        ord1 = agent_based_macro.orders.BuyOrder(22, 1, 1)
        market = base_simulation.Market('market', 1, 1)
        market.BuyList.InsertOrder(ord0)
        self.assertEqual(market.BuyList[0].FirmGID, 0)
        market.BuyList.InsertOrder(ord1)
        self.assertEqual(market.BuyList[0].FirmGID, 1)
        ord2 = agent_based_macro.orders.BuyOrder(22, 2, 2)
        market.BuyList.InsertOrder(ord2)
        self.assertEqual(market.BuyList[0].FirmGID, 1)
        ord0 = agent_based_macro.orders.BuyOrder(21, 1, 3)
        market.BuyList.InsertOrder(ord2)
        ord3 = agent_based_macro.orders.SellOrder(22, 1, 1)
        ord4 = agent_based_macro.orders.SellOrder(22, 2, 2)
        market.SellList.InsertOrder(ord3)
        market.SellList.InsertOrder(ord4)
        self.assertEqual(market.SellList[0].FirmGID, 1)
        ord5 = agent_based_macro.orders.SellOrder(21, 2, 5)
        market.SellList.InsertOrder(ord5)
        self.assertEqual(market.SellList[0].FirmGID, 5)


class TestInventory(TestCase):
    def test_get_empty(self):
        obj = base_simulation.Inventory()
        info = obj[1]
        self.assertIsInstance(info, base_simulation.InventoryInfo)
        self.assertEqual(info.CommodityID, 1)

    def test_COGS_1(self):
        info = base_simulation.InventoryInfo(1)
        info.add_inventory(100, 201)
        self.assertEqual(info.Amount, 100)
        COGS = info.RemoveInventory(30)
        self.assertEqual(COGS, 60)
        self.assertEqual(70, info.Amount)
        self.assertEqual(201-COGS, info.Cost)
        COGS2 = info.RemoveInventory(70)
        self.assertEqual(COGS+COGS2, 201)
        self.assertEqual(0, info.Cost)
        self.assertEqual(0, info.Amount)
