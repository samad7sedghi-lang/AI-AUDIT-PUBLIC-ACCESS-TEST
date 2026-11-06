import unittest
from policy_compare import classify, report, POLICIES

class CohortTests(unittest.TestCase):
    def test_no_trade_retained_and_not_pnl(self):
        events=[{"event_id":"X:1","market":"X","base_return60_atr":0.5,
                 "base_return120_atr":0.2,"choch_time":None,"fvg_time":None,"retest_time":None},
                {"event_id":"X:2","market":"X","base_return60_atr":-0.2,
                 "base_return120_atr":-0.4,"choch_time":"t1","fvg_time":"t2",
                 "retest_time":"t3","retest_return60_atr":0.1}]
        rows=classify(events)
        self.assertEqual(len(rows),6)
        result=report(rows)
        self.assertEqual(result["paired_base_events"],2)
        self.assertEqual(result["by_policy"]["A_SWEEP"]["qualified_events"],2)
        self.assertEqual(result["by_policy"]["B_CHOCH"]["no_trade"],1)
        self.assertEqual(result["by_policy"]["C_FVG_FIRST_RETEST"]["no_trade"],1)
        self.assertTrue(all(r["net_pnl_r"] is None for r in rows))
        self.assertFalse(result["pnl_computed"])
    def test_duplicate_cohort_fails_closed(self):
        e={"event_id":"X:1","market":"X","base_return60_atr":None,
           "base_return120_atr":None,"choch_time":None,"retest_time":None}
        with self.assertRaises(ValueError):
            report(classify([e,e]))
if __name__=="__main__":
    unittest.main()
