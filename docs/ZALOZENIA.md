# Tester palet — założenia aplikacji PLC

Dokument roboczy. Źródłem prawdy jest opis maszyny od Karola; tutaj jest on
uporządkowany do postaci, z której powstaje kod. Wszystko oznaczone **[?]**
wymaga rozstrzygnięcia.

---

## 1. Zakres maszyny

Tester palet z jednym wejściem i dwoma wyjściami:

- wyjście **OK** — sztaple po 15 palet (stacja 13),
- wyjście **NOK** — pojedyncze palety (stacja 16).

16 stacji transportowych, 19 falowników NORDAC PRO SK 550P po EtherCAT,
zawory Festo VAEM po IO-Link, przetworniki położenia siłowników Posital
(wartość bezwzględna, DINT) po IO-Link.

---

## 2. Stacje

| Nr | Nazwa | Rola | Falownik |
|----|-------|------|----------|
| 1 | Załadunek stosów | operator wstawia stos 1–15 palet, potwierdza przyciskiem; bufor | 8 |
| 2 | Bufor stosów | wyłącznie bufor między 1 a 3 | 9 |
| 3 | Desztaplarka | rozdziela stos na pojedyncze palety (krzywka) | 10 + krzywka 1 |
| 4 | Test ściskania desek | siłowniki dociskowe góra/dół + rolki dociskowe | 4 + rolki 3 |
| 5 | Test rozrywania | szczęki na dolne deski + 6 siłowników rozrywających + blokada | 5 |
| 6 | Pomiar laserowy | test realizuje urządzenie zewnętrzne | 6 |
| 7 | Etykietowanie | urządzenie zewnętrzne; **palety NOK nie są etykietowane** | 11 |
| 8 | Stacja rozjazdowa | rolki podnoszone; OK → 11, NOK → w dół → 9 | 12 + krzywka 2 **[?]** |
| 9 | Transporter łańcuchowy | poprzeczny, 8 → 10, bez własnych czujników | 7 |
| 10 | Stacja przekierowująca | rolki podnoszone; przyjmuje z 9, wydaje na 14 | 16 |
| 11 | Sztaplarka | buduje stos 15 palet | 13 |
| 12 | Bufor stosów | bufor przed wyjściem OK | 14 |
| 13 | Wyjście OK | operator odbiera stosy po 15 palet | 15 |
| 14 | Bufor odrzutu | pojedyncza paleta | 17 |
| 15 | Bufor odrzutu | pojedyncza paleta | 18 |
| 16 | Odbiór NOK | operator odbiera pojedyncze palety | 19 |

Trasa OK: `1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 11 → 12 → 13`
Trasa NOK: `… → 8 (opuszczenie) → 9 → 10 (podniesienie) → 14 → 15 → 16`

---

## 3. Typy transporterów

**Rolkowy** — dwa czujniki optyczne na końcu, logika odwrócona
(1 = wolne, 0 = coś widać). Obecność w pozycji końcowej = **zero z obu**.
Czujniki są ustawione geometrycznie tak, że widzą pierwszą i ostatnią
kostkę palety; „miganie" kostkami w trakcie przejazdu ignorujemy.

**Łańcuchowy (stacja 9)** — wozi palety w poprzek, nie ma własnych
czujników, korzysta z czujników stacji 8 i 10. Nie jest buforem — paleta
może stać tylko na 8 albo na 10. Przejazd wymaga, żeby oba transportery
rolkowe były **opuszczone**.

**Blokada łańcuch / rolki** — gdy pracuje transporter łańcuchowy, rolki
stacji 8 i 10 są opuszczone i paleta leży na łańcuchu. Kręcenie nimi w tym
czasie szarpałoby paletę z dwóch stron naraz, więc napędy stacji 8 i 10
(falowniki 12 i 16) **nie mają prawa pracować razem z falownikiem 7**.
Stwierdzone na maszynie przy pierwszej próbie ruchu; w kodzie jest to
warunek nadrzędny, sprawdzany niezależnie od sekwencji.

---

## 4. Reguły wspólne transportu

1. Na jednym transporterze może przebywać **jedna** paleta albo stos.
2. Przejazd wymaga zgody obu stron. Jeżeli oddający jest gotowy i
   przyjmujący jest gotowy — **ruszają jednocześnie**.
3. Paleta zawsze jedzie tak daleko, jak może.
4. **Przejazd bez zatrzymania** — jeżeli na węźle nie ma nic do zrobienia,
   a następny czeka, nie zatrzymujemy się na czujnikach.
5. W AUTO transporter jedzie zawsze do przodu. Zmiana kierunku tylko
   w MANUAL. Tryb podawany do transportera z zewnątrz.
6. Każdy czujnik można wyłączyć (uszkodzony). Wyłączenie obu → przejazd
   na czasówkę. Wtedy **poprzednik musi zatrzymać paletę u siebie**, żeby
   punkt startu był powtarzalny.
7. Obecność ładunku trzymana w pamięci nieulotnej. Po każdym ruchu i po
   każdym zatrzymaniu pamięć jest porównywana z czujnikami; rozjazd =
   alarm i decyzja operatora.
8. Watchdog przejazdu (czas nastawiany przez operatora). Przekroczenie =
   stop + alarm + zapamiętanie przerwanego ruchu.
9. Po resecie maszyna **sama próbuje dokończyć** przerwany przejazd
   (liczba prób to nastawa).
10. Awaryjne kasowanie stanu — serwis zabiera paletę ręcznie i przyciskiem
    zgłasza, że węzeł jest pusty.
11. **Przerwanie testu** (grzybek, kurtyna, przeciążenie napędu, zanik
    zasilania). Na stacjach **4 i 6** wynik przerwanego testu jest
    nieważny — paleta idzie na odrzut i nie jest badana ponownie.
    Na pozostałych stacjach można kontynuować albo powtórzyć cykl
    od początku. Sterowane nastawą `Cfg.xNokOnInterrupt` per stacja.

    Powód jest ten sam dla obu: **badanie toczy się na jadącej palecie**.
    Stacja 6 buduje model 3D profilometrami milimetr po milimetrze i
    zatrzymanie wprowadza błąd do skanu. Na stacji 4 rolki dociskają
    w sposób ciągły, a po niekontrolowanym zatrzymaniu rolki górne
    i dolne ruszają z różnymi prędkościami — nie wiadomo, jak daleko
    pojedzie paleta ani czy rolki nie omskną się na jej krawędziach.

    Stacja 5 jest poza regułą: paleta ma wytrzymać ciągły nacisk, więc
    dodatkowa dawka siły po wznowieniu niczego nie zmienia.

### Nastawy operatora na transporter (nieulotne)

częstotliwość AUTO, częstotliwość MANUAL, opóźnienie zatrzymania,
watchdog wjazdu, watchdog wyjazdu, czas przejazdu bez czujników,
czas potwierdzenia zjazdu, czas stabilizacji czujników, włączenie
czujnika 1, włączenie czujnika 2, włączenie stacji, zgoda na przejazd
bez zatrzymania, liczba prób wznowienia.

---

## 5. Reguły wspólne siłowników

Każdy siłownik ma:

- sterowanie cewkami (jedno- lub dwucewkowe; zawór blokady jest
  3-położeniowy — cofnięcie to zdjęcie **obu** wyjść),
- opóźnienie wysterowania zaworu przy wysuwie,
- opóźnienie wysterowania zaworu przy wsuwie,
- watchdog ruchu, **z możliwością wyłączenia dla kierunku bez krańcówki**,
- czasówkę zastępczą: dla każdego kierunku można wyłączyć obserwację
  położenia końcowego i uznać ruch za wykonany po upływie czasu
  (praca z uszkodzonym czujnikiem).

Sprzężenie zwrotne bywa dwojakie: krańcówki (blokada stacji 5, siłownik
szczęk, rolki stacji 8 i 10) albo przetwornik położenia IO-Link o wartości
bezwzględnej (stacja 4 i siłowniki rozrywające stacji 5).

### Bazowanie przetworników

- **Stacja 4** — w MANUAL: wstawić paletę, wysunąć wszystkie siłowniki,
  wyzerować wskazanie wybranego czujnika lub wszystkich naraz. Pozycje
  końcowe („siłownik wycofany") podaje operator z palca i są nieulotne.
- **Stacja 5** — zero na siłowniku **wycofanym**, bez palety.

---

## 6. Stacje technologiczne

### Stacje 3 i 11 — desztaplarka i sztaplarka

Ta sama kinematyka: wózek ze szczękami na falowniku, enkoder absolutny,
**trzy pozycje** wpisywane z palca (automat bazujący dojdzie później):

| Pozycja | Znaczenie |
|---------|-----------|
| `diPosBottom` | wysokość desek **pierwszej** palety od dołu |
| `diPosMiddle` | wysokość desek **drugiej** palety od dołu |
| `diPosTop` | stos uniesiony |

Odległość między nimi to wysokość palety. Kod sprawdza, czy tworzą ciąg
rosnący albo malejący — pomyłka w kolejności wysłałaby wózek w złą stronę.

**Desztaplarka (stacja 3)** — w trakcie wjazdu stosu szczęki są otwarte,
a wózek jedzie na `Middle`. Po potwierdzeniu czujnikami zapisujemy w pamięci
nieulotnej, że stos dojechał, i liczbę palet (`nStackSize`, na razie 15).
Szczęki zamykają się pod drugą paletą od dołu, wózek jedzie na `Top`,
najniższa paleta zostaje na transporterze i wyjeżdża. Po jej zjeździe wózek
schodzi na `Bottom`, szczęki się otwierają i cykl się powtarza.
**Gdy zostaje jedna paleta, nie ma czego chwytać** — wyjeżdża wprost
z transportera.

**Sztaplarka (stacja 11)** — wózek czeka na `Top` z zamkniętymi szczękami.
Paleta nie ma prawa wjechać, dopóki tak nie jest — to warunek przyjęcia
ładunku, nie tylko krok sekwencji. Po wjeździe trzymany stos schodzi na
`Middle` i siada na nową paletę, szczęki się otwierają, wózek jedzie na
`Bottom`, chwyta cały stos od spodu i wraca na `Top`. Po `nStackSize`
sztukach stos ląduje na transporterze i jedzie na stację 12.

Liczniki (`nRemaining`, `nHeld`) są nieulotne — po zaniku zasilania maszyna
wie, ile palet zostało w stosie i ile wisi na szczękach. Czujnik wykrywający
koniec stosu dojdzie później; wtedy licznik będzie wartością oczekiwaną,
a prawdę powie czujnik.

### Stacja 4 — test ściskania
Wyjścia zaworów:

| Wyjście | Funkcja |
|---------|---------|
| `GVL.OUTPUTS[2]` | górne zewnętrzne + środkowa — **cofnij** |
| `GVL.OUTPUTS[3]` | dolne — **cofnij** |
| `GVL.OUTPUTS[4]` | dolne — **wysuń** |
| `GVL.OUTPUTS[5]` | górne środkowe — **wysuń** |
| `GVL.OUTPUTS[6]` | górne środkowe — **cofnij** |
| `GVL.OUTPUTS[7]` | górne zewnętrzne + środkowa — **wysuń** |

Skład: 3 siłowniki dolne, 3 górne od szerokich desek, 2 górne od wąskich.
Sterowane grupowo, **mierzone indywidualnie**.

Przebieg:

1. Paleta wjeżdża → start falownika 3 (rolki dociskowe).
2. Paleta mija czujnik wstępny. Czujnik jeszcze nie zamontowany —
   przy `xPreSensorInstalled = FALSE` czasówka startuje od rozpoczęcia
   wjazdu, po montażu wystarczy przełączyć bit.
3. Czasówka → wysuw **górnych**, po kolejnej czasówce wysuw **dolnych**
   (żeby dolne nie uniosły palety).
4. Po osiągnięciu wysuwu nastawionego dla każdego siłownika — test.
5. Siłownik wysunięty **ponad próg** = deska pękła → paleta NOK,
   natychmiastowe wycofanie, brak dalszych testów, jazda na odrzut.
6. Cofanie rusza już na **pierwszym** czujniku końcowym, żeby mechanika
   zdążyła zejść przed zatrzymaniem palety. Kolejność odwrotna do wysuwu:
   najpierw **dolne**, potem **górne** — górne trzymają paletę dociętą
   do transportera, dopóki dolne nie zejdą.
7. Rolki dociskowe stają razem z rozpoczęciem cofania.
8. Jeżeli mechanika zdążyła zejść, a następna stacja czeka — jedziemy
   dalej bez zatrzymania. Jeśli nie zdążyła, paleta staje i sekwencja
   kończy się na postoju.
9. Stacja wyłączalna globalnie → wtedy sam przejazd.

### Stacja 5 — test rozrywania

Zawory:

| Sygnał | Funkcja |
|--------|---------|
| `FestoValves_1[6,1]` / `[6,2]` | blokada punktu zatrzymania — wysuw / cofnięcie |
| `FestoValves_1[7,1]` / `[7,2]` | siłownik szczęk — podnoszenie / opuszczanie |
| `FestoValves_1[1,1]` | szczęki lewe: TRUE = zamknięte |
| `FestoValves_1[2,1]` | szczęki środkowe: TRUE = zamknięte |
| `FestoValves_1[3,1]` | szczęki prawe: TRUE = zamknięte |
| `FestoValves_2[1..6, 1]` | siłownik rozrywający 3,4,2,1,5,6 — opuszczanie |
| `FestoValves_2[1..6, 2]` | siłownik rozrywający 3,4,2,1,5,6 — podnoszenie |

Zawór blokady jest 3-położeniowy: podniesienie `[6,1] = TRUE`, opuszczenie
`[6,2] = TRUE`, oba wyjścia zdjęte = położenie spoczynkowe. W kodzie typ
`CYLV_3POS_MID`. Blokada ma czujniki górny i dolny. Siłownik podnoszenia szczęk ma
czujniki po obu stronach. Każdy siłownik szczęk ma czujnik otwarcia —
wjazd i wyjazd palety **tylko przy otwartych szczękach**.

Przebieg:

1. Przed wjazdem: szczęki otwarte i opuszczone, siłowniki rozrywające
   wycofane. **Blokada podnosi się dopiero w chwili, gdy z poprzedniej
   stacji rusza paleta** — nie na czasówkę po zjeździe poprzedniej.
2. Paleta dojeżdża do blokady, potwierdzenie czujnikami.
3. Czasówka → podniesienie szczęk → czasówka → zamknięcie szczęk.
   Każdy ruch z własnym watchdogiem.
4. Podnoszenie siłowników rozrywających. Każdy sprawdzany **osobno**,
   bo mają różne prędkości.
5. Przekroczenie pozycji maksymalnej = deska odpadła → paleta NOK.
6. Po przekroczeniu pozycji zaprogramowanej start odliczania czasu
   trzymania nacisku; po jego upływie sprawdzenie, czy deska się urwała,
   potem powrót do bazy.
7. Otwarcie szczęk, opuszczenie szczęk, cofnięcie blokady.
8. Gotowość do wyjazdu dopiero gdy wszystko wycofane.

### Stacja 6 — pomiar laserowy
Sygnał startu do urządzenia zewnętrznego **przed** wjazdem palety.
Paleta jedzie do końca, zatrzymuje się na dwóch czujnikach, czeka na
werdykt OK/NOK. Niezależnie od wyniku jedzie na stację 7.

### Stacja 7 — etykietowanie
Kształt nieznany. Założenie: paleta dojeżdża do czujników, PLC daje sygnał
startu, urządzenie odpowiada boolem „gotowe". **Palety NOK nie są
etykietowane** — dla nich stacja realizuje sam przejazd.

### Stacja 8 — rozjazd
Rolki podnoszone: `GVL.OUTPUTS[11]` podnoszenie, `GVL.OUTPUTS[13]`
opuszczanie. Wjazd tylko przy **podniesionych** rolkach.
Paleta OK → prosto na 11 (bez zatrzymania, jeśli 11 pusta).
Paleta NOK → zatrzymanie, opuszczenie rolek, zgłoszenie do stacji 9.

### Stacja 10 — przekierowanie
Rolki podnoszone: `GVL.OUTPUTS[10]` podnoszenie, `GVL.OUTPUTS[12]`
opuszczanie. Przyjęcie z 9 przy **opuszczonych** rolkach, wydanie na 14
przy **podniesionych**. Dwa czujniki położenia palety.

### Stacje 13 i 16 — odbiór przez operatora
Paleta/stos stoi na dwóch czujnikach. Operator wciska przycisk — sprawdzamy,
czy ładunek zniknął z czujników; jeśli tak, miejsce jest wolne. Przycisk
można wyłączyć w nastawach — wtedy miejsce uznajemy za wolne po 10 s
(nastawa) od zniknięcia z obu czujników.

---

## 7. Do rozstrzygnięcia

1. **Falownik 2** — opisany jako „Stacja 8 krzywka stakera", ale sztaplarka
   to stacja 11. Czy to krzywka sztaplarki na stacji 11?
2. **Stacja 4, falownik rolek dociskowych** — w opisie raz „falownik 2",
   raz „falownik 3". Zakładam **3**.
3. **Stacja 4, grupy zaworów** — opis wyjść nazywa zarówno grupę `7/2`,
   jak i `5/6` „środkowymi". Przyjęte: `7/2` to trzy siłowniki od szerokich
   desek, `5/6` to dwa od wąskich. Zamiana dotyczy tylko mapowania w MAIN.
4. **Numeracja wejść/wyjść** — czy zostajemy przy `GVL.INPUTS[1..300]` /
   `GVL.OUTPUTS[1..300]`, czy robimy nazwane struktury I/O per stacja?
5. **Falownik krzywki sztaplarki** — opis mówi „falownik 2, stacja 8",
   ale sztaplarka to stacja 11. Zakładam falownik 2 na stacji 11.
6. **Śledzenie palety** — czy potrzebny numer sztuki i rejestr wyników
   testów (licznik, log), czy wystarczy sortowanie OK/NOK?

---

## 8. Rozstrzygnięte

- **Zasilanie awaryjne** — sterownik ma **UPS 1 s**. TwinCAT zapisuje dane
  persystentne przy zaniku zasilania, więc pamięć obecności palet nie
  wymaga jawnego zapisu przy każdej zmianie. Flaga `xPersistDirty` zostaje
  w kodzie jako punkt zaczepienia, ale menedżer zapisu nie jest potrzebny.
  Warunek: w konfiguracji PLC musi być włączona obsługa persystencji przy
  zaniku (`Persistent Variables` + tryb zapisu przy power-fail).
- **Stacja 11** zasilana ze **stacji 8**.
- **Zawory stacji 5**: blokada `FestoValves_1[6,x]` (podniesienie `[6,1]`,
  opuszczenie `[6,2]`), podnoszenie szczęk `[7,x]`.
- **Stacja 5 zawsze zatrzymuje paletę** — bez przejazdu bez zatrzymania,
  także dla palet odrzuconych i przy wyłączonym teście
  (`aConv[5].Cfg.xAllowPassThrough := FALSE`).
- **Blokada stacji 5 podnosi się w chwili ruszenia palety z poprzedniej
  stacji**, nie na czasówkę.
- **Przerwanie testu**: stacje 4 i 6 → paleta NOK
  (`aConv[4].Cfg.xNokOnInterrupt := TRUE`, tak samo `aConv[6]`),
  pozostałe stacje → wznowienie albo powtórzenie cyklu.
