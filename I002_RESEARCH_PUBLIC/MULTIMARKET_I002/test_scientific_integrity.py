import unittest
from policy_compare import classify, report

def event(id, choch=None, fvg=None, retest=None, ret=0.2):
    return {"event_id":id,"market":"XAUUSD","choch_time":choch,
            "fvg_time":fvg,"retest_time":retest,
            "base_return60_atr":ret,"base_return120_atr":None}

class ScientificIntegrityTests(unittest.TestCase):
    def test_missing_horizon_visible_without_deleting_event(self):
        e=event("a",ret=None)
        data=report(classify([e]))
        self.assertEqual(data["paired_base_events"],1)
        self.assertEqual(data["by_policy"]["A_SWEEP"]["qualified_events"],1)
        self.assertEqual(data["by_policy"]["A_SWEEP"]["n_missing_base_horizon"],1)
        self.assertIsNone(data["by_policy"]["A_SWEEP"]["mean_on_base_cohort_atr"])
    def test_intersection_and_no_trade_separate(self):
        data=report(classify([event("a",choch="1",fvg="2",retest="3",ret=0.6),
                              event("b",ret=-0.2)]))
        self.assertEqual(data["intersection_qualified_events"],1)
        self.assertEqual(data["by_policy"]["A_SWEEP"]["mean_on_base_cohort_atr"],0.2)
        self.assertEqual(data["by_policy"]["A_SWEEP"]["mean_on_intersection_qualified_atr"],0.6)
        self.assertEqual(data["by_policy"]["C_FVG_FIRST_RETEST"]["n_reason_mentions"],3)
        self.assertEqual(data["by_policy"]["C_FVG_FIRST_RETEST"]["n_no_trade_events"],1)
        self.assertFalse(data["pnl_computed"])
        self.assertIn("NOT policy-specific",data["warning"])
    def test_bad_nonfinite_horizon_rejected(self):
        with self.assertRaises(ValueError):
            classify([event("a",ret=float("nan"))])
    def test_unknown_policy_fails_closed(self):
        rows=classify([event("a")])
        rows[0]["policy"]="UNKNOWN"
        with self.assertRaises(ValueError):
            report(rows)
if __name__=="__main__":
    unittest.main()
