"""Explicitly opted-in G4 exploratory price-unit tick pilot. NEVER sends orders.

This cannot produce strategy USD PnL / net R or validate broker fill probability.
An event's signal time is the close of its confirming M1 candle; if CSV stamps
bar OPEN, add one minute before requesting a strictly later tick.
"""
import csv
import math
from datetime import datetime, timedelta
from pathlib import Path
from policy_compare import POLICIES
from virtual_execution import simulate_buy

TIMES={"A_SWEEP":"event_time","B_CHOCH":"choch_time",
       "C_FVG_FIRST_RETEST":"retest_time"}
REQUIRED=("stop_distance","target_distance","commission_roundtrip_price",
          "max_spread_price","latency_ms","slippage_price","bar_timestamp_semantics")

def load_ticks_csv(path):
    ticks=[]
    with Path(path).open(newline="",encoding="utf-8-sig") as f:
        reader=csv.DictReader(f)
        if not reader.fieldnames or not {"timestamp","bid","ask"}.issubset(reader.fieldnames):
            raise ValueError("Tick CSV needs timestamp,bid,ask")
        for r in reader:
            t=datetime.fromisoformat(r["timestamp"])
            if t.tzinfo is not None:
                raise ValueError("Tick clock needs naive broker-server time")
            bid=float(r["bid"])
            ask=float(r["ask"])
            if not all(math.isfinite(n) for n in (bid,ask)) or bid<=0 or ask<bid:
                raise ValueError("Bad bid/ask tick")
            if ticks and t<=ticks[-1][0]:
                raise ValueError("Unsorted ticks")
            ticks.append((t,bid,ask))
    if not ticks:
        raise ValueError("Empty tick CSV")
    return ticks

def run_virtual_policy_pilot(events, ticks, model):
    if not isinstance(model,dict) or any(x not in model for x in REQUIRED):
        raise ValueError("Complete price-unit simulation configuration required")
    semantics=model["bar_timestamp_semantics"]
    if semantics not in ("OPEN","CLOSE"):
        raise ValueError("M1 timestamp semantics OPEN or CLOSE required")
    # All numeric settings validated before any output, including no-trade sets.
    for k in ("stop_distance","target_distance","commission_roundtrip_price",
              "latency_ms","slippage_price"):
        x=model[k]
        if not isinstance(x,(int,float)) or isinstance(x,bool) or not math.isfinite(x) or x<0:
            raise ValueError("Invalid virtual pilot parameter: "+k)
    if model["stop_distance"]<=0 or model["target_distance"]<=0:
        raise ValueError("Nonpositive virtual stop/target")
    if (model["max_spread_price"] is not None and
            (not isinstance(model["max_spread_price"],(int,float)) or
             model["max_spread_price"]<0 or not math.isfinite(model["max_spread_price"]))):
        raise ValueError("Invalid spread cap")
    rows=[]
    used=set()
    for ev in events:
        identity=ev["event_id"]
        if identity in used:
            raise ValueError("Duplicate event identifier")
        used.add(identity)
        timestamps={}
        for name in ("event_time","choch_time","fvg_time","retest_time"):
            value=ev.get(name)
            timestamps[name]=None if value is None else datetime.fromisoformat(value)
            if timestamps[name] is not None and timestamps[name].tzinfo is not None:
                raise ValueError("Unaligned time zones")
        t=timestamps
        if (t["choch_time"] is not None and t["choch_time"]<=t["event_time"] or
            t["fvg_time"] is not None and
             (t["choch_time"] is None or t["fvg_time"]<=t["choch_time"]) or
            t["retest_time"] is not None and
             (t["fvg_time"] is None or t["retest_time"]<=t["fvg_time"])):
            raise ValueError("Impossible signal chronology")
        for policy in POLICIES:
            required=("event_time",) if policy=="A_SWEEP" else (
                ("event_time","choch_time") if policy=="B_CHOCH" else
                ("event_time","choch_time","fvg_time","retest_time"))
            if any(t[name] is None for name in required):
                rows.append({"event_id":identity,"policy":policy,"status":"NO_TRADE",
                             "price_delta_per_unit":None,"reason":"SIGNAL_INCOMPLETE"})
                continue
            signal=t[TIMES[policy]]+(timedelta(minutes=1) if semantics=="OPEN" else timedelta())
            fill=simulate_buy(ticks,signal,model["stop_distance"],model["target_distance"],
                              commission_roundtrip=model["commission_roundtrip_price"],
                              max_spread=model["max_spread_price"],
                              latency_ms=model["latency_ms"],
                              slippage_price=model["slippage_price"])
            rows.append({"event_id":identity,"policy":policy,"signal_time":signal.isoformat(),
                         "status":fill["status"],"reason":fill.get("reason"),
                         "price_delta_per_unit":fill.get("pnl_price"),
                         "overlapping_event":ev.get("overlaps_previous_episode",False)})
    by_policy={}
    for policy in POLICIES:
        subset=[r for r in rows if r["policy"]==policy]
        closed=[r["price_delta_per_unit"] for r in subset
                if r["status"] in ("EXIT_STOP","EXIT_TARGET")
                and r["price_delta_per_unit"] is not None]
        counts={}
        for r in subset:
            counts[r["status"]]=counts.get(r["status"],0)+1
        by_policy[policy]={"base_events":len(events),
            "status_counts":dict(sorted(counts.items())),
            "n_closed_hypothetical_exits":len(closed),
            "mean_price_delta_per_unit_on_closed_exits":round(sum(closed)/len(closed),10) if closed else None,
            "economic_policy_comparison_valid":False}
    return {"status":"EXPLORATORY_PRICE_UNITS_ONLY" if events else "EXPLORATORY_NO_EVENTS","rows":rows,
            "by_policy":by_policy,
            "base_events":len(events),"policy_rows":len(rows),
            "order_path":False,"net_usd_pnl_computed":False,
            "portfolio_execution_simulated":False,"broker_fill_certified":False,
            "matched_null_done":False,"tick_feed_authenticated":False,
            "warning":"Hypothetical one-unit trades assessed independently; overlaps, market impact, lot sizing, USD currency conversion and real fills NOT modelled."}
