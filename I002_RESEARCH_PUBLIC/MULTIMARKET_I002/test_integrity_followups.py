"""Read-only regression tests for DeepSeek I002 integrity follow-ups."""
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from i002_event_lab_snapshot import Bar, scan
from temporal_integrity import verify_temporal_integrity
from manifest_gate import evaluate, MARKETS

def b(t, o=100, h=100.6, l=99.4, c=100, pdl=98, pdr=5, atr=1):
    return Bar(t, o, h, l, c, 0.01, pdl, pdr, atr)

def overlapping_bars():
    start=datetime(2026,1,2,10)
    series=[b(start+timedelta(minutes=i),o=100+i*.01,h=100.6+i*.01,
              l=99.4+i*.01,c=100+i*.01) for i in range(250)]
    for index in (10,20):
        series[index]=replace(series[index],l=95,c=99)
    return series

def staged_bars():
    start=datetime(2026,1,2,10)
    series=[b(start+timedelta(minutes=i)) for i in range(200)]
    series[6]=replace(series[6],h=105)
    series[10]=replace(series[10],l=95,c=99)
    series[12]=replace(series[12],o=104,h=107,l=103.5,c=106)
    series[14]=replace(series[14],o=111,h=112,l=110,c=111.5)
    series[15]=replace(series[15],o=109,h=111,l=106,c=109)
    return series

def full_sessions():
    start=datetime(2026,1,2)
    out=[]
    for i in range(2880):
        t=start+timedelta(minutes=i)
        out.append(b(t,o=100,h=100.5,l=99.5,c=100,
                     pdl=98 if i<1440 else 99.5,
                     pdr=5 if i<1440 else 1,atr=1))
    return out

def csv_data(bars):
    header="timestamp,open,high,low,close,spread_price,prev_d1_low,prev_d1_range,atr_m1_20\n"
    return header+"".join(f"{x.time.isoformat()},{x.o},{x.h},{x.l},{x.c},{x.spread},{x.prev_low},{x.prev_range},{x.atr}\n" for x in bars)

def manifest(file):
    rec={"broker_symbol":"SYNTHETIC_TEST_ONLY","m1_csv":str(file),
         "source":"SYNTHETIC_UNIT_TEST","timezone":"BROKER_SERVER_NAIVE",
         "start":"2026-01-02","end":"2026-01-03","data_usage":"PREVIOUSLY_USED",
         "tick_size":0.01,"commission_per_lot_usd":0,
         "slippage_model":"NONE_TEST_ONLY",
         "atr_method":"WILDER_RMA20","d1_session_start":"00:00"}
    return {"schema":"i002-multi-v0.1","research_only":True,
            "cohort_mode":"ALL_SWEEPS",
            "markets":{m:rec.copy() if m=="XAUUSD" else {} for m in MARKETS}}

class IntegrityFollowupTests(unittest.TestCase):
    def test_overlapping_mode_retains_both_sweeps(self):
        series=overlapping_bars()
        separated=scan(series)
        full=scan(series,allow_overlapping=True)
        self.assertEqual(len(separated),1)
        self.assertEqual(len(full),2)
        self.assertEqual([x["event_index"] for x in full],[10,20])
        self.assertFalse(full[0]["overlaps_previous_episode"])
        self.assertTrue(full[1]["overlaps_previous_episode"])

    def test_multistage_future_perturb_only_changes_matured_outcome(self):
        series=staged_bars()
        baseline=scan(series,allow_overlapping=True)[0]
        self.assertTrue(baseline["pivot_confirmed"])
        self.assertIsNotNone(baseline["choch_time"])
        self.assertIsNotNone(baseline["fvg_time"])
        self.assertIsNotNone(baseline["retest_time"])
        modified=list(series)
        modified[70]=replace(modified[70],c=100.3)
        modified[75]=replace(modified[75],c=100.2)
        after=scan(modified,allow_overlapping=True)[0]
        for name in ("event_time","pivot_high","pivot_confirmed","choch_time",
                     "fvg_time","retest_time"):
            self.assertEqual(baseline[name],after[name])
        self.assertNotEqual(baseline["base_return60_atr"],after["base_return60_atr"])
        self.assertNotEqual(baseline["retest_return60_atr"],after["retest_return60_atr"])
        changed_choch=list(series)
        changed_choch[12]=b(changed_choch[12].time)
        later=scan(changed_choch,allow_overlapping=True)[0]
        self.assertEqual(baseline["event_time"],later["event_time"])
        self.assertIsNone(later["choch_time"])
        changed_pre=list(series)
        changed_pre[9]=replace(changed_pre[9],c=100.1)
        pre=scan(changed_pre,allow_overlapping=True)[0]
        self.assertEqual(baseline["choch_time"],pre["choch_time"])

    def test_configured_sma_and_wilder_can_pass_strict_proxy(self):
        series=full_sessions()
        for method in ("SMA_TR20","WILDER_RMA20"):
            result=verify_temporal_integrity(series,atr_method=method,
                                             d1_session_start="00:00")
            self.assertEqual(result["status"],"PASS_CONFIGURED_PROXY",result)
            self.assertEqual(result["checked_d1_rows"],1440)
            self.assertGreater(result["checked_atr_rows"],0)

    def test_partial_prior_day_must_not_be_called_valid(self):
        result=verify_temporal_integrity(full_sessions()[60:],
                                         atr_method="WILDER_RMA20",
                                         d1_session_start="00:00")
        self.assertEqual(result["status"],"NOT_VERIFIED")
        self.assertEqual(result["checked_d1_rows"],0)

    def test_previous_d1_mutation_fails(self):
        series=full_sessions()
        series[1440]=replace(series[1440],prev_low=99.6)
        result=verify_temporal_integrity(series,atr_method="WILDER_RMA20",
                                         d1_session_start="00:00")
        self.assertEqual(result["status"],"FAIL")
        self.assertGreater(result["n_errors"],0)

    def test_atr_first_check_requires_prior_close(self):
        seq=full_sessions()[:21]
        r20=verify_temporal_integrity(seq[:20],atr_method="SMA_TR20",
                                      d1_session_start="00:00")
        r21=verify_temporal_integrity(seq,atr_method="SMA_TR20",
                                      d1_session_start="00:00")
        self.assertEqual(r20["checked_atr_rows"],0)
        self.assertEqual(r21["checked_atr_rows"],1)

    def test_gate_invokes_temporal_checker_on_synthetic_file(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"source.csv"
            p.write_text(csv_data(full_sessions()),encoding="utf-8")
            data=manifest(p)
            result=evaluate(data,Path(folder)/"manifest.json")["markets"]["XAUUSD"]
            self.assertEqual(result["status"],"INPUT_DECLARED_REVIEW_REQUIRED",result["reasons"])
            self.assertEqual(result["temporal"]["status"],"PASS_CONFIGURED_PROXY")
            self.assertFalse(result["temporal_feed_authentication"])

    def test_gate_blocks_corrupt_atr_and_unknown_session(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"source.csv"
            series=full_sessions()
            series[1500]=replace(series[1500],atr=3)
            p.write_text(csv_data(series),encoding="utf-8")
            data=manifest(p)
            result=evaluate(data,Path(folder)/"manifest.json")["markets"]["XAUUSD"]
            self.assertEqual(result["status"],"BLOCKED")
            self.assertEqual(result["temporal"]["status"],"FAIL")
            series[1500]=replace(series[1500],atr=1)
            p.write_text(csv_data(series),encoding="utf-8")
            data["markets"]["XAUUSD"]["d1_session_start"]="unknown"
            result=evaluate(data,Path(folder)/"manifest.json")["markets"]["XAUUSD"]
            self.assertEqual(result["status"],"BLOCKED")
            self.assertEqual(result["temporal"]["status"],"NOT_VERIFIED")

if __name__=="__main__":
    unittest.main()
