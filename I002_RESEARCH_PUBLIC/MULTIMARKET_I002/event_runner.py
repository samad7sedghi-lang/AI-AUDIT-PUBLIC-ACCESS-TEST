"""Read-only seven-market descriptive event scan. No PnL, orders or GO."""
import argparse
import json
import csv
from pathlib import Path
from manifest_gate import evaluate, MARKETS
from i002_event_lab_snapshot import load_bars, scan
from policy_compare import classify, report
from virtual_policy_pilot import load_ticks_csv, run_virtual_policy_pilot

def execute(manifest, manifest_path):
    mode = manifest.get("cohort_mode", "SEPARATED")
    if mode not in ("ALL_SWEEPS", "SEPARATED"):
        raise ValueError("Unknown cohort mode")
    pilot_config = manifest.get("virtual_pilot")
    if pilot_config is not None and not isinstance(pilot_config,dict):
        raise ValueError("Invalid optional virtual pilot configuration")
    gate = evaluate(manifest, manifest_path)
    results = {}
    for market in MARKETS:
        status = gate["markets"][market]
        if status["status"] == "BLOCKED":
            results[market] = {"status":"BLOCKED","reasons":status["reasons"],"events":[],"count":0}
            continue
        record = manifest["markets"][market]
        p = Path(record["m1_csv"])
        if not p.is_absolute():
            p = manifest_path.parent / p
        try:
            events = scan(load_bars(p), allow_overlapping=(mode == "ALL_SWEEPS"))
            for i, event in enumerate(events):
                event["event_id"] = "%s:%s" % (market,event["event_time"])
                event["market"] = market
            if len({event["event_id"] for event in events}) != len(events):
                raise ValueError("Duplicate stable event identity")
            results[market] = {"status":"DESCRIPTIVE_ONLY_REVIEW_REQUIRED",
                               "events":events, "count":len(events),
                               "cohort_mode":mode,
            "virtual_pilot_is_optional":True,
                               "overlap_events":sum(e["overlaps_previous_episode"] for e in events),
                               "statistical_independence_proven":False,
                               "policy_rows":classify(events),
                               "policy_report":report(classify(events))}
            # Optional G4 research-only tick pilot is strictly separate from
            # descriptive scanner. A bad/missing tick feed cannot fabricate PnL.
            if pilot_config is not None and pilot_config.get("enabled") is True:
                try:
                    tick_ref=record.get("tick_csv")
                    if not tick_ref:
                        raise ValueError("No tick CSV for optional pilot")
                    tick_path=Path(tick_ref)
                    if not tick_path.is_absolute():
                        tick_path=manifest_path.parent/tick_path
                    results[market]["virtual_pilot"]=run_virtual_policy_pilot(
                        events,load_ticks_csv(tick_path),pilot_config.get("model"))
                except (ValueError,OSError,KeyError,TypeError,csv.Error,UnicodeError) as ex:
                    results[market]["virtual_pilot"]={
                        "status":"BLOCKED","reason":"tick_pilot:"+type(ex).__name__,
                        "net_usd_pnl_computed":False}

        except (ValueError, OSError, KeyError, IndexError, TypeError, csv.Error) as e:
            results[market]={"status":"BLOCKED","reasons":["scanner: "+type(e).__name__],
                             "events":[],"count":0}
    return {"research_only":True,"order_path":False,"pnl_computed":False,
            "matched_null_done":False,"oos_certified":False,
            "cohort_mode":mode,"pr12_independent_review_done":False,
            "markets":results}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--manifest",required=True)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    source=Path(args.manifest).resolve()
    result=execute(json.loads(source.read_text(encoding="utf-8")),source)
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({m:{"status":v["status"],"events":len(v["events"])}
                      for m,v in result["markets"].items()},ensure_ascii=False))
if __name__=="__main__":
    main()
