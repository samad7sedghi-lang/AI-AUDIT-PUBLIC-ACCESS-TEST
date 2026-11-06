import tempfile
import unittest
from pathlib import Path
from data_quality import audit_m1

HEADER = "timestamp,open,high,low,close,spread_price,prev_d1_low,prev_d1_range,atr_m1_20\n"
def row(t, low="99"):
    return f"{t},100,101,{low},100,0.01,98,5,1\n"

class QualityTests(unittest.TestCase):
    def check(self, data):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/"m1.csv"
            p.write_text(HEADER + data, encoding="utf-8")
            return audit_m1(p)
    def test_valid_closed_bars(self):
        r = self.check(row("2026-01-02T10:00:00")+row("2026-01-02T10:01:00"))
        self.assertEqual(r["issues"], [])
        self.assertEqual(r["rows"], 2)
    def test_gap_blocks(self):
        r = self.check(row("2026-01-02T10:00:00")+row("2026-01-02T10:03:00"))
        self.assertEqual(r["gaps"],1)
        self.assertTrue(any("gap" in s for s in r["issues"]))
    def test_duplicate_blocks(self):
        r = self.check(row("2026-01-02T10:00:00")*2)
        self.assertTrue(any("duplicate" in s for s in r["issues"]))
    def test_bad_ohlc_blocks(self):
        r = self.check(row("2026-01-02T10:00:00",low="102"))
        self.assertTrue(any("geometry" in s for s in r["issues"]))
    def test_nonfinite_blocks(self):
        r = self.check(row("2026-01-02T10:00:00").replace(",0.01,",",nan,"))
        self.assertTrue(any("infinite" in s for s in r["issues"]))
    def test_declared_date_mismatch_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"a.csv"
            p.write_text(HEADER+row("2026-01-02T10:00:00"))
            r=audit_m1(p,expected_start="2026-01-03")
            self.assertTrue(any("start date" in s for s in r["issues"]))

if __name__ == "__main__":
    unittest.main()
