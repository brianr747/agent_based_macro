from unittest import TestCase
import agent_based_macro.base_simulation as base_simulation

class TestOrderQueue(TestCase):
    def test_insert_order(self):
        ord0 = base_simulation.BuyOrder(21, 1, 0)
        ord1 = base_simulation.BuyOrder(22, 1, 1)
        market = base_simulation.Market('market', 1, 1)
        market.BuyList.InsertOrder(ord0)
        self.assertEqual(market.BuyList[0].FirmGID, 0)
        market.BuyList.InsertOrder(ord1)
        self.assertEqual(market.BuyList[0].FirmGID, 1)
        ord2 = base_simulation.BuyOrder(22, 2, 2)
        market.BuyList.InsertOrder(ord2)
        self.assertEqual(market.BuyList[0].FirmGID, 1)
        ord0 = base_simulation.BuyOrder(21, 1, 3)
        market.BuyList.InsertOrder(ord2)
        ord3 = base_simulation.SellOrder(22, 1, 1)
        ord4 = base_simulation.SellOrder(22, 2, 2)
        market.SellList.InsertOrder(ord3)
        market.SellList.InsertOrder(ord4)
        self.assertEqual(market.SellList[0].FirmGID, 1)
        ord5 = base_simulation.SellOrder(21, 2, 5)
        market.SellList.InsertOrder(ord5)
        self.assertEqual(market.SellList[0].FirmGID, 5)

