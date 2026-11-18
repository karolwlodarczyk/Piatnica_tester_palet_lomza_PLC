"""Symulacja skanowa FB_CamAxis + krok 70 desztaplarki (10 ms).
Pytanie: czy JEDNOCYKLOWY blad odczytu enkodera (np. 0 z IO-Link)
zatrzaskuje xInPos i konczy krok 70 na wysokosci?
"""
DT = 10  # ms

class TON:
    def __init__(s): s.t = 0; s.q = False
    def __call__(s, IN, PT):
        if IN:
            s.t = min(s.t + DT, PT); s.q = s.t >= PT
        else:
            s.t = 0; s.q = False
        return s.q

class TOF:
    def __init__(s): s.t = 0; s.q = False
    def __call__(s, IN, PT):
        if IN: s.t = 0; s.q = True
        else:
            if s.q:
                s.t += DT
                if s.t >= PT: s.q = False
        return s.q

class RTRIG:
    def __init__(s): s.old = False
    def __call__(s, clk):
        q = clk and not s.old; s.old = clk; return q

class FB_CamAxis:
    def __init__(s):
        s.xInit=False; s.diPosPrev=0; s.diTargetPrev=0; s.diMoveStart=0
        s.diAccum=0; s.diTurns=0; s.xInPos=False; s.xStall=False; s.xNoDrvAck=False
        s.rtrgGo=RTRIG(); s.rtrgSet=RTRIG(); s.rtrgReset=RTRIG()
        s.tofBrake=TOF(); s.tonBrakeOpen=TON(); s.tonGrace=TON(); s.tonStall=TON()
        s.tonRest=TON(); s.tonDrvAck=TON(); s.diStallRef=0; s.xRunPrev=False
        s.diStopAccum=0; s.xCoasting=False; s.diCoast=0; s.xRunReq=False
        s.tBrakeHold=700; s.tStallGrace=3000; s.tStall=2000; s.diStallMin=20; s.tDrvAck=1500; s.tRest=300
        s.diStep=0; s.diRemain=0
    def __call__(s, diRawPos, xEnable, xGoTo, diTargetAbs, xSetAccum=False, diSetAccumTo=0, xDrvRunning=True, xReset=False):
        diPos = diRawPos % 65536
        s.diPos = diPos
        if not s.xInit:
            s.xInit=True; s.diPosPrev=diPos; s.diStallRef=diPos; s.diTargetPrev=diTargetAbs
        diStep = diPos - s.diPosPrev
        if diStep > 32768: diStep -= 65536; s.diTurns -= 1
        if diStep < -32768: diStep += 65536; s.diTurns += 1
        s.diPosPrev = diPos; s.diStep = diStep
        s.diAccum += diStep
        if s.rtrgSet(xSetAccum):
            s.diAccum = diSetAccumTo; s.diMoveStart = diSetAccumTo; s.xInPos=True
            s.diStopAccum = diSetAccumTo; s.xCoasting=False
        xNewMove = s.rtrgGo(xGoTo and xEnable) or (diTargetAbs != s.diTargetPrev)
        s.diTargetPrev = diTargetAbs
        if xNewMove:
            s.diMoveStart = s.diAccum; s.xInPos=False; s.diStallRef = diPos
        s.diRemain = diTargetAbs - s.diAccum
        if s.diRemain <= 0: s.xInPos = True
        xMoveWanted = xEnable and not s.xStall and (xGoTo and not s.xInPos)
        s.xBrakeRelease = s.tofBrake(xMoveWanted, s.tBrakeHold)
        xMoving = xMoveWanted and s.xBrakeRelease
        s.xRunReq = xMoving
        # czuwaki
        xStallArmed = s.tonGrace(s.xRunReq, s.tStallGrace)
        xStallReset = abs(s.diAccum - s.diStallRef) > s.diStallMin or not xStallArmed or xNewMove
        if xStallReset: s.diStallRef = s.diAccum
        if s.tonStall(xStallArmed and not xStallReset, s.tStall): s.xStall=True
        if s.tonDrvAck(s.xRunReq and not xDrvRunning, s.tDrvAck): s.xNoDrvAck=True; s.xStall=True
        return s

def run(glitch_at_pos=None, glitch_val=0, glitch_len=1, speed=60, label=""):
    """Krok 60 -> 70 -> 80. Wozek na gorze (diPos=25000 po dojezdzie), cel dol=0.
    speed = impulsow na cykl 10 ms (60 -> ok. 11 s na obrot)."""
    fb = FB_CamAxis()
    raw = 25000 + 3*65536   # dowolna liczba obrotow w surowej wartosci
    step = 60; stepOld = 60
    target = 0; goto = False; goToEnc = 0
    jaws = True; brakeRel = True
    log = []
    glitch_left = 0
    for cyc in range(4000):
        # --- fizyka: os obraca sie, gdy falownik dostal zadanie (uproszczenie: bez rampy)
        if fb.xRunReq: raw += speed
        raw_read = raw
        if glitch_at_pos is not None and (raw % 65536) >= glitch_at_pos and glitch_left == 0 and not getattr(run, "done", False) and step == 70:
            glitch_left = glitch_len; run.done = True
        if glitch_left > 0:
            raw_read = glitch_val; glitch_left -= 1
        # --- MAIN / ACT_CamCycles
        newStep = step != stepOld; stepOld = step
        atPos = fb.xInPos and not newStep
        goto = False
        if step == 60:
            if cyc >= 5: step = 70          # IN4 po 50 ms
        elif step == 70:
            goto = True; goToEnc = 0; jaws = True
            if atPos: step = 80
        elif step == 80:
            jaws = fb.xBrakeRelease   # otwarcie po zalozeniu hamulca
        if newStep:
            d = goToEnc - fb.diPos if hasattr(fb, 'diPos') else 0
            if d < 0: d += 65536
            if d >= 65536 - 5000: d = 0
            target = fb.diAccum + d
        fb(raw_read, True, goto, target)
        pos_true = raw % 65536
        if cyc % 50 == 0 or newStep or (glitch_left>0) or (step==80 and not jaws and len([l for l in log if 'OTWARTE' in l])==0):
            log.append(f"{cyc*DT:6d} ms step={step:2d} rawRead%={raw_read%65536:5d} posTrue={pos_true:5d} accum={fb.diAccum:6d} remain={fb.diRemain:6d} inPos={int(fb.xInPos)} run={int(fb.xRunReq)} brk={int(fb.xBrakeRelease)} jaws={'ZAMKN' if jaws else 'OTWARTE'}")
        if step == 80 and not jaws:
            log.append(f"==> {label}: SZCZEKI OTWARTE przy pozycji rzeczywistej {pos_true} (dol = 0)")
            break
    run.done = False
    return log

print("=== A. bez zaklocen ===")
for l in run(label="bez zaklocen")[-6:]: print(l)
print("\n=== B. jeden cykl odczytu = 0 przy diPos ~ 40000 (w kroku 70) ===")
for l in run(glitch_at_pos=40000, label="glitch 0 @40000"):
    if 'step=70' in l and ('rawRead%=    0' in l) or '==>' in l or 'step=80' in l: print(l)
print("\n=== C. jeden cykl odczytu = 0 przy diPos ~ 30000 (< 32768) ===")
out = run(glitch_at_pos=30000, label="glitch 0 @30000")
for l in out[-4:]: print(l)
print("\n=== D. odczyt zamrozony przez 5 cykli, potem skok (np. IO-Link 'COMSTOP') przy 40000 ===")
# zamrozenie: podstawiamy stara wartosc -> brak kroku; tu symulujemy jako glitch_val=ostatnia (niegrozne) - pomijamy
