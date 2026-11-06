import unittest
from virtual_execution import simulate_buy

class VirtualTests(unittest.TestCase):
    def test_entry_after_signal_and_bid_exit_with_cost(self):
        ticks=[(1,100,100.1),(2,100,100.2),(3,101.4,101.5)]
        r=simulate_buy(ticks,1,1,1,0.1)
        self.assertEqual(r["status"],"EXIT_TARGET")
        self.assertAlmostEqual(r["pnl_price"],1.1)
        self.assertEqual(r["entry_ask"],100.2)
    def test_no_fill_without_later_quote(self):
        self.assertEqual(simulate_buy([(1,100,100.1)],1,1,1)["status"],"NO_FILL")
    def test_spread_cap_blocks(self):
        self.assertEqual(simulate_buy([(1,100,100.1),(2,100,100.9)],1,1,1,max_spread=0.2)["reason"],"SPREAD_CAP")
    def test_stop(self):
        r=simulate_buy([(1,100,100.1),(2,100,100.2),(3,98,98.1)],1,1,1)
        self.assertEqual(r["status"],"EXIT_STOP")
    def test_no_exit_tick_is_not_fake_pnl(self):
        r=simulate_buy([(1,100,100.1),(2,100,100.2)],1,1,1)
        self.assertEqual(r["status"],"OPEN_UNRESOLVED")
        self.assertIsNone(r["pnl_price"])
    def test_bad_quote_fails_closed(self):
        with self.assertRaises(ValueError):
            simulate_buy([(1,100,99)],0,1,1)
if __name__=="__main__":
    unittest.main()
