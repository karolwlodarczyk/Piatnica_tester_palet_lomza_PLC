# Reguły projektu — Tester palet (TwinCAT 3)

## Co jest czym

- Właściwy kod: `Tester_Palet_2\Ponowne_skanowanie`, projekt PLC
  `TC3_Tester_Palet`, projekt safety `TC3_Test_Palet`.
- `oprogramowanie\TC3_Nord_SK550P` — **ignorować**. Luźny przykład obsługi
  falownika NORD, nie część aplikacji. Nie wyciągać z niego wzorców.
- Założenia maszyny: `docs\ZALOZENIA.md`.
- Runtime na osobnym sterowniku (CX), XAE na laptopie.

## Warstwy

```
MAIN
 └─ warstwa maszyny   tryby, reset, alarmy, routing OK/NOK
     └─ warstwa stacji   FB_* dziedziczące z FB_TransportNodeBase
         └─ warstwa napędów   FB_NordSK550PP  (ARRAY[1..20])
```

**Kolejność wywołań w MAIN jest częścią kontraktu:** najpierw stacje
(wołają metody bloków napędu), potem napędy. Odwrotna kolejność opóźnia
każdą komendę o cykl.

## Architektura warstwy transportu

- `FB_TransportNodeBase` — cała wspólna logika: pamięć obecności, weryfikacja
  względem czujników, watchdogi, wznawianie przerwanych przejazdów,
  uzgadnianie przejazdu z sąsiadem, tryb ręczny.
- Klasa pochodna dostarcza tylko **szew**: wypełnia wejścia czujników
  i napędu, woła `SUPER^()`, przepisuje `xDrvRun / xDrvRev / lrDrvFreq`
  na swój aktuator.
- Stacje technologiczne nadpisują `M_OperationRequired`, `M_OperationCycle`
  i — jeżeli pracują na jadącej palecie — `M_TravelCycle`. Nic więcej.
  Jeżeli stacja potrzebuje zmienić przebieg transportu, to znak, że brakuje
  haka w klasie bazowej, a nie powód do kopiowania sekwencji.
- Dwa rodzaje stacji technologicznych: **na postoju** (5, 3, 7, 11) robią
  swoje w `NODE_BUSY` po zatrzymaniu palety, **na przejeździe** (4, 6)
  w `M_TravelCycle` w trakcie `NODE_INFEED`. Te drugie mają
  `Cfg.xNokOnInterrupt := TRUE`, bo przerwanego badania na jadącej palecie
  nie da się odtworzyć.
- Sąsiedztwo przez wskaźniki (`M_Link`, `M_SetNext`). Stacja 8 przełącza
  następnika w locie: OK → 11, NOK → 9.

## Zmienne nieulotne

- Wszystkie w `GVL_PERSIST`, nigdy wewnątrz instancji FB.
- `Cfg` — nastawy operatora, **kod ich nie zapisuje**.
- `Mem` — obraz stanu maszyny; każda zmiana ustawia `xPersistDirty`.
- Wartości domyślne z deklaracji obowiązują tylko przy pierwszym pobraniu
  projektu. Zmiana domyślnej w kodzie nie zmieni nastawy na sterowniku.

## Diagnostyka — reguła nadrzędna

Kod nie ma prawa „stanąć gdzieś w środku". Każdy postój ma **dokładnie
jedną** przyczyną w `eWait`:

- warunki sprawdzamy w stałej kolejności i wychodzimy na pierwszym
  niespełnionym (`RETURN`), zamiast zagnieżdżać `IF`,
- odmowę sąsiada przepisujemy z jego `M_WhyCannotAccept()`, żeby na HMI
  było widać nie „czeka", tylko czego brakuje i po której stronie,
- pierwszy alarm zostaje, kolejne go nie nadpisują — operator ma widzieć
  przyczynę, nie skutek.

Maksymalna głębokość zagnieżdżenia `IF` w nowym kodzie: **2**.

## Styl

- Komentarze po polsku, bez polskich znaków (edytor TC3).
- Prefiksy: `x` BOOL, `n` INT, `w` UINT/WORD, `lr` LREAL, `t` TIME,
  `e` ENUM, `st` STRUCT, `fb` instancja, `p` wskaźnik, `a` tablica,
  `c` stała, `M_` metoda.
- Enumy z jawnymi wartościami — numery trafiają na HMI.
- Bez magicznych liczb w kodzie sekwencji: czasy i progi wyłącznie
  z `GVL_PERSIST`.
- Sekcje oddzielane komentarzem blokowym, jak w `FB_NordSK550PP`.

## Napędy

- `FB_NordSK550PP` steruje **wyłącznie częstotliwością**. Rampy siedzą
  w falowniku (P102/P103/P108). PLC ich nie dotyka.
- Metody napędu wołamy **na zboczu**, nie co cykl. Blok przy blokadzie
  sam kasuje żądanie ruchu i napęd nie może ruszyć sam po ustąpieniu
  przyczyny — wołanie `M_Start` co cykl psuje to zabezpieczenie.
- `lrFmax` w bloku **musi** być równe P105 w falowniku.
- Do zrobienia: podpiąć realny `xEtherCAT_OK` (`WcState` / `InfoData.State`),
  dziś jest zaszyte `TRUE` i watchdog komunikacji nie działa.

## Osie krzywek (desztaplarka st.3, sztaplarka st.11)

- `FB_CamAxis` obsługuje obie. Enkoder **single-turn 0..65535**, zero na
  pozycji dolnej, pozycja liczona modulo — przekręcenie samo sprowadza ją
  do zera.
- **Korba jedzie tylko do przodu.** Jeden cykl maszyny to dokładnie jeden
  obrót (65536 impulsów). Nigdy nie liczyć „najkrótszej drogi" po okręgu —
  kazałaby cofać podniesiony stos. `diMaxReverse` to korekta przestrzelenia,
  nie sposób jazdy.
- Każda wysokość występuje **dwa razy** na obrót: raz na podjeździe, raz na
  zjeździe. Punkt środkowy sztaplarki (49536) leży po stronie zjazdu i jest
  lustrem punktu desztaplarki (16000).
- `xInPos` jest **zatrzaskiem**. Silnik hamuje rampą i przejeżdża cel, a
  wózek po zaciśnięciu hamulca jeszcze się osuwa — porównanie na żywo nigdy
  by nie trafiło w okno i krok wisiałby w nieskończoność.
- **Hamulec:** `TRUE` = rozłączony, stan bez zasilania trzyma wózek.
  Schodzi razem z komendą dla falownika (`tBrakeReleaseLead` = 0) i zaciska
  się `tBrakeHold` = 0,7 s po jej zdjęciu — czyli **przed końcem rampy 1 s**.
  To jest wybór świadomy: lepiej dołożyć hamulcowi ten kawałek pracy, niż
  puścić wózek wolno i pozwolić mu opaść. Nie wydłużać bez rozmowy.
- Dwa czuwaki, każdy o innej wymowie: `xNoDrvAck` — falownik nie potwierdza
  pracy (problem napędu), `xStall` bez niego — falownik pracuje, a enkoder
  stoi (mechanika albo enkoder).

## Bezpieczeństwo

- `GVL_SAFETY.xSTO` jest jedynym miejscem, w którym interpretujemy
  polaryzację sygnału z TwinSAFE. Jeżeli okaże się odwrotna — negujemy
  tam, nie w każdej stacji.
- Zanik STO w trakcie przejazdu jest zapamiętywany jako przerwany ruch,
  nie jako błąd stacji.
