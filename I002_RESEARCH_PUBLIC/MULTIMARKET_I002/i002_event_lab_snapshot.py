"""Read-only, synthetic-capable I002 event-discovery prototype.

This deliberately DOES NOT send orders, choose a profit-maximising threshold,
compute a matched-null alpha, simulate fills, or make deployment decisions.
Input M1 values must be from closed broker bars with trusted previous-completed-D1
fields and M1 ATR available BEFORE each timestamp; this tool doesn't authenticate
feed provenance. Numeric windows are new preregistration PROPOSALS, not historical
S2 parameters and must be fixed before independent data use.
"""
import argparse
import csv
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

FIELDS = ('timestamp', 'open', 'high', 'low', 'close', 'spread_price',
          'prev_d1_low', 'prev_d1_range', 'atr_m1_20')
CHOCH_LIMIT = 30
FVG_LIMIT = 20
RETEST_LIMIT = 30
# Conservative, predeclared non-overlap: latest possible retest is 30+20+30
# minutes after sweep, then its 120-minute descriptive outcome matures.
# Not an optimized strategy threshold; this reduces N to protect inference.
EPISODE_SEPARATION_MINUTES = CHOCH_LIMIT + FVG_LIMIT + RETEST_LIMIT + 120


@dataclass(frozen=True)
class Bar:
    time: datetime
    o: float
    h: float
    l: float
    c: float
    spread: float
    prev_low: float
    prev_range: float
    atr: float


def load_bars(path):
    result = []
    with open(path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or not set(FIELDS).issubset(reader.fieldnames):
            raise ValueError('Missing required M1 fields; no silent substitutions')
        for row in reader:
            t = datetime.fromisoformat(row['timestamp'])
            if t.tzinfo is not None:
                raise ValueError('Use broker-server-local naive timestamps consistently')
            v = [float(row[k]) for k in FIELDS[1:]]
            import math
            if any(not math.isfinite(x) for x in v):
                raise ValueError('Nonfinite OHLC/ATR/spread')
            o,h,l,c,spread,pdl,pdr,atr=v
            if min(o,h,l,c,pdl) <= 0 or not l <= min(o,c) <= max(o,c) <= h:
                raise ValueError('Invalid prices / OHLC geometry')
            if spread<0 or pdr<=0 or atr<=0:
                raise ValueError('Invalid spread, previous-day range or ATR')
            if result and t<=result[-1].time:
                raise ValueError('M1 timestamps not strictly increasing')
            result.append(Bar(t,o,h,l,c,spread,pdl,pdr,atr))
    return result


def confirmed_pivot_high(bars, at):
    """2-left/2-right pivot. Right-side bars must be closed by event time."""
    for p in range(at-2,1,-1):
        h=bars[p].h
        # Do not combine sessions or missing M1 bars into a nominal 2-2 pivot.
        # The pivot and subsequent sweep must share a contiguous closed-bar history.
        if continuous(bars,p-2,at) and all(h>bars[q].h for q in (p-2,p-1,p+1,p+2)):
            return h
    return None


def continuous(bars, a, b):
    return (b>=a and bars[b].time-bars[a].time==timedelta(minutes=b-a)
            and all(bars[i].time-bars[i-1].time==timedelta(minutes=1)
                    for i in range(a+1,b+1)))


def forward_atr(bars, at, horizon):
    end=at+horizon
    if end>=len(bars) or not continuous(bars,at,end):
        return None
    return round((bars[end].c-bars[at].c)/bars[at].atr,8)


def scan(bars, allow_overlapping=False):
    """Research events from closed M1 bars; no trades.

    Default: >=200-minute event separation to limit overlapping outcomes.
    allow_overlapping=True: enumerate ALL eligible raw sweeps, including
    neighbouring events. Mark overlap; never assume statistical independence.
    This switch is observational, not a data-driven model optimization.
    """
    out=[]
    last_event_time=None
    for i in range(4,len(bars)):
        b=bars[i]
        # Evaluate predicate BEFORE applying optional event-sampling policy.
        # In full-cohort mode, event separation never suppresses a sweep.
        overlap_with_prior=(last_event_time is not None and
                (b.time-last_event_time).total_seconds() <=
                60 * EPISODE_SEPARATION_MINUTES)
        if overlap_with_prior and not allow_overlapping:
            continue
        threshold=max(b.spread,0.02*b.prev_range)
        if not(b.l<=b.prev_low-threshold and b.c>b.prev_low):
            continue
        pivot=confirmed_pivot_high(bars,i)
        # Every sweep belongs to base cohort A, even without an eligible pivot.
        # A missing pivot disables CHoCH/FVG/retest, not the sweep event itself.
        last_event_time=b.time
        choch=None
        if pivot is not None:
            for j in range(i+1,min(len(bars),i+CHOCH_LIMIT+1)):
                if not continuous(bars,i,j):
                    break
                if bars[j].c>pivot and bars[j].c>bars[j].o and bars[j].c-bars[j].o>=bars[j].atr:
                    choch=j
                    break
        fvg=None
        if choch is not None:
            for k in range(choch+1,min(len(bars),choch+FVG_LIMIT+1)):
                if not continuous(bars,choch,k):
                    break
                if k>=2 and bars[k].l>bars[k-2].h:
                    fvg=k
                    break
        retest=None
        if fvg is not None:
            for z in range(fvg+1,min(len(bars),fvg+RETEST_LIMIT+1)):
                if not continuous(bars,fvg,z):
                    break
                if bars[z].l<=bars[fvg].l and bars[z].h>=bars[fvg-2].h:
                    retest=z
                    break
        out.append(dict(
            event_time=b.time.isoformat(sep=' '),event_index=i,threshold_price=round(threshold,8),
            pivot_high=None if pivot is None else round(pivot,8),
            pivot_confirmed=pivot is not None,
            overlaps_previous_episode=bool(overlap_with_prior),
            choch_time=None if choch is None else bars[choch].time.isoformat(sep=' '),
            fvg_time=None if fvg is None else bars[fvg].time.isoformat(sep=' '),
            retest_time=None if retest is None else bars[retest].time.isoformat(sep=' '),
            base_return60_atr=forward_atr(bars,i,60),
            base_return120_atr=forward_atr(bars,i,120),
            retest_return60_atr=None if retest is None else forward_atr(bars,retest,60),
            retest_return120_atr=None if retest is None else forward_atr(bars,retest,120)
        ))
    return out


def main():
    ap=argparse.ArgumentParser(description='Research-only I002 event classification (no order path)')
    ap.add_argument('--m1-csv',required=True)
    ap.add_argument('--allow-overlapping',action='store_true',help='Full raw sweep cohort; overlapping labels are NOT independent')
    ap.add_argument('--output-json',required=True)
    args=ap.parse_args()
    result=scan(load_bars(args.m1_csv),allow_overlapping=args.allow_overlapping)
    dest=Path(args.output_json)
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps({'research_only':True,'matched_null_done':False,
        'trade_execution_tested':False,'allow_overlapping':args.allow_overlapping,'events':result},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'events':len(result),'with_choch':sum(x['choch_time'] is not None for x in result),
        'with_fvg':sum(x['fvg_time'] is not None for x in result),
        'with_retest':sum(x['retest_time'] is not None for x in result),
        'qualified_for_trading':False}))

if __name__=='__main__':main()
