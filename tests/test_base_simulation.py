from unittest import TestCase
import agent_based_macro.base_simulation as base_simulation


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
        COGS = info.remove_inventory(30)
        self.assertEqual(COGS, 60)
        self.assertEqual(70, info.Amount)
        self.assertEqual(201-COGS, info.Cost)
        COGS2 = info.remove_inventory(70)
        self.assertEqual(COGS+COGS2, 201)
        self.assertEqual(0, info.Cost)
        self.assertEqual(0, info.Amount)
