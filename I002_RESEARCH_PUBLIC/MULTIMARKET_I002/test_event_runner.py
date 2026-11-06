import unittest
from pathlib import Path
from event_runner import execute
from manifest_gate import MARKETS

class RunnerTests(unittest.TestCase):
    def test_seven_markets_preserved_when_missing(self):
        manifest={"schema":"i002-multi-v0.1","research_only":True,
                  "markets":{m:{} for m in MARKETS}}
        out=execute(manifest,Path("manifest.json"))
        self.assertEqual(set(out["markets"]),set(MARKETS))
        self.assertTrue(all(out["markets"][m]["status"]=="BLOCKED" for m in MARKETS))
        self.assertFalse(out["order_path"])
        self.assertFalse(out["pnl_computed"])
        self.assertFalse(out["oos_certified"])
        self.assertFalse(out["pr12_independent_review_done"])

if __name__=="__main__":
    unittest.main()
