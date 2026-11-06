"""Conservative market-data preflight: NEVER trades or asserts alpha."""
import argparse
import csv
import json
import math
from pathlib import Path
from data_quality import audit_m1
from i002_event_lab_snapshot import load_bars
from temporal_integrity import verify_temporal_integrity, METHODS

MARKETS = ("XAUUSD", "EURUSD", "SP500", "NAS100", "GBPUSD", "USDJPY", "EURGBP")
COLUMNS = {"timestamp", "open", "high", "low", "close", "spread_price",
           "prev_d1_low", "prev_d1_range", "atr_m1_20"}
MANDATORY = ("broker_symbol", "m1_csv", "source", "timezone", "start", "end",
             "data_usage", "tick_size", "commission_per_lot_usd", "slippage_model",
             "atr_method", "d1_session_start")

def evaluate(data, manifest_path):
    if data.get("schema") != "i002-multi-v0.1" or data.get("research_only") is not True:
        raise ValueError("Schema and research-only guard required")
    markets = data.get("markets")
    if not isinstance(markets, dict) or set(markets) != set(MARKETS):
        raise ValueError("Exactly seven declared markets required; none may be silently dropped")
    report = {}
    for market in MARKETS:
        record = markets[market]
        if not isinstance(record, dict):
            report[market] = {"status": "BLOCKED", "reasons": ["invalid record"]}
            continue
        missing = [k for k in MANDATORY if record.get(k) is None or record.get(k) == ""]
        reasons = ["missing:" + k for k in missing]
        if record.get("data_usage") not in ("UNTOUCHED_VERIFIED", "PREVIOUSLY_USED", "UNREVIEWED"):
            reasons.append("invalid data_usage declaration")
        if record.get("data_usage") == "UNREVIEWED":
            reasons.append("unreviewed data-consumption ledger")
        for n in ("tick_size", "commission_per_lot_usd"):
            if record.get(n) is not None:
                try:
                    v = float(record[n])
                    if not math.isfinite(v) or (v <= 0 if n == "tick_size" else v < 0):
                        reasons.append("invalid:" + n)
                except (ValueError, TypeError):
                    reasons.append("invalid:" + n)
        if record.get("atr_method") not in METHODS:
            reasons.append("unsupported:atr_method")
        if not isinstance(record.get("d1_session_start"), str):
            reasons.append("missing:d1_session_start")
        file_name = record.get("m1_csv")
        rows = None
        quality = None
        temporal = None
        if file_name:
            p = Path(file_name)
            if not p.is_absolute():
                p = manifest_path.parent / p
            if not p.is_file():
                reasons.append("missing M1 file")
            else:
                try:
                    quality = audit_m1(p, record.get("start"), record.get("end"))
                    rows = quality["rows"]
                    reasons.extend(quality["issues"])
                    if quality.get("aborted") or not quality.get("scanned_to_eof", False):
                        reasons.append("incomplete M1 audit: " + str(quality.get("abort_reason")))
                    if (not quality["issues"] and not quality.get("aborted")
                            and quality.get("scanned_to_eof") is True
                            and record.get("atr_method") in METHODS):
                        temporal = verify_temporal_integrity(
                            load_bars(p), atr_method=record["atr_method"],
                            d1_session_start=record.get("d1_session_start"))
                        if temporal["status"] != "PASS_CONFIGURED_PROXY":
                            reasons.append("temporal integrity: " + temporal["status"])
                    elif quality["issues"]:
                        reasons.append("temporal integrity: NOT_VERIFIED_BAD_M1")

                except (OSError, UnicodeError, csv.Error, ValueError, TypeError) as e:
                    reasons.append("unreadable M1: " + type(e).__name__)
        report[market] = {"status": "BLOCKED" if reasons else "INPUT_DECLARED_REVIEW_REQUIRED",
                          "reasons": reasons, "rows": rows, "quality": quality,
                          "temporal": temporal, "temporal_feed_authentication":False,
                          "trading_approved": False, "oos_certified": False}
    return {"research_only": True, "order_path": False, "edge_proven": False,
            "markets": report}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    src = Path(args.manifest).resolve()
    result = evaluate(json.loads(src.read_text(encoding="utf-8")), src)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v["status"] for k, v in result["markets"].items()}))

if __name__ == "__main__":
    main()
