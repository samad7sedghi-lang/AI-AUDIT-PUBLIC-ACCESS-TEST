"""Strict, read-only quality checks for CLOSED M1 OHLC rows; not feed authentication."""
import csv
import math
from datetime import datetime, timedelta
from pathlib import Path

REQUIRED = ("timestamp","open","high","low","close","spread_price",
            "prev_d1_low","prev_d1_range","atr_m1_20")

def audit_m1(path, expected_start=None, expected_end=None):
    issues = []
    aborted = False
    abort_reason = None
    scanned_to_eof = True
    rows = 0
    gaps = 0
    last = None
    first = None
    lo = hi = None
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            return {"rows":0, "gaps":0, "issues":["missing or duplicate header"], "aborted":True, "abort_reason":"invalid_header", "scanned_to_eof":False}
        if not set(REQUIRED).issubset(reader.fieldnames):
            return {"rows":0, "gaps":0, "issues":["missing M1 required columns"], "aborted":True, "abort_reason":"missing_columns", "scanned_to_eof":False}
        for r in reader:
            rows += 1
            if rows > 2000000:
                issues.append("row limit exceeded for preflight")
                aborted = True
                abort_reason = "row_limit"
                scanned_to_eof = False
                break
            try:
                ts = datetime.fromisoformat(r["timestamp"])
                if ts.tzinfo is not None:
                    raise ValueError("offset-aware timestamp is not broker-local-naive")
                vals = [float(r[k]) for k in REQUIRED[1:]]
                if not all(math.isfinite(v) for v in vals):
                    raise ValueError("NaN or infinite values")
                o,h,l,c,spread,pdl,pdr,atr = vals
                if min(o,h,l,c,pdl,pdr,atr) <= 0 or spread < 0:
                    raise ValueError("nonpositive price/ATR/range or negative spread")
                if not (l <= min(o,c) <= max(o,c) <= h):
                    raise ValueError("invalid OHLC geometry")
                if last is not None:
                    if ts <= last:
                        raise ValueError("duplicate or reversed timestamps")
                    if ts-last > timedelta(minutes=1):
                        gaps += 1
                first = first or ts
                lo = ts if lo is None else lo
                hi = ts
                last = ts
            except (ValueError, TypeError, KeyError) as e:
                issues.append("row %d: %s" % (rows, str(e)[:100]))
                if len(issues) >= 20:
                    issues.append("too many data errors; scan stopped")
                    aborted = True
                    abort_reason = "error_limit"
                    scanned_to_eof = False
                    break
    if not rows:
        issues.append("empty M1 input")
    if first is not None:
        for label,value,actual in (("start",expected_start,first),("end",expected_end,hi)):
            if value is not None:
                try:
                    declared = datetime.fromisoformat(value)
                    if declared.tzinfo is not None or actual.date() != declared.date():
                        issues.append("%s date differs from declared date" % label)
                except (TypeError,ValueError):
                    issues.append("invalid declared %s" % label)
    # Gaps can be market closures; they require review, never synthetic filling.
    if gaps:
        issues.append("unreviewed M1 gaps: %d" % gaps)
    return {"rows":rows,"gaps":gaps,"issues":issues,
            "aborted":aborted,"abort_reason":abort_reason,"scanned_to_eof":scanned_to_eof,
            "first":None if first is None else first.isoformat(),
            "last":None if hi is None else hi.isoformat()}
