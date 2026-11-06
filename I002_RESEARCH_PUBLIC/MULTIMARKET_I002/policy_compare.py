"""Diagnostic, non-trading A/B/C comparison on the SAME base event cohort.
Do not interpret descriptive forward returns as executable PnL.
"""
from collections import Counter
import math

POLICIES=("A_SWEEP","B_CHOCH","C_FVG_FIRST_RETEST")
def classify(events):
    """One immutable row per original sweep, per policy; no event deletion."""
    rows=[]
    for ev in events:
        event_id=ev["event_id"]
        base=ev.get("base_return60_atr")
        if base is not None and (not isinstance(base, (int,float)) or not math.isfinite(base)):
            raise ValueError("Invalid base event horizon")
        for policy in POLICIES:
            missing = []
            if policy in ("B_CHOCH", "C_FVG_FIRST_RETEST") and ev.get("choch_time") is None:
                missing.append("MISSING_CHOCH")
            if policy == "C_FVG_FIRST_RETEST":
                if ev.get("fvg_time") is None:
                    missing.append("MISSING_FVG")
                if ev.get("retest_time") is None:
                    missing.append("MISSING_RETEST")
            eligible = not missing
            rows.append({
                "event_id":event_id,"market":ev["market"],"policy":policy,
                "qualified":bool(eligible),
                "status":"DESCRIPTIVE_EVENT_ONLY" if eligible else "NO_TRADE",
                "reason":missing[0] if missing else None,
                "all_reasons":missing,
                "event_return60_atr":base,
                "event_return120_atr":ev.get("base_return120_atr"),
                "retest_return60_atr":ev.get("retest_return60_atr") if policy=="C_FVG_FIRST_RETEST" and eligible else None,
                "entry_time":None,"fill_status":"NOT_SIMULATED",
                "net_pnl_r":None,
                "base_horizon_available":base is not None
            })
    return rows

def report(rows):
    """Descriptive cohort audit, NOT an A/B/C economic return comparison."""
    result={}
    events={r["event_id"] for r in rows}
    if any(r.get("policy") not in POLICIES for r in rows):
        raise ValueError("Unknown policy")
    for p in POLICIES:
        subset=[r for r in rows if r["policy"]==p]
        if len(subset)!=len(events) or {r["event_id"] for r in subset}!=events:
            raise ValueError("Cohort mismatch / duplicate events")
    by_policy={p:{r["event_id"]:r for r in rows if r["policy"]==p} for p in POLICIES}
    intersection={eid for eid in events if all(by_policy[p][eid]["qualified"] for p in POLICIES)}
    common_known={eid for eid in intersection if all(by_policy[p][eid]["event_return60_atr"] is not None for p in POLICIES)}
    for p in POLICIES:
        subset=list(by_policy[p].values())
        n=sum(r["qualified"] for r in subset)
        known=[r["event_return60_atr"] for r in subset if r["event_return60_atr"] is not None]
        paired=[by_policy[p][eid]["event_return60_atr"] for eid in sorted(common_known)]
        reason_counts=Counter(reason for r in subset for reason in r.get("all_reasons",[]))
        missing_horizon=sum(r["event_return60_atr"] is None for r in subset)
        result[p]={
            "base_events":len(events),"qualified_events":n,"no_trade":len(events)-n,
            "n_no_trade_events":len(events)-n,
            "no_trade_by_reason":dict(sorted(reason_counts.items())),
            "n_reason_mentions":sum(reason_counts.values()),
            "n_missing_base_horizon":missing_horizon,
            "available_event_horizons":len(known),
            "mean_on_base_cohort_atr":round(sum(known)/len(known),8) if known else None,
            "mean_on_intersection_qualified_atr":round(sum(paired)/len(paired),8) if paired else None,
            "filled_orders":None,"net_pnl_r":None
        }
    return {"status":"DESCRIPTIVE_ONLY_NOT_STRATEGY_COMPARISON",
            "paired_base_events":len(events),
            "intersection_qualified_events":len(intersection),
            "intersection_with_known_horizon":len(common_known),
            "by_policy":result,"pnl_computed":False,"no_trade_preserved":True,
            "warning":"Identical base-event return in A/B/C is NOT policy-specific performance; no trade fills simulated."}
