# Podsumowanie wątku „Program do testera palet" (9–11 września 2026)

Plik do zasiewu nowego wątku (Claude Code). Czytaj razem z
`docs\KONTEKST_DLA_NOWEGO_WATKU.md` (reguły pracy, struktura programu,
katalog błędów) — tamten dokument nadal obowiązuje w całości. Tu jest to,
co doszło po nim.

Repo: `C:\Users\karol\Desktop\Tester palet aplikacja`
Projekt PLC: `Tester_Palet_2\Ponowne_skanowanie\Ponowne_skanowanie\TC3_Tester_Palet`
Sterownik: CX-A8FE60, Windows 10 Enterprise LTSC. XAE na laptopie.

---

## 1. Co zostało zrobione (pliki w repo)

| plik | co |
|---|---|
| `docs\ANALIZA_DESZTAPLARKA_UPADEK_STOSU.md` | analiza upadków stosu: trzy hipotezy, symulacja skanowa, §7 potwierdzenie z logu |
| `docs\sim_cam_glitch.py` | symulacja skanowa `FB_CamAxis` + krok 70 (cykl 10 ms); pokazuje, że jedna fałszywa próbka enkodera zatrzaskuje `xInPos` |
| `POUs\POUs\FB\FB_CsvLogger.TcPOU` | **nowy** blok: logger CSV na dysk CX (bufor bajtowy, kolejka, `FB_FileOpen/Write/Close`, `NT_GetTime`, `FB_CreateDir`) |
| `POUs\MAIN.TcPOU` | dopisane: deklaracje loggera w `VAR`, akcje `ACT_Logger` (kiedy pisać) i `ACT_LogRow` (co pisać), wywołanie `ACT_Logger();` jako **ostatnie** w cyklu, po `ACT_Outputs` |
| `TC3_Tester_Palet.plcproj` | dopisany `FB_CsvLogger.TcPOU` i biblioteka **`Tc2_Utilities`** |
| `docs\LOGGER.md` | instrukcja loggera: katalog, nowy plik, zdarzenia, kolumny, jak dodać kolumnę |
| `docs\tools\analyze_log.py` | analizator CSV: oś czasu kroków, zbocza czujników, żądania napędów, błędy, skoki enkodera; `--around t_ms`, `--cols ...` |
| `docs\logs\tp_20260911_114649.csv` | pierwszy log z maszyny, z incydentem o 11:50:45 |

Logger **działa na maszynie** (skompilował się po dodaniu `Tc2_Utilities`).
Plik: `C:\TesterPalet\log\tp_RRRRMMDD_GGMMSS.csv`, nowy na start PLC,
`RESET_CYCLE` i `MAIN.xLogNewFile`. Wiersz co 1 s plus na zdarzenie
(zmiana kroku, czujnika, żądania napędu, błąd falownika, bit operatora,
szczęki, `|diStep| > 2000`). ~250 kolumn. Karol kopiuje plik po procesie
do `docs\logs\`, analiza skryptem.

Sekwencja, nastawy, kolejność akcji w `MAIN` — **bez zmian**.

---

## 2. Przyczyna upadków stosu — USTALONA

Objaw: po 3, 5, 7 paletach szczęki desztaplarki otwierają się z ładunkiem,
stos spada, korba jedzie w dziwne miejsce, szczęki zamykają się w bok palety.

Log z 11.09 (t = 235,9 s od otwarcia pliku, 11:50:45):

- wózek na górze, krok 60, `de_raw` = 155 087 (`de_pos` 24015), stos na szczękach;
- **`de_raw` spada do 0 w jednym cyklu** i zostaje 0;
- IN4 → krok 70: cel liczony z `de_pos = 0` → droga 0 → `xInPos` natychmiast;
- krok 80: hamulec już założony → **szczęki otwarte na górze**; stos spada;
- enkoder potem pokazuje `2147482878, 24, 20, 17` — czyli **wyzerowany na
  pozycji górnej** (drgnięcie korby po upadku);
- krok 85 → 20 „na środek" liczony od fałszywego zera → korba w złym miejscu.

Testy Karola: zerwanie kabla IO-Link i zdjęcie zasilania enkodera **nie
zmieniają** wskazania (PLC trzyma ostatnią wartość; po powrocie zasilania
enkoder pamięta zero i liczy poprawnie). Czyli komunikacja ani Data
Storage nie są winne — enkoder **dostał komendę zerowania**.

Źródło (parametry Posital UCD-LK w `.tsproj`, port 3 i 4 EL6224):

| parametr | wartość | znaczenie |
|---|---|---|
| `Connector Pin 2 DI/DO Mode` | 14 (0x0E) = DI | pin 2 złącza M12 jest wejściem |
| `Connector Pin 2 DI Mode` | 0 = Reset | impuls na pinie 2 **zeruje pozycję** |

EL6224 jest 3-przewodowy; pin 2 enkodera wisi w kablu obok przewodów
falowników → zakłóceniowy impuls = natychmiastowe zero. Losowo, bez śladu
w komunikacji. To tłumaczy wszystkie incydenty.

**Do zrobienia przez Karola (sprzęt/parametry):**
1. Port 3 i 4 → Parameters → `Connector Pin 2 DI/DO Mode` := **0x21 = DO
   (CAM 1.2)**. Zapisać, wyłączyć/włączyć zasilanie enkodera, odczytać
   ponownie; jeśli wraca 14 — System Command 0x05 `ParamDownloadStore`.
2. Sprawdzić żyłę pinu 2 w kablu enkodera, zaizolować z obu stron.
3. Ręczne bazowanie dalej komendą po IO-Link (`0xE4` zero / `0xD0` preset).

Wpisy Startup `0x8008/0x8018/0x8028/0x8038` (CoE „Object does not exist")
są kosmetyczne — firmware EL6224 ich nie zna; można usunąć.

---

## 3. Drugi wniosek z logu — `tSt08_DropDelay` jest wyprzedzana

Pytanie Karola: czy `tSt08_DropDelay` (830 ms) nie gryzie się z czasówką
zatrzymania napędu (`tFeedSt08Stop`, 740 ms), bo „powyżej sekundy nie
działa".

Ustalenie: sama `tonSt08Drop` jest poprawna (liczy od `xSt08_AtStation`).
Ale krok 218 toru B2 oddaje paletę torowi B3 **natychmiast**, gdy
`nOut3Step = 0`, a krok 220 toru B3 **sam opuszcza rolki 8 i 10**
(`xFeedRoll08Up := FALSE`) bez pytania czasówki. Przy wolnym łańcuchu rolki
schodzą po `tFeedSt08Stop` + 2 cykle ≈ 0,76 s, niezależnie od
`tSt08_DropDelay`, jeśli jest większa. Poniżej 0,74 s nastawa działa.

**Propozycja (nie wprowadzona, czeka na zgodę):** w kroku 218 oddawać paletę
torowi B3 dopiero gdy `NOT xSt08_PalletNOK OR xSt08_RollDown`. Efekt:
rolki 8 schodzą dokładnie `tSt08_DropDelay` po IN7, B3 rusza po tym.
Jedna linijka.

---

## 4. Zabezpieczenia w kodzie — zaproponowane, NIE wprowadzone

Kolejność po usunięciu przyczyny sprzętowej (§2), każde osobno:

1. **`FB_CamAxis` — kontrola wiarygodności próbki**: skok `|diStep|` większy
   niż fizycznie możliwy w cyklu → próbkę odrzucić (`diPosPrev` bez zmian,
   licznik); po ~20 odrzuconych z rzędu przyjąć nową wartość, ale zapalić
   `xEncJump` i potraktować jak `xStall` — oś stoi, hamulec założony, `CASE`
   sekwencji nie wykonuje się, więc `xDeJawsClosed` zostaje jak było
   (szczęki nie puszczają). Wyjście przez `RESET_CAM`. To zatrzymałoby
   maszynę o 235,9 s ze stosem bezpiecznie na górze.
2. **`FB_CamAxis` — hamulec natychmiast przy utracie napędu**: `xRunReq` i
   (`axDrvFault` lub `NOT xDrvRunning` po tym, jak był TRUE, lub `NOT xSTO`)
   → `xMoveWanted := FALSE` i ominąć `tBrakeHold`. Dziś okno swobodnego
   opadania ≈ 2,2 s (`tDrvAck` 1,5 s + `tBrakeHold` 0,7 s).
3. `xAutoResetOnStart := FALSE` na czas diagnozy (błąd falownika ma przeżyć
   do odczytu).
4. Podlinkowanie `State Ch3/Ch4` i `WcState` EL6224 do PLC — niższy
   priorytet, bo zerwanie komunikacji zamraża wartość (łapie `xStall`).
5. Drobne: `Singleturn Resolution = 65535` vs `MOD 65536` w `FB_CamAxis`
   (dryf 1 impuls/obrót); `Total Resolution = 2147482880` (przejście przez
   0 wstecz daje skok 768 w `diPos`); `tDrvAck = 1,5 s` długie.

---

## 5. Odpowiedzi na pytania, które padły (żeby nie szukać ponownie)

- Odstęp „rolki st.5 stają → szczęki ruszają": `(tFeedToSt05 − tSt05_Push)
  + tSt05_Settle` = 0 + 8 s; zamknięcie szczęk jeszcze `tCylTime` później.
  Regulować `tSt05_Settle`, nie `tSt05_Push`.
- Częstotliwość transportera stacji 8: `alrDriveFreq[12]` (0 = `lrTestFreq`
  20 Hz); stacja 6: `alrDriveFreq[6]`; stacja 7: `alrDriveFreq[11]`.
  Napęd czyta częstotliwość przy starcie. Po zmianie prędkości przesuwają
  się czasówki przejazdów bez czujników (`tFeed5to6`) i dobiegi po IN7.
- Zatrzymanie PLC po błędzie: nie trzeba — logger robi otwórz/dopisz/zamknij,
  plik zawsze spójny; przed Stop PLC sprawdzić `fbLog.nState = 0` i
  `nOutLen = 0`. `xLogNewFile` odcina plik incydentu.
- Wizualizacje PLC HMI (`.TcVIS`): potrafię generować XML, ale bez podglądu;
  najpierw Karol robi wzorcową wizualizację z jednym elementem każdego typu,
  ja z niej generuję ekrany skryptem. Nie zaczęte.

---

## 6. Reguły pracy, które obowiązują nadal

- Przed KAŻDĄ edycją pobrać aktualny plik z dysku Karola (mtime!). Karol
  zmienia nastawy online i zapisuje projekt.
- Nastaw czasowych nie zmieniać i nie kopiować z notatek — źródłem prawdy
  jest `MAIN.TcPOU` na dysku.
- Jedna zmiana naraz, z wypisanym oczekiwanym efektem na maszynie.
- Nie zgaduj — zmierz. Teraz jest logger: najpierw log, potem diagnoza.
- Symuluj (cykl 10 ms, wierna kolejność akcji).
- Komentarze po polsku bez polskich znaków; `.TcPOU` = XML, UTF-8 **z BOM**,
  CRLF; po edycji sprawdzić XML, ASCII, bilans `IF/CASE/FOR`.
- Nie dodawać „zjazdu z zamkniętymi szczękami" w kroku 0 — świadoma decyzja.
- Pozycje 0/16000/24000 zostają; Karol bazuje ręcznie; bramka `xDeCfgOK`
  bez zmian do odwołania.
- `oprogramowanie\TC3_Nord_SK550P` ignorować.

---

## 7. Stan na koniec wątku

- Logger: działa, pierwszy log przeanalizowany.
- Przyczyna upadków: zidentyfikowana (pin 2 = Reset), czeka na przestawienie
  parametru i ponowny proces z logiem — jeśli przez kilka stosów nie będzie
  `ENCJUMP` ani zera, temat zamknięty.
- Hipotezy 2.2 (falownik/STO przy zwolnionym hamulcu) i 2.3 (pneumatyka) z
  analizy pozostają warte zabezpieczeń z §4, ale nie są już głównym
  podejrzanym.
- Otwarte decyzje Karola: poprawka kroku 218 (§3), zabezpieczenia §4,
  wizualizacja.
