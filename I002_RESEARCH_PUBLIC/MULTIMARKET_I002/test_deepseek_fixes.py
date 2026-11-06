import tempfile
import unittest
from pathlib import Path
from policy_compare import classify, report
from data_quality import audit_m1

HEADER="timestamp,open,high,low,close,spread_price,prev_d1_low,prev_d1_range,atr_m1_20\n"
def row(i):
    return f"2026-01-02T10:{i:02d}:00,100,101,99,100,0.01,98,5,1\n"
def ev(**kw):
    return dict({"event_id":"X:one","market":"X","base_return60_atr":0.1,
        "base_return120_atr":0.2,"choch_time":"t1","fvg_time":"t2","retest_time":"t3"},**kw)
class DeepSeekFixTests(unittest.TestCase):
    def test_fvg_and_retest_reasons_separate(self):
        e=ev()
        e["fvg_time"]=None
        c=[x for x in classify([e]) if x["policy"]=="C_FVG_FIRST_RETEST"][0]
        self.assertEqual(c["reason"],"MISSING_FVG")
        self.assertEqual(c["all_reasons"],["MISSING_FVG"])
        e["retest_time"]=None
        c=[x for x in classify([e]) if x["policy"]=="C_FVG_FIRST_RETEST"][0]
        self.assertEqual(c["all_reasons"],["MISSING_FVG","MISSING_RETEST"])
        summary=report(classify([e]))
        self.assertEqual(summary["by_policy"]["C_FVG_FIRST_RETEST"]["no_trade_by_reason"],{"MISSING_FVG":1,"MISSING_RETEST":1})
    def test_missing_choch_in_c_reported(self):
        e=ev()
        e["choch_time"]=None
        c=[x for x in classify([e]) if x["policy"]=="C_FVG_FIRST_RETEST"][0]
        self.assertFalse(c["qualified"])
        self.assertEqual(c["reason"],"MISSING_CHOCH")
    def test_missing_header_marks_aborted(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"a.csv"
            p.write_text("bad\n")
            result=audit_m1(p)
            self.assertTrue(result["aborted"])
            self.assertEqual(result["abort_reason"],"missing_columns")
            self.assertFalse(result["scanned_to_eof"])
    def test_error_limit_aborts(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"a.csv"
            p.write_text(HEADER+"".join(row(i).replace(",100,101,99,",",100,101,102,") for i in range(25)))
            result=audit_m1(p)
            self.assertTrue(result["aborted"])
            self.assertEqual(result["abort_reason"],"error_limit")
            self.assertFalse(result["scanned_to_eof"])
    def test_valid_file_scanned_to_eof(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"a.csv"
            p.write_text(HEADER+row(0)+row(1))
            result=audit_m1(p)
            self.assertFalse(result["aborted"])
            self.assertIsNone(result["abort_reason"])
            self.assertTrue(result["scanned_to_eof"])
if __name__=="__main__":
    unittest.main()
