#!/usr/bin/env python3
"""Analiza logu CSV z obserwatora stanu (FB_CsvLogger / ACT_LogRow).

Uzycie:
    python analyze_log.py tp_20260911_101500.csv            # przeglad
    python analyze_log.py plik.csv --around 123456 --win 5000   # wiersze +-5 s wokol t_ms
    python analyze_log.py plik.csv --cols nDeStep de_pos de_inPos  # wybrane kolumny, tylko zmiany

Nie wymaga pandas - czysty Python 3.
"""
import csv, sys, argparse
from collections import Counter, OrderedDict

STEP_COLS = ["nDeStep", "nStStep", "nFeedStep", "nOutStep", "nOut2Step", "nOut3Step"]
SENSOR_COLS = ["in1","in2","in3","in4","in5","in6","in7","in8","in9","in10"]
PAL_COLS = ["xPal_St03","xPal_St04In","xPal_St04End","xPal_St07","xPal_St13","xPal_St08","xPal_St11","xPal_St16"]
BIT_COLS = ["START_TEST","START_FEED","START_DESTACK","START_STACK","RESET_CYCLE","RESET_CAM","xCmdResetDrives",
            "xSt01_StackReady","xDe_PalletReleased","xSt05_Done","xSt08_PalletNOK","xOutStart","xOut2Start","xOut3Start",
            "de_jawsClosed","st_jawsClosed","de_inPos","de_stall","de_noDrvAck","de_brakeRel","xSTO","xAir"]

def load(path):
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    for r in rows:
        r["_t"] = int(r.get("t_ms") or 0)
    return rows

def fmt_t(ms):
    return f"{ms/1000:9.2f}s"

def transitions(rows, col):
    out, prev = [], None
    for r in rows:
        v = r.get(col)
        if v != prev:
            out.append((r["_t"], prev, v, r))
            prev = v
    return out

def overview(rows, path):
    if not rows:
        print("pusty plik"); return
    t0, t1 = rows[0]["_t"], rows[-1]["_t"]
    print(f"== {path}")
    print(f"   wierszy: {len(rows)}   czas: {fmt_t(t0)} .. {fmt_t(t1)}  ({(t1-t0)/1000:.1f} s)   kolumn: {len(rows[0])-1}")
    print(f"   zegar: {rows[0].get('clock')} .. {rows[-1].get('clock')}")
    why = Counter()
    for r in rows:
        for w in (r.get("why") or "").split():
            why[w] += 1
    print("   powody wierszy:", dict(why))
    last = rows[-1]
    print(f"   logger: dropped={last.get('log_dropped')} errors={last.get('log_errors')} lastErr={last.get('log_lastErr')}")

    # kroki
    for col in STEP_COLS:
        tr = transitions(rows, col)
        if len(tr) <= 1:
            continue
        print(f"\n-- {col}: {len(tr)-1} zmian")
        for i, (t, a, b, r) in enumerate(tr):
            t_end = tr[i+1][0] if i+1 < len(tr) else rows[-1]["_t"]
            phase = ""
            if col == "nDeStep": phase = r.get("sDePhase", "")
            if col == "nFeedStep": phase = r.get("sFeedPhase", "")
            if col == "nOutStep": phase = r.get("sOutPhase", "")
            print(f"   {fmt_t(t)}  {str(a):>4} -> {str(b):<4}  trwa {(t_end-t)/1000:7.2f} s   {phase[:60]}")

    # czujniki
    print("\n-- zbocza czujnikow (surowe INPUTS):")
    n = 0
    for col in SENSOR_COLS:
        for t, a, b, r in transitions(rows, col)[1:]:
            print(f"   {fmt_t(t)}  {col:5s} {a} -> {b}   (nDeStep={r.get('nDeStep')} nFeedStep={r.get('nFeedStep')} nOutStep={r.get('nOutStep')})")
            n += 1
    if n == 0: print("   brak")

    # napedy
    print("\n-- zadania napedow (dN_req) i bledy:")
    drives = sorted({k[1:-4] for k in rows[0] if k.startswith("d") and k.endswith("_req")}, key=int)
    n = 0
    for d in drives:
        for t, a, b, r in transitions(rows, f"d{d}_req")[1:]:
            print(f"   {fmt_t(t)}  d{d:>2} req {a}->{b}  run={r.get(f'd{d}_run')} sw={r.get(f'd{d}_sw')} hz={r.get(f'd{d}_hz')}")
            n += 1
        for t, a, b, r in transitions(rows, f"d{d}_flt")[1:]:
            if b == "1":
                print(f"   {fmt_t(t)}  *** FAULT d{d}  sw={r.get(f'd{d}_sw')}  nDeStep={r.get('nDeStep')}")
                n += 1
    if n == 0: print("   brak")

    # enkoder
    print("\n-- enkoder desztaplarki: skoki i zatrzask xInPos")
    n = 0
    for r in rows:
        try:
            st = int(r.get("de_step") or 0)
        except ValueError:
            st = 0
        if abs(st) > 2000:
            print(f"   {fmt_t(r['_t'])}  ENCJUMP de_step={st} de_raw={r.get('de_raw')} de_pos={r.get('de_pos')} nDeStep={r.get('nDeStep')}")
            n += 1
    for t, a, b, r in transitions(rows, "de_inPos")[1:]:
        if b == "1":
            print(f"   {fmt_t(t)}  xInPos 0->1  nDeStep={r.get('nDeStep')} de_pos={r.get('de_pos')} de_remain={r.get('de_remain')} goTo={r.get('de_goToEnc')}")
            n += 1
    if n == 0: print("   brak")

    # bity
    print("\n-- bity sterujace / uzgodnienia / bezpieczenstwo:")
    ev = []
    for col in BIT_COLS:
        for t, a, b, r in transitions(rows, col)[1:]:
            ev.append((t, col, a, b))
    ev.sort()
    for t, col, a, b in ev:
        print(f"   {fmt_t(t)}  {col:20s} {a} -> {b}")
    if not ev: print("   brak")

def around(rows, t, win, cols):
    sel = [r for r in rows if abs(r["_t"] - t) <= win]
    cols = cols or ["why"] + STEP_COLS + ["de_pos","de_accum","de_remain","de_inPos","de_runReq","de_brakeRel","de_jawsClosed","out14","out16","d1_run","d1_flt"]
    print("t_ms;" + ";".join(cols))
    for r in sel:
        print(f"{r['_t']};" + ";".join(str(r.get(c, "")) for c in cols))

def changes(rows, cols):
    prev = None
    print("t_ms;" + ";".join(cols))
    for r in rows:
        cur = tuple(r.get(c, "") for c in cols)
        if cur != prev:
            print(f"{r['_t']};" + ";".join(cur))
            prev = cur

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--around", type=int, help="t_ms srodka okna")
    ap.add_argument("--win", type=int, default=5000, help="polowa szerokosci okna [ms]")
    ap.add_argument("--cols", nargs="*", help="kolumny do wypisania")
    a = ap.parse_args()
    rows = load(a.path)
    if a.around is not None:
        around(rows, a.around, a.win, a.cols)
    elif a.cols:
        changes(rows, a.cols)
    else:
        overview(rows, a.path)
