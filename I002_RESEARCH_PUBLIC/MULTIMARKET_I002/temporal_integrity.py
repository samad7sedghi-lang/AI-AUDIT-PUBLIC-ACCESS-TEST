"""Read-only checks for CLOSED M1 ATR and previous-completed broker-session D1.

Never proves broker feed provenance, OOS, market PnL, or absence of all lookahead.
Fail closed on unknown ATR convention or unverified partial sessions.
"""
import math
import re
from collections import OrderedDict
from datetime import datetime, timedelta, time

METHODS=("SMA_TR20","WILDER_RMA20")

def verify_temporal_integrity(bars, atr_method="UNKNOWN",
                              d1_session_start=None, tolerance=1e-5):
    """Recompute using <= current closed bar; previous daily session only.

    d1_session_start is HH:MM in broker-server clock, not UTC or ET.
    Require a complete previous 1440-minute session before comparing D1,
    so partial prior days/weekend closures cause NOT_VERIFIED, not false PASS.
    ATR at index 20 is the first checkable 20-TR seed (needs prior close).
    Wilder RMA is seeded with first 20 contiguous true ranges.
    """
    if atr_method not in METHODS:
        return {"status":"NOT_VERIFIED","reason":"ATR_CONVENTION_UNSUPPORTED",
                "checked_atr_rows":0,"checked_d1_rows":0,"errors":[],"n_errors":0}
    if (not isinstance(d1_session_start,str) or
        not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]",d1_session_start)):
        return {"status":"NOT_VERIFIED","reason":"D1_SESSION_START_UNSPECIFIED",
                "checked_atr_rows":0,"checked_d1_rows":0,"errors":[],"n_errors":0}
    if not isinstance(tolerance,(int,float)) or not math.isfinite(tolerance) or tolerance<=0:
        raise ValueError("Invalid tolerance")
    h,m=map(int,d1_session_start.split(":"))
    shift=timedelta(hours=h,minutes=m)
    sessions=OrderedDict()
    errors=[]
    checked_atr=0
    checked_d1=0
    history=[]
    rma=None
    previous=None
    for i,b in enumerate(bars):
        if b.time.tzinfo is not None:
            raise ValueError("Only naive broker-server M1 times supported")
        if previous is not None and b.time<=previous.time:
            raise ValueError("Unsorted or duplicate M1 timestamps")
        session=(b.time-shift).date()
        sessions.setdefault(session,[]).append(b)
        if previous is None or b.time-previous.time!=timedelta(minutes=1):
            history=[]
            rma=None
        else:
            tr=max(b.h-b.l,abs(b.h-previous.c),abs(b.l-previous.c))
            history.append(tr)
            if len(history)>20:
                history=history[-20:]
            if len(history)==20:
                if rma is None:
                    rma=sum(history)/20
                elif atr_method=="WILDER_RMA20":
                    rma=(19*rma+tr)/20
                else:
                    rma=sum(history)/20
                expected=rma
                checked_atr+=1
                if not math.isclose(b.atr,expected,rel_tol=1e-5,abs_tol=tolerance):
                    errors.append({"index":i,"reason":atr_method+"_MISMATCH"})
        previous=b
    keys=list(sessions)
    unverified_sessions=0
    for pos,day in enumerate(keys):
        current=sessions[day]
        # Previous-day fields must be constant throughout each session.
        ref=current[0]
        for b in current[1:]:
            if abs(b.prev_low-ref.prev_low)>tolerance or abs(b.prev_range-ref.prev_range)>tolerance:
                errors.append({"session":str(day),"reason":"PREVIOUS_D1_FIELDS_CHANGE_WITHIN_SESSION"})
                break
        if pos==0:
            unverified_sessions+=1
            continue
        preceding_day=keys[pos-1]
        prev_bars=sessions[preceding_day]
        expected_start=datetime.combine(preceding_day,time(0,0))+shift
        prev_complete=(len(prev_bars)==1440 and prev_bars[0].time==expected_start
                       and prev_bars[-1].time==expected_start+timedelta(minutes=1439)
                       and all(prev_bars[i].time-prev_bars[i-1].time==timedelta(minutes=1)
                               for i in range(1,len(prev_bars))))
        if not prev_complete:
            unverified_sessions+=1
            continue
        previous_low=min(b.l for b in prev_bars)
        previous_range=max(b.h for b in prev_bars)-previous_low
        for b in current:
            checked_d1+=1
            if abs(b.prev_low-previous_low)>tolerance or abs(b.prev_range-previous_range)>tolerance:
                errors.append({"session":str(day),"reason":"PREVIOUS_COMPLETED_D1_MISMATCH"})
                break
    status=("FAIL" if errors else
            "PASS_CONFIGURED_PROXY" if checked_atr>0 and checked_d1>0
            and unverified_sessions<=1 else "NOT_VERIFIED")
    return {
        "status":status,"atr_method":atr_method,"d1_session_start":d1_session_start,
        "checked_atr_rows":checked_atr,"checked_d1_rows":checked_d1,
        "unverified_d1_sessions":unverified_sessions,"calendar_sessions":len(keys),
        "errors":errors[:30],"n_errors":len(errors),
        "warning":"Configured session and ATR are proxies only. Wilder seed and broker warmup may differ; after M1 gaps ATR history resets and some rows are unchecked. Full broker provenance remains unverified."
    }
