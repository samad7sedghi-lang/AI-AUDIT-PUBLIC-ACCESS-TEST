"""Research-only virtual BUY execution from ordered, observed bid/ask TICKS.
Not a trading interface, not a broker-certified fill model.
"""
import math
from datetime import datetime, timedelta

def simulate_buy(ticks, signal_time, stop_distance, target_distance,
                 commission_roundtrip=0.0, max_spread=None,
                 latency_ms=0, slippage_price=0.0):
    """Entry is first tick strictly AFTER signal; bid exits. One unit only.
    Missing signal/quotes, spread cap and no later tick are explicitly NO_FILL.
    Commission expressed in absolute price units per 1 unit, not USD per lot.
    """
    if not all(math.isfinite(float(x)) and float(x)>=0 for x in
               (stop_distance,target_distance,commission_roundtrip,slippage_price)):
        raise ValueError("Invalid costs / stop / target")
    if max_spread is not None and (not math.isfinite(float(max_spread)) or max_spread<0):
        raise ValueError("Invalid spread cap")
    if isinstance(latency_ms, bool) or not isinstance(latency_ms,(int,float)) or not math.isfinite(latency_ms) or latency_ms<0:
        raise ValueError("Invalid latency")
    if isinstance(signal_time,datetime):
        earliest=signal_time+timedelta(milliseconds=latency_ms)
    elif isinstance(signal_time,(int,float)) and math.isfinite(signal_time):
        earliest=signal_time+latency_ms/1000.0
    else:
        raise ValueError("Invalid signal time")
    if stop_distance<=0 or target_distance<=0:
        raise ValueError("Stop/target must be positive")
    prev=None
    for tick in ticks:
        t,bid,ask=tick
        if prev is not None and t<=prev:
            raise ValueError("Non-monotonic tick times")
        if not all(math.isfinite(float(x)) for x in (bid,ask)) or bid<=0 or ask<bid:
            raise ValueError("Invalid tick bid/ask")
        prev=t
    entry=None
    index=None
    for i,(t,bid,ask) in enumerate(ticks):
        if t<=earliest: continue
        if max_spread is not None and ask-bid>max_spread:
            return {"status":"NO_FILL","reason":"SPREAD_CAP","pnl_price":None}
        entry=ask+slippage_price
        index=i
        break
    if entry is None:
        return {"status":"NO_FILL","reason":"NO_LATER_TICK","pnl_price":None}
    stop=entry-stop_distance
    target=entry+target_distance
    for t,bid,ask in ticks[index+1:]:
        if bid-slippage_price<=stop:
            return {"status":"EXIT_STOP","entry_ask":entry,"exit_bid":bid-slippage_price,
                    "exit_time":str(t),"pnl_price":round(bid-slippage_price-entry-commission_roundtrip,10)}
        if bid-slippage_price>=target:
            return {"status":"EXIT_TARGET","entry_ask":entry,"exit_bid":bid-slippage_price,
                    "exit_time":str(t),"pnl_price":round(bid-slippage_price-entry-commission_roundtrip,10)}
    return {"status":"OPEN_UNRESOLVED","entry_ask":entry,"pnl_price":None,
            "reason":"NO_EXIT_TICK"}
