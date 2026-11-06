import json
import tempfile
import unittest
from pathlib import Path
from manifest_gate import MARKETS, evaluate

class GateTests(unittest.TestCase):
    def setUp(self):
        self.template = {"schema": "i002-multi-v0.1", "research_only": True,
                         "markets": {k: {} for k in MARKETS}}
    def test_missing_is_blocked_for_all_seven(self):
        with tempfile.TemporaryDirectory() as d:
            result = evaluate(self.template, Path(d) / "manifest.json")
            self.assertEqual(len(result["markets"]), 7)
            self.assertTrue(all(v["status"] == "BLOCKED" for v in result["markets"].values()))
            self.assertFalse(result["edge_proven"])
            self.assertFalse(result["order_path"])
    def test_no_silent_market_omission(self):
        self.template["markets"].pop("EURGBP")
        with self.assertRaises(ValueError):
            evaluate(self.template, Path("manifest.json"))
    def test_research_guard(self):
        self.template["research_only"] = False
        with self.assertRaises(ValueError):
            evaluate(self.template, Path("manifest.json"))

if __name__ == "__main__":
    unittest.main()
