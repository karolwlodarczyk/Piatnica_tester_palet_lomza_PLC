# Tester palet — kontekst uruchomieniowy

Stan na 9 września 2026. Plik jest po to, żeby nowy wątek (dowolny model)
mógł podjąć pracę bez odtwarzania kilkunastu godzin rozmowy.

**Jak zacząć nowy wątek:** wskaż ten plik i napisz, co się właśnie dzieje na
maszynie. Nie streszczaj historii — ona jest tutaj.

---

## 0. Zasady pracy — przeczytaj zanim cokolwiek zmienisz

Te reguły powstały z konkretnych szkód na maszynie. Każda kosztowała czas
albo palety.

1. **Przed KAŻDĄ edycją pobierz aktualny plik z dysku Karola.** On zmienia
   nastawy online i zapisuje projekt między turami. Praca na własnej kopii
   sprzed kilku tur nadpisuje jego pomiary starymi wartościami. To się już
   zdarzyło.

2. **Nastawy czasowe są jego pomiarami polowymi.** Nie zmieniaj ich bez
   pytania — nawet „przy okazji", nawet gdy wyglądają dziwnie. Wartości
   czytaj **z jego pliku**, nigdy z notatek ani z tego dokumentu.

3. **Dodanie nowej nastawy, która ogranicza istniejący ruch, TEŻ jest zmianą
   ruchu.** `tSt05_Push` = 4 s wyglądało jak nowa opcja, a skróciło dojazd
   palety z 9 s do 4 s i paleta przestała dojeżdżać do blokady.

4. **Jedna zmiana naraz, z wypisanym oczekiwanym efektem na maszynie.**

5. **Nie zgaduj przyczyny — zmierz.** Wielokrotnie prowadzona pewna hipoteza
   okazywała się fałszywa (reguła nadrzędna desztaplarki, enkoder, blokada
   załączenia). Poproś o wartości zmiennych, zanim postawisz diagnozę.

6. **Symuluj.** W tej sesji symulacja skanowa w Pythonie (cykl 10 ms,
   odwzorowana kolejność akcji) znalazła dwa błędy, których czytanie kodu nie
   wychwyciło. To jest tanie i skuteczne — rób to.

7. **Komentarze w kodzie po polsku, bez polskich znaków** (edytor TC3).
   Pliki `.TcPOU` to XML, UTF-8 **z BOM**, końce linii CRLF. Po edycji
   sprawdź: poprawność XML, brak znaków spoza ASCII, bilans
   `IF/END_IF`, `CASE/END_CASE`, `FOR/END_FOR`.

---

## 1. Gdzie co leży

```
C:\Users\karol\Desktop\Tester palet aplikacja\
  Tester_Palet_2\Ponowne_skanowanie\Ponowne_skanowanie\TC3_Tester_Palet\
    POUs\MAIN.TcPOU                      <- CAŁA logika uruchomieniowa
    POUs\POUs\FB\FB_CamAxis.TcPOU        <- oś krzywki (desztaplarka + sztaplarka)
    POUs\POUs\FB\FB_NordSK550PP.TcPOU    <- falownik NORD
    DUTs\DUTs\ST_StackCfg.TcDUT          <- pozycje krzywek (nieulotne)
    GVLs\GVL_PERSIST.TcGVL
  CLAUDE.md                              <- reguły architektury projektu
  docs\ZALOZENIA.md                      <- założenia maszyny
```

Katalog `oprogramowanie\TC3_Nord_SK550P` — **ignorować**, to luźny przykład,
nie część aplikacji.

`PRG_Machine` i cała warstwa obiektowa (`FB_TransportNodeBase` i pochodne)
**nie jest wywoływana**. Docelowa architektura jest opisana w `CLAUDE.md`,
ale dziś maszyna chodzi wyłącznie na `MAIN`.

Runtime na osobnym sterowniku CX, XAE na laptopie.

---

## 2. Maszyna

16 stacji transportowych, 19 falowników NORDAC PRO SK 550P po EtherCAT.
Wejście: stosy 1–15 palet. Wyjście OK: sztaple po 15. Wyjście NOK:
pojedyncze palety.

| stacja | funkcja | napęd |
|---|---|---|
| 1 | załadunek | 8 |
| 2 | bufor | 9 |
| 3 | **desztaplarka** | 10 (transporter), 1 (krzywka) |
| 4 | test ściskania | 4, 3 (rolki dociskowe) |
| 5 | **test rozrywania** | 5 |
| 6 | pomiar laserowy | 6 |
| 7 | etykietowanie | 11 |
| 8 | rozjazd | 12, 2 (krzywka st.11) |
| 9 | transporter łańcuchowy | 7 |
| 10 | przekierowanie | 16 |
| 11 | sztaplarka | 13 |
| 12 | bufor | 14 |
| 13 | wyjście OK | 15 |
| 14, 15 | bufory odrzutu | 17, 18 |
| 16 | odbiór NOK | 19 |

**Czujniki** — jedno miejsce interpretacji polaryzacji, `ACT_Inputs`,
tablica `axInInverted[1..10]`. Po XOR: `xPal_* = TRUE` znaczy **jest paleta**.

| wejście | zmienna | stacja |
|---|---|---|
| INPUTS[2] | `xPal_St03` | 3 |
| INPUTS[3] | `xPal_St04In` | wjazd na 4 |
| INPUTS[4] | `xPal_St04End` | koniec 4 |
| INPUTS[5] | `xPal_St07` | **7** |
| INPUTS[6] | `xPal_St13` | koniec 13 |
| INPUTS[7] | `xPal_St08` | **8** |
| INPUTS[8] | `xPal_St11` | 11 (polaryzacja niesprawdzona) |
| INPUTS[10] | `xPal_St16` | 16 |

INPUTS[1] (stacja 1) **nie jest używany** — zastępuje go bit operatora
`xSt01_StackReady`. Stacja 6 **nie ma czujnika** — odcinek 5→6 jedzie na
czasówkę.

Napędy odwrócone (`axReverse`): 5, 6, 7, 8, 10, 11, 12, 17, 18, 19.
Napęd 3 (rolki dociskowe st.4) jest **zablokowany** — przy pełnej
częstotliwości pchał paletę tak mocno, że wykładał falownik transportera.
Zanim go włączysz, ustaw mu własną częstotliwość `alrDriveFreq[3]`;
`axDriveEnabled[3] := TRUE` włącza go online.

---

## 3. Struktura programu

Kolejność akcji w `MAIN` jest **częścią kontraktu**:

```
ACT_Config       jednorazowa konfiguracja (axDriveEnabled, axReverse)
ACT_Inputs       czujniki -> xPal_*   (jedyne miejsce polaryzacji)
ACT_Sequence     stara sekwencja START_TEST; kasuje axRunReq[1..20]
ACT_CamCycles    desztaplarka + sztaplarka; RESET_CYCLE; cewki szczęk
ACT_TestFeed     transport próby całościowej: tory A, B1, B2, B3
ACT_ResetDrives  kasowanie błędów falowników
ACT_ApplyDrives  warunki nadrzędne + M_Start/M_Stop na zboczu
ACT_Drives       wywołanie fbNord[1..20]
ACT_Outputs      mapowanie na zawory i wyjścia
```

### Sześć maszyn stanu

| maszyna | zakres | podgląd |
|---|---|---|
| `nDeStep` | desztaplarka, stacja 3 | `sDePhase` |
| `nStStep` | sztaplarka, stacja 11 | `sStPhase` |
| `nFeedStep` | **tor A**: stacja 1 → 3 → 4 → cykl stacji 5 | `sFeedPhase` |
| `nOutStep` | **tor B1**: stacja 5 → 6 → 7 | `sOutPhase` |
| `nOut2Step` | **tor B2**: stacja 7 → 8 | `sOut2Phase` |
| `nOut3Step` | **tor B3**: stacja 8 → łańcuch → 10 → 14 → 15 → 16 | `sOut3Phase` |

Rozbicie na tory daje **buforowanie**: w obiegu mogą być naraz paleta na
stacji 5, na 7, na 8 i jedna w drodze na 16.

### Kto jest właścicielem którego napędu

- tor A: 8, 9, 10, 4, (3), 5
- tor B1: 5, 6, 11
- tor B2: 11, 12
- tor B3: 7, 16, 17, 18, 19
- krzywki: 1 (desztaplarka), 2 (sztaplarka) — sterowane **wyłącznie** przez
  `ACT_CamCycles`

**Zasoby wspólne i ich bramki:**

| zasób | kto rywalizuje | rozstrzygnięcie |
|---|---|---|
| napęd 5 + blokada st.5 | tor A (wjazd) vs tor B1 (wyjazd) | krok 75 toru A: czeka aż `nOutStep = 0` lub `>= 200` |
| napęd 11 (st.7) | tor B1 vs tor B2 | krok 205: oddaje paletę dopiero gdy `nOut2Step = 0` |
| napęd 12 (rolki st.8) | tor B2 vs tor B3 | krok 218: oddaje dopiero gdy `nOut3Step = 0` |
| rolki st.8/10 vs łańcuch | `ACT_ApplyDrives` | `IF axRunReq[7] THEN axRunReq[12] := FALSE; axRunReq[16] := FALSE` |
| blokada st.5 vs transporter | `ACT_ApplyDrives` | krok 180 nie ruszy, dopóki `tonSt05BlockDown.Q` nie potwierdzi opuszczenia |

### Tabele kroków

**Tor A** (`nFeedStep`)

```
  0  czekam na xSt01_StackReady
 10  st.1 -> st.3, czekam IN2                    napędy 8,9,10
 15  dobieg po IN2 (tFeedSt03Stop)               9,10
 20  czekam na xDe_PalletReleased z desztaplarki
 30  jazda na st.4, czekam IN3                   4,10
 40  odstęp przed dociskiem (tSt04_EntryToPress) 3,4,10
 50  górne dociski schodzą (tSt04_UpToLo)        3,4,10
 60  TEST, czekam IN4                            3,4,10
 70  dojazd (tSt04_StopDelay)                    4
 75  BRAMKA: czekam aż zwolni się stacja 5
 80  st.4 -> st.5, blokada wysunięta             4,5   (napędy tylko przez tSt05_Push)
100  uspokojenie (tSt05_Settle)
110..160  cykl rozrywania, każdy krok tCylTime
170  blokada opada; PRZEKAZANIE palety torowi B1 -> krok 20
```

**Tor B1** (`nOutStep`): `0 → 180` (st.5→6, `tFeed5to6`, napędy 5,6)
`→ 200` (st.6→7, czekam IN5, napędy 6,11) `→ 205` (paleta czeka) `→ 0`

**Tor B2** (`nOut2Step`): `0 → 210` (st.7→8, czekam IN7, napędy 11,12)
`→ 215` (dobieg `tFeedSt08Stop`) `→ 218` (paleta czeka) `→ 0`

**Tor B3** (`nOut3Step`): `0 → 220` (rolki 8 i 10 w dół) `→ 230` (łańcuch,
`tFeed9Chain`, napęd 7) `→ 240` (rolki w górę) `→ 250` (st.10→14)
`→ 260` (st.14→15) `→ 270` (st.15→16, czekam IN10) `→ 275` (dobieg)
`→ 280` (czekam aż operator odbierze) `→ 0`

**Desztaplarka** (`nDeStep`)

```
  0  dom: szczęki otwarte, jazda na dół
 10  czekam na sztaplę (IN2); ustawia nRemaining := nStackSize
 20  jazda na pozycję pośrednią, szczęki otwarte
 30  hamulec założony, odliczam tDeGripDelay
 40  szczęki chwytają 2. paletę od dołu; nHeld := nRemaining - 1
 50  jazda na górę — stos uniesiony
 60  paleta zwolniona, czekam IN4; nRemaining := nRemaining - 1
 70  dopełnienie obrotu — zjazd stosu na dół
 80  hamulec, szczęki otwierają się, stos odłożony; nHeld := 0
 85  BRAMKA: na dole czekam na koniec cyklu stacji 5 (xSt05_Done)
 90  ostatnia paleta wyjeżdża sama, bez chwytu
```

**Sztaplarka** (`nStStep`) — 0, 10, 20, 25, 30, 40, 50, 60, 70, 80, 90, 95.
Nie była jeszcze uruchamiana w polu.

---

## 4. Reguły nienaruszalne

Każda z nich powstała po awarii. Złamanie którejkolwiek daje szkodę na
maszynie, nie tylko brzydki kod.

### 4.1 Krok wchodzi wyłącznie z własnego `CASE`

Flagi `xNewStep` i `xAdvance` liczą się **na początku akcji**. Jeżeli inna
maszyna stanu wpisze numer kroku **po** tym miejscu, krok wykona się jeszcze
w tym samym cyklu — ze **starą** flagą `xAdvance`, odziedziczoną po kroku 0,
gdzie czasówka dawno wybiła. Krok przeskoczy natychmiast.

Tak zginął przejazd st.5 → st.6: krok 180 trwał **jeden cykl zadania**,
napęd 5 dostawał żądanie na 10 ms.

**Rozwiązanie w kodzie:** żaden tor nie wpisuje numeru kroku innemu torowi.
Zgłasza żądanie (`xOutStart`, `xOut2Start`, `xOut3Start`), a tor podnosi je
**sam, w swoim kroku 0**.

### 4.2 „Już jestem u celu" nie jest powodem do czekania

Uzbrojenie czujnika (`xArmed`) wymaga, żeby czujnik **najpierw zgasł**.
Jeżeli paleta już tam stoi, warunek nigdy się nie spełni. Każdy krok
kończony czujnikiem musi rozpoznawać sytuację „zasłonięty na wejściu
w krok" i traktować ją jako dojazd, a nie jako powód do czekania.

Ta pułapka wystąpiła **cztery razy**: enkoder desztaplarki, IN2 na stacji 3,
IN3 na stacji 4, IN5 na stacji 7.

### 4.3 Nie wolno jechać w zajęte miejsce

Zasłonięty czujnik przy nieuzbrojonym kroku znaczy **cudza paleta**.
Napędy muszą wtedy stać:

```
IF NOT xPal_St07 OR xOutArmed THEN
    axRunReq[6]  := TRUE;
    axRunReq[11] := TRUE;
END_IF
```

Bez tego transporter pchał paletę w tę stojącą aż do zderzenia i przy okazji
wykładał falownik. Reguła obowiązuje w krokach 200 (IN5), 210 (IN7),
270 (IN10).

### 4.4 Nic nie może wisieć w powietrzu podczas czekania

Bramka cyklu desztaplarki stała kiedyś w kroku 60 — na górze, ze stosem na
szczękach. Sześć palet wisiało na pneumatycznym chwycie przez cały cykl
stacji 5, kilkadziesiąt sekund zamiast kilku. Stos spadł.

**Bramka stoi w kroku 85**: wózek na dole, stos oparty o transporter,
szczęki otwarte, hamulec założony.

Krok 60 czeka **tylko** na IN4 i to musi być krótkie oczekiwanie. IN4 pilnuje
też, żeby stos nie zjechał na paletę, która jeszcze nie wyjechała.

### 4.5 Zatrzask kasuj zboczem, nie poziomem

```
IF nOut3Step >= 240 THEN ...          <- ŹLE, prawdziwe przez całą trasę
IF xOut3NewStep AND (nOut3Step = 240) THEN ...   <- dobrze
```

Reguły po `CASE` wykonują się co cykl. Warunek poziomowy gasił zatrzask
w tym samym cyklu, w którym następna paleta go zapalała.

### 4.6 Odliczaj od stanu, nie od numeru kroku

```
tonSt08Drop(IN := (nOut2Step = 215), ...)   <- ŹLE
tonSt08Drop(IN := xSt08_AtStation, ...)     <- dobrze
```

Krok 215 trwa `tFeedSt08Stop` = 740 ms. Przy `tSt08_DropDelay` = 830 ms timer
nigdy nie dobiegał do końca — zerował się przy przejściu do kroku 218.
Dwie czasówki od tego samego czujnika muszą być naprawdę niezależne.

### 4.7 Metody napędu wołamy na zboczu

`M_Start` co cykl psuje zabezpieczenie bloku (przy blokadzie sam kasuje
żądanie ruchu). Pamięć zbocza `axRunOld` trzymamy wyzerowaną w czasie
blokady, żeby po ustąpieniu przyczyny powstało **jedno** nowe zbocze.

### 4.8 ST nie gwarantuje skrócenia obliczeń w `AND`

`(n > 0) AND arr[n]` **czyta `arr[0]`**. To wywaliło runtime
(„target is in invalid state"). Indeksuj zawsze zmienną z pętli.

### 4.9 Wartości domyślne a Online Change

TwinCAT przy Online Change **nie reinicjalizuje** istniejących zmiennych.
Zmiana wartości początkowej w deklaracji **nie zmieni** wartości na
sterowniku — potrzebne pełne pobranie projektu. To samo dotyczy zmiennych
nieulotnych.

---

## 5. Osie krzywek — `FB_CamAxis`

- Enkoder **narastający, nie zeruje się** przy resecie ani pobraniu projektu.
  Blok sprowadza go modulo 65536 → `diPos`.
- **Korba jedzie tylko do przodu.** Nigdy „najkrótszą drogą" po okręgu —
  kazałaby cofać podniesiony stos.
- Pozycja narastająca `diAccum` służy do wszystkich porównań; ujemny uchyb
  znaczy „cel przejechany" i kończy ruch natychmiast.
- `xInPos` jest **zatrzaskiem** — silnik hamuje rampą i przejeżdża cel.
- Hamulec: `TRUE` = rozłączony. `tCamBrakeHold` = 0,7 s jest **świadomie**
  krótsze niż rampa 1 s. Nie wydłużać bez rozmowy.
- Dwa czuwaki: `xNoDrvAck` (falownik nie potwierdza pracy) i `xStall`
  (falownik pracuje, enkoder stoi).
- **Szczęki otwierają się natychmiast w kroku 0, także na górze.** To jest
  świadomy wybór Karola: lepiej żeby palety spadły, niż żeby silnik 1000 Nm
  przeorał szczękami po stosie. Nie dodawać „zjazdu trzymając" — było
  zrobione i zostało cofnięte.

### Pozycje — otwarty dług techniczny

`ST_StackCfg` ma **wpisane na sztywno** `diPosBottom = 0`,
`diPosMiddle = 16000`, `diPosTop = 24000`. Te liczby są prawdziwe **tylko
wtedy, gdy enkoder został zbazowany**, bo modulo-zero enkodera nie ma
żadnego związku z dolnym położeniem korby.

Karol **bazuje desztaplarkę ręcznie przed startem** i świadomie odłożył
przebudowę. Mechanizm uczenia istnieje i zapisuje właściwą wartość
(`TEACH_DE_BOTTOM/MIDDLE/TOP` → `fbCamDestack.diPos` → nastawy nieulotne).

Wada projektowa do naprawienia kiedyś: bramka `xDeCfgOK` sprawdza tylko, czy
trzy punkty są od siebie oddalone o `diCamMinSpan`. 0/16000/24000 przechodzą
ten test śpiewająco, więc bramka **nie odróżnia „nauczone" od „wymyślone"**.
Propozycja: wyrzucić wartości domyślne (zostawić zera, żeby maszyna odmówiła
startu) i dodać `xTaught`, ustawiany przez uczenie.

Do sprawdzenia: `diDeCycleCounts` wychodziło 65505 zamiast 65536. Jeśli to
nie błąd pomiaru dojazdu, nauczone wartości będą odpływać ~31 impulsów na
obrót.

---

## 6. Nastawy

**Nie kopiuj wartości z tego pliku.** Karol reguluje je online i zapisuje
projekt. Zawsze czytaj aktualne z `MAIN.TcPOU`. Poniżej tylko po to, żeby
wiedzieć, co istnieje i za co odpowiada.

| zmienna | co odmierza |
|---|---|
| `tSt04_EntryToPress` | IN3 → opuszczenie docisków, stacja 4 |
| `tSt04_UpToLo` | górne rolki → dolne rolki |
| `tSt04_StopDelay` | IN4 → stop, stacja 4 |
| `tFeedSt03Stop` | dobieg po IN2, stacja 3 |
| `tFeedToSt05` | długość kroku 80 (st.4 → st.5) |
| `tSt05_Push` | jak długo napędy 4 i 5 pchają paletę do blokady |
| `tSt05_Settle` | paleta na blokadzie → start mechaniki |
| `tCylTime` | **wspólna** dla ośmiu ruchów siłowników stacji 5 **oraz** dla rolek 8/10 i odstępu przed ruszeniem transportera |
| `tFeed5to6` | st.5 → st.6 (brak czujnika na 6) |
| `tFeedSt08Stop` | dobieg po IN7 — zatrzymanie falownika |
| `tSt08_DropDelay` | dobieg po IN7 — **opuszczenie rolek** pod paletę NOK |
| `tFeed9Chain` | łańcuch st.8 → st.10 |
| `tFeed10to14`, `tFeed14to15` | przejazdy buforów odrzutu |
| `tFeedSt16Stop` | dobieg po IN10 |
| `tSt16_Clear` | zgaśnięcie IN10 → stacja uznana za pustą |
| `tDeGripDelay` | zaciśnięcie hamulca → chwyt szczęk |
| `tCamBrakeHold` | zwłoka zacisku hamulca krzywki |
| `lrTestFreq`, `lrCamFreq` | częstotliwości bazowe |
| `alrDriveFreq[1..20]` | własna częstotliwość napędu (0 = użyj `lrTestFreq`) |

`tCylTime` jest **przeciążona** — obsługuje i szczęki, i odstęp przed
ruszeniem transportera stacji 5. Skrócenie jej dla szczęk skróciło też czas
na opuszczenie blokady. Warto ją kiedyś rozbić.

**Bity operatora w MAIN:** `START_TEST`, `START_FEED`, `START_DESTACK`,
`START_STACK`, `RESET_CYCLE`, `RESET_CAM`, `xCmdResetDrives`,
`xSt01_StackReady`, `xDe_PalletReleased`, `xSt08_PalletNOK`,
`xSt04_RollRev`, `JOG_DESTACK_FWD/REV`, `JOG_STACK_FWD/REV`,
`TEACH_DE_*`, `TEACH_ST_*`.

---

## 7. Katalog znalezionych błędów

Wzorce, nie ciekawostki — każdy z nich może wrócić w innym miejscu.

| objaw | przyczyna |
|---|---|
| krok wisi w nieskończoność | czujnik już zasłonięty, uzbrojenie nigdy nie powstaje (4.2) |
| krok trwa jeden cykl zadania | numer kroku wpisany z zewnątrz, stara flaga `xAdvance` (4.1) |
| napęd nie startuje mimo żądania | zbocze `M_Start` skonsumowane, albo blokada załączenia falownika |
| napęd bez błędu i bez ruchu | Switch-on inhibit — trzeba wysłać 047E przed 047F |
| falownik w przeciążeniu | transporter pracuje w zaporę (blokada, korek, zderzenie) |
| paleta wjeżdża w stojącą | brak warunku „nie jedź w zajęte" (4.3) |
| funkcja działa dla 1. palety, nie działa dla kolejnych | zatrzask kasowany poziomem (4.5) |
| czasówka nigdy nie dobiega końca | odliczanie na numerze kroku krótszego niż nastawa (4.6) |
| stos spada z wysokości | coś czeka, trzymając ciężar (4.4) |
| runtime się wywala | indeks tablicy poza zakresem, brak skróconego `AND` (4.8) |
| nastawa nie działa mimo zmiany w deklaracji | Online Change nie reinicjalizuje (4.9) |
| pozycje krzywki kompletnie złe | enkoder nie zbazowany, nastawy 0/16000/24000 są fikcją (§5) |

**Hipotezy, które okazały się fałszywe** — nie wracaj do nich bez nowych
danych:

- reguła nadrzędna `nHeld <= 0` jako przyczyna upuszczenia stosu
  (zmierzone: `nHeld` = 6, reguła nie zadziałała),
- enkoder jako niesprawny lub gubiący pozycję (jest narastający i stabilny,
  modulo liczone poprawnie),
- „koniec obrotu = 65536" jako pewnik (zmierzone 65505),
- czujnik stacji 6 (nie ma go — INPUTS[5] to stacja 7, potwierdzone).

---

## 8. Stan na dziś

**Działa:**

- dowóz stosu ze stacji 1 na 3,
- desztaplowanie — cykl mechanicznie poprawny,
- stacja 4: test ściskania z dociskami,
- stacja 5: pełny cykl rozrywania,
- transport 5 → 6 → 7 → 8 → łańcuch → 10 → 14 → 15 → 16,
- buforowanie: kilka palet naraz w obiegu,
- posadzenie palety NOK na łańcuchu (`tSt08_DropDelay`).

**Nie działa / niedokończone:**

- **DESZTAPLARKA — problem otwarty.** Ostatni objaw: zrzuciła palety
  i zrobiła kolizję. Nie znam przyczyny.
- rolki dociskowe stacji 4 (napęd 3) — wyłączone, brak dobranej
  częstotliwości,
- sztaplarka (stacja 11) — nieuruchamiana, polaryzacja IN8 niesprawdzona,
- klasyfikacja OK/NOK — nie istnieje, `xSt08_PalletNOK` jest na sztywno TRUE,
- `xEtherCAT_OK` zaszyte TRUE — watchdog komunikacji nie działa,
- czasówki przejazdów bez czujników (`tFeed5to6`, `tFeed9Chain`,
  `tFeed10to14`, `tFeed14to15`) to wartości dobrane obserwacyjnie.

---

## 9. Desztaplarka — otwarty problem

To jest **priorytet** nowego wątku.

**Objaw:** zrzuciła palety, kolizja. Wcześniej podobnie: podała 5 palet
poprawnie, przy 6. otworzyła szczęki na wysokości.

**Co zostało wykluczone pomiarem:**

- reguła nadrzędna `nHeld <= 0` w krokach 50–70 — w chwili awarii
  `nHeld` = 6, `nRemaining` = 7, `nStackSize` = 12, więc **nie zadziałała**,
- cewki szczęk są przepisywane co cykl poza `CASE`, więc krok, który ich nie
  pisze, nie może ich zgubić.

**Co pozostaje do sprawdzenia — w tej kolejności:**

1. **Czy `GVL.OUTPUTS[14]` (zamykanie szczęk) było TRUE w chwili
   upuszczenia?** Jeśli tak — program kazał trzymać, a szczęki puściły:
   problem pneumatyki albo mechaniki, nie kodu. To jest pytanie
   rozstrzygające i najtańsze.
2. Wartości w chwili awarii: `nDeStep`, `sDePhase`, `fbCamDestack.diPos`,
   `.diAccum`, `.diRemain`, `diDeTarget`, `xDeJawsClosed`,
   `GVL_PERSIST.St03.Mem.nHeld` i `.nRemaining`.
3. Czy krok 70 (zjazd na dół) nie kończy się za wcześnie —
   `fbCamDestack.xInPos` zapalony przy złej pozycji oznaczałby, że krok 80
   otwiera szczęki na wysokości. **To jest najbardziej prawdopodobna
   ścieżka do „upuszczenia z góry"** i nie została jeszcze zweryfikowana.
4. Czy pozycje w `St03.Cfg` odpowiadają rzeczywistemu zbazowaniu enkodera
   w tym konkretnym uruchomieniu (§5).

**Czego nie robić:** nie dodawać „zjazdu z zamkniętymi szczękami" jako
zabezpieczenia — Karol to odrzucił świadomie.

---

## 10. Narzędzie: symulacja skanowa

Dwa razy znalazła błąd, którego czytanie kodu nie wychwyciło. Schemat:

- cykl 10 ms, klasa `TON` odwzorowująca zachowanie TwinCAT,
- **wierna kolejność w cyklu**: kasowanie `axRunReq` → silnik kroków
  (flagi `xNewStep`, `xAdvance` liczone **na początku**) → wartości domyślne
  → `CASE` kolejnych torów → warunki nadrzędne → logika zboczy `M_Start`,
- logowanie tylko zmian stanu (numer kroku, żądania napędów, zatrzaski),
- porównanie dwóch wariantów kodu obok siebie (przed/po poprawce).

Klucz: **odwzorować kolejność i to, że flagi są liczone raz na cykl**.
Właśnie tam siedziały oba błędy.
