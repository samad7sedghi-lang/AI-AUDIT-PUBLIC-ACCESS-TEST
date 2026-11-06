import unittest
from dataclasses import replace
from datetime import datetime,timedelta
from i002_event_lab_snapshot import Bar,scan
from temporal_integrity import verify_temporal_integrity

def bars():
    origin=datetime(2026,1,2,10)
    arr=[]
    for i in range(180):
        # Increasing highs prevent confirmed 2+2 pivot before sweep.
        o=100+i*0.01
        low=o-0.3
        close=o
        if i==10:
            low=95
            close=99
        arr.append(Bar(origin+timedelta(minutes=i),o,o+0.5,low,close,0.01,98,5,1))
    return arr

class IntegrityTests(unittest.TestCase):
    def test_unpivoted_sweep_retained_in_A(self):
        e=scan(bars())
        self.assertEqual(len(e),1)
        self.assertEqual(e[0]["event_index"],10)
        self.assertFalse(e[0]["pivot_confirmed"])
        self.assertIsNone(e[0]["choch_time"])
    def test_future_perturb_does_not_change_sweep_or_signal_at_t(self):
        a=bars()
        modified=list(a)
        # Modify only bars > event time. Ex post outcome may change, not event predicate.
        for i in range(11,180):
            modified[i]=replace(modified[i],c=modified[i].c+0.001)
        x=scan(a)[0]
        y=scan(modified)[0]
        for key in ("event_time","event_index","threshold_price","pivot_confirmed","pivot_high"):
            self.assertEqual(x[key],y[key])
    def test_unknown_atr_method_fails_unverified(self):
        r=verify_temporal_integrity(bars(),atr_method="UNSUPPORTED")
        self.assertEqual(r["status"],"NOT_VERIFIED")
    def test_wrong_atr_flags_failure(self):
        r=verify_temporal_integrity(bars(),atr_method="SMA_TR20",d1_session_start="00:00")
        self.assertEqual(r["status"],"FAIL")
        self.assertTrue(any(e["reason"]=="SMA_TR20_MISMATCH" for e in r["errors"]))
if __name__=="__main__":
    unittest.main()
