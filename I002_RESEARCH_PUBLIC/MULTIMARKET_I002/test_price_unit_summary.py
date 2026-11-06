import unittest
from virtual_policy_pilot import run_virtual_policy_pilot
from test_virtual_policy_pilot import event, ticks, model

class SummaryTests(unittest.TestCase):
    def test_empty_events_are_distinguished(self):
        x=run_virtual_policy_pilot([],ticks(),model())
        self.assertEqual(x["status"],"EXPLORATORY_NO_EVENTS")
        self.assertEqual(x["policy_rows"],0)
        for p in x["by_policy"].values():
            self.assertIsNone(p["mean_price_delta_per_unit_on_closed_exits"])

    def test_policy_denominators_preserved(self):
        x=run_virtual_policy_pilot([event(False)],ticks(),model())
        a=x["by_policy"]["A_SWEEP"]
        c=x["by_policy"]["C_FVG_FIRST_RETEST"]
        self.assertEqual(a["base_events"],1)
        self.assertEqual(a["n_closed_hypothetical_exits"],1)
        self.assertAlmostEqual(a["mean_price_delta_per_unit_on_closed_exits"],1.1)
        self.assertEqual(c["status_counts"]["NO_TRADE"],1)
        self.assertIsNone(c["mean_price_delta_per_unit_on_closed_exits"])
        self.assertFalse(c["economic_policy_comparison_valid"])

if __name__=="__main__":
    unittest.main()
