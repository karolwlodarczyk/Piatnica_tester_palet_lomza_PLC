# Obserwator stanu maszyny — log CSV na dysku sterownika

Dodane 11 września 2026. Trzy pliki:

| plik | co |
|---|---|
| `POUs\POUs\FB\FB_CsvLogger.TcPOU` | blok zapisu: bufor wiersza, kolejka, `FB_FileOpen/Write/Close` po ADS, nazwa pliku z zegara CX |
| `POUs\MAIN.TcPOU` — `ACT_Logger` | **kiedy** pisać: takt `tLogPeriod` (1 s) + zdarzenia |
| `POUs\MAIN.TcPOU` — `ACT_LogRow` | **co** pisać: jedna lista kolumn dla nagłówka i danych |

`ACT_Logger()` jest wołane jako **ostatnia** akcja cyklu, po `ACT_Outputs`,
więc w pliku jest to, co naprawdę poszło na wyjścia. Logger tylko czyta
zmienne procesu; nie ma prawa niczego zmienić. Kolejność pozostałych akcji
bez zmian.

## Zanim pierwszy raz uruchomisz

1. Katalog `C:\TesterPalet\log\` blok zakłada sam przy pierwszym
   starcie (`FB_CreateDir`, wynik w `fbLog.nMkDirErrId`). Inny katalog →
   zmień online `MAIN.fbLog.sDir`, z końcowym `\`.
2. Pobierz projekt (nowy blok, nowe zmienne w `MAIN` — Online Change może
   nie wystarczyć; pełne pobranie jest bezpieczniejsze).
3. Po starcie sprawdź online `MAIN.fbLog`:
   - `sFileName` — pełna ścieżka bieżącego pliku,
   - `nFlushes` rośnie mniej więcej co sekundę,
   - `nErrors = 0`. Jeśli `nLastErrId = 1804` (`0x70C`) — ścieżka nie
     istnieje. `sLastErrWhere` mówi, która operacja padła.

Projekt wymaga biblioteki `Tc2_Utilities` (`NT_GetTime`, `FB_CreateDir`) —
dopisana do `.plcproj`; jest w każdej instalacji TwinCAT.

## Kiedy powstaje nowy plik

- start PLC,
- każde `RESET_CYCLE`,
- zbocze `MAIN.xLogNewFile` (sam się zdejmuje).

Nazwa: `tp_RRRRMMDD_GGMMSS.csv`. Bez zegara (błąd `NT_GetTime`):
`tp_noclock_N.csv`.

## Kiedy powstaje wiersz

- co `tLogPeriod` (kolumna `why = tick`),
- natychmiast, gdy zmieni się: numer któregokolwiek kroku (`step`),
  którekolwiek `INPUTS[1..10]` (`in`), żądanie któregokolwiek napędu
  (`drv`), pojawi się błąd falownika (`FAULT`), zmieni się bit operatora,
  uzgodnienie, szczęki, `xInPos`, czuwak, hamulec, `xSTO`, `xAir` (`bit`),
  albo `|diStep|` którejś osi przekroczy `diLogEncJump` = 2000 (`ENCJUMP`).
- Najwyżej **jeden wiersz na cykl**. Przy przepełnieniu kolejki wiersz
  przepada i rośnie `log_dropped` (jest w każdym wierszu).

## Jak to czytać

Po procesie skopiuj plik z CX do `docs\logs\` w repo. Analiza:

```
python docs\tools\analyze_log.py docs\logs\tp_20260911_101500.csv
python docs\tools\analyze_log.py plik.csv --around 123456 --win 5000
python docs\tools\analyze_log.py plik.csv --cols nDeStep de_pos de_inPos de_jawsClosed out14
```

Pierwsze wywołanie daje oś czasu kroków z czasami trwania, zbocza
czujników, żądania napędów, błędy, skoki enkodera i zmiany bitów.
Drugie wypisuje wiersze wokół podanego `t_ms`. Trzecie — tylko zmiany
wybranych kolumn.

## Kolumny (skrót)

`t_ms` od otwarcia pliku, `clock` zegar CX, `why`, `nCycles` ·
kroki `nDeStep … nOut3Step` + `sDePhase/sFeedPhase/sOutPhase` ·
bity `START_*`, `RESET_*`, uzgodnienia · `xSTO`, `xAir`, `xResetCmd` ·
`in1..in10` surowe + `xPal_*` · desztaplarka `de_*` (`nHeld`, `nRemaining`,
`raw`, `pos`, `accum`, `remain`, `step`, `target`, `inPos`, `runReq`,
`brakeRel`, `jawsClosed`, `stall`, …) · sztaplarka `st_*` ·
`out1..out17`, `festo1/2` (maski 16-bit hex: bit = (i-1)·2+(j-1)) ·
napędy `dN_req/run/flt/sw/st/hz` dla N = 1..19 · `log_dropped`,
`log_errors`, `log_lastErr`.

## Dodanie kolumny

Jedna linijka w `ACT_LogRow`, np.
`fbLog.M_Int('nazwa', zmienna);`. Nagłówek robi się sam z tej samej
linijki. Metody: `M_Bool`, `M_Int` (DINT), `M_UInt` (UDINT), `M_Hex`
(WORD), `M_Real` (1 miejsce po kropce), `M_Str`, `M_Clock`.

## Nastawy online

`MAIN.xLogEnable` (FALSE = przestań zbierać, plik zostaje),
`MAIN.tLogPeriod`, `MAIN.diLogEncJump`, `MAIN.fbLog.sDir`,
`MAIN.fbLog.tFlushMin` (najkrótszy odstęp między zrzutami na dysk, 500 ms).
