# Desztaplarka — analiza upadków stosu (9 września 2026)

Objaw: w trakcie normalnej pracy, po 3, 5 albo 7 paletach, szczęki
otwierają się z ładunkiem, stos spada, a potem wózek jeździ na pozycje
niezgodne z nauczonymi — „jakby rozsypała się pozycja enkodera".
Powtarzalne, losowe co do momentu.

Analiza oparta na aktualnym `MAIN.TcPOU` z dysku, `FB_CamAxis.TcPOU`,
`ST_StackCfg`, `GVL_PERSIST` i — czego wcześniej nie oglądano — na
konfiguracji sprzętu w `Ponowne_skanowanie.tsproj`.

---

## 1. Co wynika z `.tsproj`, a nie było wcześniej w kontekście

| element | fakt |
|---|---|
| enkodery krzywek | **Posital UCD-LK, IO-Link, magnetyczne multiturn** (`LK-MT`, IODD 2022-02-02) |
| gdzie podpięte | **EL6224 (Term 48) port 3 (desztaplarka) i port 4 (sztaplarka)** — Device 1, szyna lokalna CX |
| na tym samym EL6224 | port 1 i 2: wyspy Festo VAEM-L1-S-PT (stacja 5) |
| zmienna | `GVL.IO_Destaker_Act_Pos` ← `IO-Link Port3^Position` (INT32) |
| parametr enkodera | **`Singleturn Resolution = 65535`** (nie 65536) |
| parametr enkodera | `Total Resolution = 2147482880` (zawinięcie pozycji multiturn) |
| komendy systemowe | `0xD0` pozycja := Preset, `0xE4` pozycja := 0 |
| szczęki desztaplarki | `OUTPUTS[14]/[15]` ← EP2338 (Box 32, Device 2), kanały 10/11 |
| hamulec krzywki | `OUTPUTS[16]` ← EL2068 (Term 4) kanał 5 |
| bezpieczeństwo | EL1918 + EL2904, sygnały `GVL_SAFETY.xSTO / xAir / xResetCmd` — **nieużywane w MAIN** |
| stan portów IO-Link | `State Ch1..4` EL6224 i `Device status` Posital — **niepodlinkowane do PLC** |

Konsekwencja: PLC nie ma żadnej informacji o tym, czy wartość enkodera
jest ważna. Nie ma też informacji o STO ani o powietrzu.

---

## 2. Trzy mechanizmy, które pasują do objawu

### 2.1 Błędna próbka enkodera zatrzaskuje `xInPos` (kod)

`FB_CamAxis` liczy przyrost i prostuje przejście przez zero progiem
±32768. Przy tym `xInPos` jest **zatrzaskiem** — raz ustawiony nie gaśnie
do nowego ruchu. Te dwie rzeczy razem dają pułapkę:

```
diPos (prawdziwe) = 40000, w kroku 70, cel = dół (0)
próbka błędna = 0 przez JEDEN cykl (10 ms):
    diStep = 0 - 40000 = -40000  <  -32768  ->  +25536   (uznane za obrót)
    diAccum += 25536                            ->  diRemain < 0
    xInPos := TRUE                              ->  ZATRZAŚNIĘTE
następny cykl, próbka wraca do 40000:
    diStep = +40000 > 32768 -> -25536, diAccum wraca, diRemain = 25536
    ale xInPos nadal TRUE  ->  xDeAtPos  ->  nDeStep := 80
krok 80: hamulec po 0,7 s, szczęki OTWARTE na pozycji 40000
```

Symulacja skanowa (`sim_cam_glitch.py`, cykl 10 ms, wierna kolejność
akcji) potwierdza:

| scenariusz | wynik |
|---|---|
| bez zakłóceń | szczęki otwarte przy `diPos = 24` (dół) |
| jedna próbka `0` przy `diPos ≈ 40000`, krok 70 | **szczęki otwarte przy `diPos = 40000`** |
| jedna próbka `0` przy `diPos ≈ 30000` (< 32768) | nieszkodliwe — dojazd na dół |

Zatem glitch bije **tylko w drugiej połowie obrotu** (`diPos > 32768`),
czyli podczas zjazdu ze stosem w kroku 70 i podczas jazdy do domu
w kroku 0. W krokach 20 i 50 (`diPos` 0…24000) ten sam glitch nic nie
robi. To tłumaczy, dlaczego awaria wygląda zawsze jak „otworzyła na
wysokości podczas schodzenia".

Skąd błędna próbka: EL6224 przy utracie komunikacji IO-Link
(`COMSTOP`, brak urządzenia) może podać w danych wejściowych 0 —
**do sprawdzenia na maszynie** (pkt 3.2). Kabel IO-Link biegnie
z szafy na maszynę obok kabli falowników; EMC i zakłócenia zasilania
L+ są realne.

Po takim incydencie kod dalej działa: krok 85 → 20 liczy cel do
środka od bieżącego `diPos` (40000), więc wózek jedzie „do przodu"
przez dół i dopiero do środka — 41 000 impulsów, w leżący stos.
Dla obserwatora: „jeździ na pozycje z dupy".

**Zastrzeżenie.** W poprzednim incydencie odczytano po upadku
`nHeld = 6`. Krok 80 zeruje `nHeld` w pierwszym cyklu. Jeżeli ten
odczyt jest z chwili po upadku, to w **tamtym** incydencie program
nie przeszedł przez 80 i cały czas kazał trzymać — czyli mechanizm
2.1 go nie tłumaczy. Może tłumaczyć obecny. To rozstrzyga czarna
skrzynka (pkt 3.1).

### 2.2 Utrata momentu na krzywce przy zwolnionym hamulcu (falownik / STO)

Jeżeli falownik 1 wyłoży się w trakcie ruchu (przeciążenie, I²t,
STO z bezpieczeństwa), `FB_CamAxis` reaguje tak:

```
xRunReq pozostaje TRUE            (xMoveWanted nadal spełnione)
tonDrvAck  1,5 s                  -> xNoDrvAck, xStall
xMoveWanted := FALSE
tofBrake    0,7 s                 -> dopiero teraz hamulec ZAŁOŻONY
```

Razem **≈ 2,2 s z puszczonym hamulcem i bez momentu**. Stos na
korbie napędza ją wstecz lub do przodu, wózek opada, szczęki zostają
wyrwane z desek albo ześlizgują się. Korba ląduje w przypadkowym
miejscu. Program dalej „każe trzymać" (`OUTPUTS[14] = TRUE`,
`nHeld` niezmienione) — **zgodne z odczytem `nHeld = 6`**.

Dodatkowe okoliczności sprzyjające:

- `tCamBrakeHold = 0,7 s < rampa 1 s` — świadomie, ale znaczy to, że
  przy każdym zatrzymaniu falownik przez 0,3 s pracuje w zaporę na
  założonym hamulcu. Kilka cykli z rzędu to obciążenie termiczne;
  „po 3, 5, 7 paletach" pasuje do kumulacji.
- `xAutoResetOnStart = TRUE` — przy kolejnym `START_DESTACK` błąd
  falownika jest kasowany automatycznie. **Dowód znika.**
- Sygnały bezpieczeństwa (`GVL_SAFETY.xSTO`) nie są czytane
  w `MAIN`, więc zadziałanie kurtyny lub grzybka jest dla sekwencji
  niewidoczne.

### 2.3 Szczęki puszczają pneumatycznie / przez zanik zasilania zaworu

Szczęki trzymają 6 palet, gdy stacja 5 uruchamia sześć siłowników
rozrywających i podnoszenie. Spadek ciśnienia w sieci albo zanik
zasilania boxa EP2338 (jeśli jego 24 V idzie przez stycznik
bezpieczeństwa i zawór jest ze sprężyną) otwiera szczęki bez udziału
programu. Też zgodne z `nHeld = 6`. Gdy jednocześnie STO odcina
falownik, dostajemy oba objawy naraz: upadek i losową pozycję korby.

---

## 3. Co zmierzyć — w tej kolejności, zanim ruszymy kod sekwencji

### 3.1 Czarna skrzynka w PLC (jedyna zmiana kodu na teraz)

Bufor kołowy w `MAIN`, co cykl, np. 3000 próbek (30 s), zamrażany
automatycznie. Zapisywać:

```
GVL.IO_Destaker_Act_Pos      surowa wartość z IO-Link
fbCamDestack.diPos / diAccum / diRemain / diStep / xInPos / xRunReq / xBrakeRelease
nDeStep, GVL_PERSIST.St03.Mem.nHeld, nRemaining
xDeJawsClosed, GVL.OUTPUTS[14], GVL.OUTPUTS[15], GVL.OUTPUTS[16]
axDrvRunning[1], axDrvFault[1], awDrvStatus[1]
GVL_SAFETY.xSTO, GVL_SAFETY.xAir
(po podlinkowaniu) EL6224 State Ch3, Posital Device status, WcState Term 48
```

Wyzwalacze zamrożenia (dowolny): `ABS(fbCamDestack.diStep) > 2000`,
zbocze `axDrvFault[1]`, zbocze `NOT axDrvRunning[1]` przy `xRunReq`,
wejście w krok 80 przy `diPos` dalej niż 3000 od dołu, opadające
zbocze `xSTO` lub `xAir`, bit ręczny. Po zamrożeniu jeszcze 200
próbek „po", potem stop. Odczyt online z tablicy.

To rozstrzyga między 2.1, 2.2 i 2.3 przy pierwszym następnym
incydencie, bez zgadywania.

### 3.2 Bez kodu, od ręki

1. **Pamięć błędów falownika 1** (NORD P700/P701, NORDCON albo
   panel) — wpisy z godzin awarii przesądzają o 2.2.
2. **Wyciągnąć wtyk enkodera na chwilę** przy stojącej maszynie
   (START_DESTACK = FALSE) i patrzeć na `fbCamDestack.diPos`:
   spada do 0 → EL6224 zeruje dane, wektor 2.1 jest realny;
   zamarza → 2.1 wymaga innego źródła glitcha.
3. Sprawdzić `sDePhase` **zaraz po incydencie, przed jakimkolwiek
   resetem**: komunikat `CZUWAK - falownik 1 nie potwierdza pracy`
   = 2.2.
4. Zasilanie EP2338 (Box 32) i typ zaworu szczęk (impulsowy
   bistabilny vs sprężyna). Manometr na gałęzi szczęk desztaplarki.

### 3.3 Podlinkować diagnostykę w `.tsproj`

`Term 48 (EL6224)^DeviceState Inputs^State Ch3` i `Ch4`,
`IO-Link Port3^Device status`, `WcState` terminala → nowe zmienne
w `GVL`. Bez tego PLC nigdy nie dowie się, że enkoder zniknął.

---

## 4. Proponowane zabezpieczenia (po pomiarach, każde osobno)

### 4.1 `FB_CamAxis`: kontrola wiarygodności próbki

Po korekcie przejścia przez zero: jeżeli `ABS(diStep) > diStepMax`
(kilkukrotność największego fizycznie możliwego przyrostu na cykl —
do ustalenia z pomiaru `diStepMax` w czarnej skrzynce), **próbkę
odrzucić**: `diStep := 0`, `diPosPrev` bez zmiany, licznik
`nBadSamples`. Jeżeli odrzuconych z rzędu > ~20 (200 ms), wartość
jest nową rzeczywistością: przyjąć ją, ale zapalić `xEncJump`
i potraktować jak `xStall` — ruch stoi, hamulec zakłada się,
sekwencja nie wykonuje `CASE`, więc `xDeJawsClosed` zostaje jak było
(szczęki nie puszczają). Wymaga `RESET_CAM`.

Dodatkowo: gdy port IO-Link nie jest w `OP` albo `Device status ≠ 0`
albo `WcState ≠ 0` — próbki nie przyjmować w ogóle.

### 4.2 `FB_CamAxis`: hamulec natychmiast przy utracie napędu

Jeżeli `xRunReq` i (`axDrvFault[1]` lub `NOT xDrvRunning` po tym,
jak już był `TRUE` w tym ruchu, lub `NOT xSTO`): `xMoveWanted := FALSE`
**i ominąć `tBrakeHold`** — hamulec ma paść w tym samym cyklu.
Skraca okno swobodnego opadania z ≈2,2 s do jednego cyklu.

### 4.3 `xAutoResetOnStart := FALSE` na czas diagnozy

Żeby błąd falownika przeżył do odczytu.

### 4.4 Drobne, ale do zrobienia kiedyś

- `Singleturn Resolution = 65535` vs `MOD 65536` w `FB_CamAxis`:
  dryf −1 impuls na obrót, po 1000 paletach 1000 impulsów. Albo
  ustawić enkoder na wartość, którą kod zakłada, albo zrobić
  z 65536 parametr `diCountsPerRev` i wpisać prawdziwą wartość.
- `Total Resolution = 2147482880` nie jest wielokrotnością ani
  65535, ani 65536. Przejście surowej pozycji przez 0 wstecz
  (po `Preset = 0` na dole i cofnięciu jogiem) daje w `diPos` skok
  o 768 impulsów zamiast ciągłości. Po bazowaniu presetem lepiej
  ustawić preset na wartość ze środka zakresu, np. 2^30, nie 0.
- Czasówka `tDrvAck = 1,5 s` przy 1000 Nm na korbie jest długa.

---

## 5. Czego ta analiza nie zmienia

- Nie dodajemy „zjazdu z zamkniętymi szczękami" w kroku 0 — decyzja
  Karola stoi.
- Nie ruszamy nastaw czasowych ani pozycji 0/16000/24000.
- Nie zmieniamy kolejności akcji w `MAIN`.
- Hipotezy wykluczone wcześniej (reguła `nHeld <= 0`, „gubienie
  cewek") pozostają wykluczone; ta analiza ich nie reanimuje.

---

## 6. Pytania do Karola

1. Jak wygląda ręczne bazowanie: komenda `0xE4`/`0xD0` po IO-Link
   z TwinCAT, czy coś innego?
2. Czy po którymkolwiek incydencie trzeba było kasować `RESET_CAM`
   lub `xCmdResetDrives`, żeby ruszyć dalej?
3. Ile trwa zjazd w kroku 70 (góra → dół, ~41 000 impulsów)? Z tego
   liczymy `diStepMax`.
4. Zawór szczęk desztaplarki: bistabilny impulsowy czy ze sprężyną?
   Skąd zasilanie EP2338 (Box 32)?
5. Czy w chwilach awarii stacja 5 była w trakcie rozrywania
   (110…160)?

---

## 7. Potwierdzenie z logu — 11 września 2026, `docs\logs\tp_20260911_114649.csv`

Trzecia paleta w cyklu, awaria o 11:50:45 (t = 235,9 s od otwarcia pliku).

| t [s] | zdarzenie |
|---|---|
| 32,4 | ręczne bazowanie: `de_raw` 38919 → 0 przy stojącej korbie (zerowanie enkodera po IO-Link) |
| 234,9 | krok 50 → 60, wózek na górze, `de_raw` = 155 087 (`de_pos` 24015), stos na szczękach |
| **235,9** | **`de_raw` = 0 przez 12,3 s** — enkoder zniknął z IO-Link, EL6224 podaje zero |
| 247,46 | IN4 → krok 70; cel liczony z `de_pos = 0` daje drogę 0 → `xInPos` natychmiast |
| 247,48 | krok 80, hamulec już założony → **szczęki otwarte na górze**, stos spada, `nHeld` → 0 |
| 248,2 | enkoder wraca: `de_raw` 2 147 482 878, potem 24, 20, 17 — **wyzerowany na pozycji górnej** |
| 278,9 | `xSt05_Done` → krok 20 „na środek" od fałszywego zera → korba w złym miejscu, szczęki w bok palety |

Wnioski:

- Mechanizm z §2.1 potwierdzony, w wariancie „cel liczony z fałszywego
  zera" (a nie tylko zatrzask). Kod nie ma żadnej kontroli wiarygodności
  pozycji.
- EL6224 przy utracie urządzenia IO-Link podaje w `Position` **0**.
- Po ponownym połączeniu enkoder miał **nowe zero w miejscu, gdzie stał**
  (góra). Do ustalenia: Data Storage / parametry startowe portu 3 EL6224
  (`Preset = 0` w `.tsproj`) albo nietrwałe zerowanie komendą.
- `nHeld = 6` z poprzedniego incydentu nadal wskazuje, że tam mogła być
  inna droga (§2.2/2.3) — logger to rozstrzygnie przy następnym razie.

Do zrobienia (kolejność): (1) `xPosValid` w `FB_CamAxis` z `State Ch3/Ch4`
+ `WcState` EL6224 + odrzucanie nierealnych skoków, przy niewiarygodnej
pozycji stop z zachowaniem stanu szczęk; (2) wykrycie skoku pozycji po
powrocie enkodera → stop i żądanie bazowania; (3) ustalić przyczynę zaniku
IO-Link (Diag History EL6224 o 11:50:45, kabel, L+); (4) wyłączyć
przestawianie zera przez master.
