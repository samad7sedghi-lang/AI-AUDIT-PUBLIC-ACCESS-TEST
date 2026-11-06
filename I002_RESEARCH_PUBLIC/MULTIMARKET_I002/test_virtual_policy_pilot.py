"""Synthetic-only pilot integration; no real broker economics or orders."""
import tempfile
import unittest
from datetime import datetime,timedelta
from pathlib import Path
from virtual_policy_pilot import run_virtual_policy_pilot, load_ticks_csv
from virtual_execution import simulate_buy
from event_runner import execute
from test_integrity_followups import full_sessions,csv_data,manifest

def time(h,m,s=0):
    return datetime(2026,1,2,h,m,s)

def ticks():
    return [(time(10,0,30),100,100.1),
            (time(10,1,0),100,100.1),
            (time(10,1,1),100,100.2),
            (time(10,2,0),101.3,101.4),
            (time(10,4,1),100,100.1),
            (time(10,6,0),101.2,101.3),
            (time(10,8,1),100,100.1),
            (time(10,9,0),101.2,101.3)]
def event(full=True):
    return {"event_id":"XAUUSD:2026-01-02 10:00:00","market":"XAUUSD",
            "event_time":"2026-01-02T10:00:00",
            "choch_time":"2026-01-02T10:03:00",
            "fvg_time":"2026-01-02T10:05:00" if full else None,
            "retest_time":"2026-01-02T10:07:00" if full else None,
            "overlaps_previous_episode":False}
def model(semantics="OPEN"):
    return {"stop_distance":1,"target_distance":1,
            "commission_roundtrip_price":0.0,"max_spread_price":0.5,
            "latency_ms":0,"slippage_price":0.0,
            "bar_timestamp_semantics":semantics}

class VirtualPolicyTests(unittest.TestCase):
    def test_all_three_signals_after_bar_close(self):
        result=run_virtual_policy_pilot([event()],ticks(),model())
        self.assertEqual(result["policy_rows"],3)
        self.assertTrue(all(x["status"]=="EXIT_TARGET" for x in result["rows"]))
        self.assertEqual(result["rows"][0]["signal_time"],"2026-01-02T10:01:00")
        self.assertAlmostEqual(result["rows"][0]["price_delta_per_unit"],1.1)
        self.assertFalse(result["net_usd_pnl_computed"])
        self.assertFalse(result["portfolio_execution_simulated"])

    def test_no_trade_is_retained_not_fake_zero_pnl(self):
        result=run_virtual_policy_pilot([event(False)],ticks(),model())
        self.assertEqual(result["rows"][2]["status"],"NO_TRADE")
        self.assertIsNone(result["rows"][2]["price_delta_per_unit"])
        self.assertEqual(result["rows"][1]["status"],"EXIT_TARGET")

    def test_chronology_fails_closed(self):
        bad=event()
        bad["retest_time"]="2026-01-02T10:02:00"
        with self.assertRaises(ValueError):
            run_virtual_policy_pilot([bad],ticks(),model())

    def test_missing_m1_bar_semantics_rejected(self):
        broken=model()
        broken["bar_timestamp_semantics"]="UNKNOWN"
        with self.assertRaises(ValueError):
            run_virtual_policy_pilot([event()],ticks(),broken)

    def test_adverse_slippage_and_latency(self):
        sample=[(1,100,100.1),(1.2,100,100.2),(2,100,100.2),(3,101.5,101.6)]
        result=simulate_buy(sample,1,1,1,commission_roundtrip=0.1,
                            latency_ms=500,slippage_price=0.1)
        self.assertEqual(result["status"],"EXIT_TARGET")
        self.assertAlmostEqual(result["entry_ask"],100.3)
        self.assertAlmostEqual(result["pnl_price"],1.0)

    def test_optional_runner_tick_pilot_synthetic_contract(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            m1=root/"m1.csv"
            m1.write_text(csv_data(full_sessions()),encoding="utf-8")
            tick=root/"tick.csv"
            tick.write_text("timestamp,bid,ask\n2026-01-03T00:01:00,100,100.1\n",encoding="utf-8")
            data=manifest(m1)
            data["markets"]["XAUUSD"]["tick_csv"]=str(tick)
            data["virtual_pilot"]={"enabled":True,"model":model()}
            result=execute(data,root/"manifest.json")
            x=result["markets"]["XAUUSD"]
            self.assertEqual(x["status"],"DESCRIPTIVE_ONLY_REVIEW_REQUIRED")
            self.assertEqual(x["virtual_pilot"]["status"],"EXPLORATORY_NO_EVENTS")
            self.assertEqual(x["virtual_pilot"]["policy_rows"],0)
            self.assertFalse(result["pnl_computed"])
            self.assertFalse(result["order_path"])
            self.assertEqual(result["markets"]["EURUSD"]["status"],"BLOCKED")
if __name__=="__main__":
    unittest.main()
