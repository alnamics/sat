# Dodatki MPX

🇬🇧 [English version](../mpx.md)

> [!WARNING]
> Wszystko na tej stronie napisał Claude, model AI, i nikt tego nie sprawdził ręcznie ani nie
> uruchamiał dłużej na prawdziwym kotle. Kod przechodzi testy automatyczne i tylko tyle o nim
> wiadomo. Używasz na własne ryzyko; włączaj funkcje po jednej i obserwuj kocioł.

Ta strona opisuje, co ten fork (wersje z czwartą liczbą, np. 5.2.0.5) dodaje do [SAT v2](https://github.com/bellini666/SAT). Same ustawienia są w [Opcjach](options.md#zaawansowane-dodatki-mpx) (System Configuration → Advanced); tutaj jest wyjaśnione, co robią i jak się ze sobą łączą.

**Wartości domyślne.** Gdy wszystkie nowe opcje mają wartości domyślne, SAT steruje kotłem dokładnie tak jak oryginalny SAT v2. Niezależnie od ustawień działają liczniki, szacowanie sprawności i przepływu, monitor pętli i komunikaty w Naprawach: czytają dane kotła i zgłaszają problemy, ale niczym nie sterują. Błąd w którymkolwiek z nich jest raz zapisywany w logu, a sterowanie ogrzewaniem działa dalej bez niego.

- [Po co](#po-co)
- [Ustawienia kotła](#ustawienia-kotła)
- [Budżet ciepła](#budżet-ciepła)
- [Harmonogramy i obecność](#harmonogramy-i-obecność)
- [Ciepła woda](#ciepła-woda)
- [Monitoring](#monitoring)
- [Komunikaty w Naprawach](#komunikaty-w-naprawach)
- [Pomiar pętli](#pomiar-pętli)
- [Po restarcie](#po-restarcie)
- [Ograniczenia i to, czego nie sprawdzono](#ograniczenia-i-to-czego-nie-sprawdzono)

## Po co

Kocioł kondensacyjny dwufunkcyjny o mocy 25–35 kW ma moc minimalną około 4–6 kW. Dobrze ocieplone mieszkanie z ogrzewaniem podłogowym w wylewce potrzebuje przez większość sezonu 1–4 kW, więc kocioł nie może pracować bez przerwy: nagrzewa wodę, wyłącza się, odczekuje czas antytaktowania i zapala ponownie. Każdy start to przedmuch komory spalania i kilka minut rozgrzewania, a do tego zużycie kotła.

Wylewka jest powolna: magazynuje ciepło na godziny. Dla pokoju nie ma znaczenia, czy ciepło z jednej godziny dotrze w czterech paleniach po 7 minut, czy w jednym trwającym 28 minut, ale kocioł ma wtedy trzy starty mniej. To właśnie robi budżet ciepła. Pozostałe dodatki wynikają z tej samej instalacji: mierzą, co robi kocioł, wcześnie wychwytują problemy i nie grzeją, gdy nikt tego nie potrzebuje.

## Ustawienia kotła

| Opcja | Domyślnie | Co robi |
|---|---|---|
| Boiler anti-cycling time | 0 | Własny czas oczekiwania kotła przed ponownym zapłonem (ustawienie instalatora, np. P17 w De Dietrich). SAT czeka tyle plus minutę, zanim uzna, że płomień się nie zapala, kalibracja czeka tyle plus dwie minuty na zapłon, a budżet ciepła nie planuje przerwy krótszej niż ten czas. |
| Valve opening time | 0 | Ile trwa otwarcie siłowników termostatów pokojowych (siłowniki termiczne: 3–6 minut). Gdy pokój zaczyna wołać o ciepło, a wcześniej nie wołał żaden, SAT czeka tyle przed zapaleniem kotła. Nie dotyczy to kotła, który już pali. |
| Cut-short burns before ending the PWM on-phase | 2 | Ile paleń kocioł może sam przerwać z powodu przegrzania wody w jednej fazie ON cyklu PWM. Dla przewymiarowanego kotła na podłogówce pasuje 1. |
| Learn overshoot protection value | wył. | Koryguje wartość ochrony przed przegrzaniem na podstawie tego, jak kończą się palenia PWM: o 1 °C w górę, gdy kocioł przerywa palenie albo palnik się nie zapala, bo woda jest już cieplejsza od temperatury zadanej; o 0,5 °C w dół, gdy palenie trwające co najmniej 10 minut ustala się 2 °C lub więcej poniżej niej. Wartość pozostaje między 30 °C a maksymalną temperaturą zadaną minus 3 °C; ponowna kalibracja albo ręczna zmiana wartości zaczyna naukę od nowa. |
| Keep heating enabled between PWM on-phases | wył. | W fazach OFF cyklu PWM zostawia centralne ogrzewanie włączone z minimalną temperaturą zadaną, żeby kocioł dwufunkcyjny nie przestawiał zaworu trójdrogowego na zasobnik ciepłej wody, gdzie długi wybieg pompy wychładzałby zasobnik. Niektóre kotły podnoszą niską temperaturę zadaną do własnego minimum i zapalają palnik: jeśli palnik zapali się później niż 90 sekund po rozpoczęciu fazy OFF, SAT przestaje to robić na godzinę i zapisuje ostrzeżenie. Krótki wybieg pompy ustawiony w kotle rozwiązuje ten sam problem prościej. |
| Duty cycles per hour (podłogówka) | 1–4 | Ogrzewanie podłogowe może zejść do jednego cyklu na godzinę. |
| Heat per cubic metre of gas | 10,2 | kWh/m³ do szacowania gazu, ciepła i sprawności; dla propanu około 24. |
| Condensing boiler | wł. | Do szacowania sprawności kotła bez czujnika temperatury spalin. |

### Moc palnika

Liczniki ciepła i gazu, przepływ wody i budżet ciepła potrzebują mocy cieplnej palnika. SAT bierze ją z mocy maksymalnej kotła i minimalnego poziomu modulacji, jeśli kocioł je podaje (OpenTherm), a w przeciwnym razie z ustawień **Minimum Consumption** i **Maximum Consumption**. Gdy nie jest znane ani jedno, ani drugie, liczniki ciepła i gazu stoją na zerze, zamiast pokazywać wymyślone wartości; budżet ciepła nadal działa i liczy w jednostkach mocy minimalnej.

OpenTherm definiuje modulację względną jako udział w zakresie między mocą minimalną a maksymalną, ale wiele kotłów podaje udział w mocy maksymalnej i na minimum pokazuje na przykład 16%. Odczytane jako udział w zakresie, prawie podwoiłoby to moc na minimum. Dlatego SAT uczy się, co kocioł pokazuje, gdy jest trzymany na minimalnej modulacji w ustabilizowanych paleniach, i liczy od tej wartości. Kocioł, którego najniższy odczyt z wielu paleń równa się jego własnemu minimalnemu poziomowi modulacji, też jest rozpoznawany. Zanim SAT zobaczy takie palenia, przyjmuje znaczenie z OpenTherm.

## Budżet ciepła

`Off`, `Learn only (shadow)` albo `On`. Dla powolnych odbiorników (ogrzewanie podłogowe w wylewce) z kotłem, którego moc minimalna jest większa od tego, czego dom zwykle potrzebuje. `On` steruje tylko ogrzewaniem podłogowym; z grzejnikami albo pompą ciepła budżet tylko się uczy, jak w trybie shadow, bo godzinne bloki powodowałyby wahania temperatury przy szybkich odbiornikach.

**Model.** Co godzinę SAT zapisuje ciepło spalone na ogrzewanie, różnicę temperatur wewnątrz i na zewnątrz, nasłonecznienie i zmianę temperatury wewnętrznej. Z bieżącej doby takich godzin dopasowuje metodą rekurencyjnych najmniejszych kwadratów równanie *ciepło + S × słońce = H × (wewnątrz − na zewnątrz) × godziny + ciepło zmagazynowane*: H to straty ciepła domu (W/K), S to ciepło, które daje pełne słońce. Doba uśrednia ciepło, które wylewka magazynuje i oddaje. Godzina zmierzona co najmniej w połowie jest przeskalowana do pełnej, krótsza jest pomijana, a okno przetrwa restart. Pierwsze dopasowanie następuje po 20 godzinach danych, a budżet jest gotowy po dwunastu dopasowaniach, czyli mniej więcej półtorej doby po włączeniu (`heat_budget_ready`). Z ustawionym na stałe **Heat loss of the house** jest gotowy od razu.

**Rozdzielanie ciepła.** Ciepło potrzebne na następny okres to *H × (temperatura zadana − zewnętrzna) − S × słońce*, plus powolna korekta PI błędu temperatury w pokoju (wzmocnienie 2 K na K, całkowanie przez 8 godzin, najwyżej ±1,5 K, dopiero gdy budżet jest gotowy). Z prognozą pogody temperatura zewnętrzna to wartość zmierzona plus trend z prognozy na najbliższe 3 godziny (najwyżej ±5 K), więc prognoza, która jest cieplejsza albo zimniejsza od Twojego czujnika, nie zafałszowuje ilości ciepła. To ciepło jest spalane w jednym bloku na mocy minimalnej:

- jeden blok na **Heat budget period** (60 minut: mniej więcej jeden zapłon na godzinę);
- potrzeba mniejsza niż **Heat budget minimum burn** przechodzi na następny okres (`heat_credit_kwh`), tak samo jak to, czego blok nie zdążył dostarczyć, do wysokości jednego okresu na mocy minimalnej;
- pobór ciepłej wody nie skraca bloku: blok trwa, aż dostarczy swoje ciepło;
- dwa palenia przerwane przez kocioł z powodu przegrzania kończą blok;
- dogrzanie ciepłej wody w ostatniej tercji okresu od razu rozpoczyna następny blok, póki kocioł jest ciepły (`hot_water_piggybacks`);
- przerwa krótsza niż czas antytaktowania nie jest warta zapłonu, więc blok trwa dalej.

Dopóki budżet nie jest gotowy, działa zwykłe sterowanie z własnym ustawieniem Force PWM. Gdy jest gotowy, SAT zawsze używa cykli przy małym obciążeniu, tak jak przy Force PWM.

**Przeciążenie.** Budżet pali tylko na mocy minimalnej. Gdy potrzeba przez dwie godziny przekracza ją o 10%, a w pokoju jest co najmniej 0,2 °C poniżej temperatury zadanej (zimny dzień w większym albo słabiej ocieplonym domu), SAT oddaje sterowanie krzywej grzewczej z własną modulacją kotła i przejmuje je z powrotem, gdy potrzeba przez godzinę jest poniżej 85% mocy minimalnej (`heat_budget_overloaded`).

**Harmonogram komfortu i obniżenie.** Z pomocnikiem harmonogramu, który jest włączony w godzinach komfortu, budżet ciepła poza nimi obniża swoją temperaturę zadaną o **Setback**. Dogrzewanie zaczyna się wcześniej o nauczony czas (Seem i in.: *godziny = a × wzrost temperatury + b × niedawne obciążenie*), a komfort kończy się godzinę wcześniej, bo wylewka grzeje dalej. Obniżenie działa tylko wtedy, gdy steruje budżet ciepła.

**Tryb shadow** uczy się i pokazuje plan, podczas gdy działa zwykłe sterowanie. Historię mają dwa sensory: **Heat need** (kW, z kredytem ciepła i długością bloku w atrybutach) oraz **Heat loss of the house** (W/K). Resztę pokazują atrybuty termostatu (`heat_budget_ready`, `solar_gain_kw`, `heat_block_active`, `heat_budget_target`, `learning_samples`). Używaj go przez kilka dni przed przełączeniem na `On`.

W symulacji mieszkania 87 m² (H = 0,12 kW/K, moc minimalna 5,3 kW) budżet zmniejszył liczbę startów palnika z około 60–75 do około 26 na dobę przy tym samym zużyciu gazu, a temperatura w pokoju trzymała się przeważnie w granicach około ±0,5 °C od zadanej. Symulacja to nie dom.

## Harmonogramy i obecność

- **Wyłączanie ogrzewania przy cieple** (Warm weather shutdown): centralne ogrzewanie wyłącza się, gdy temperatura zewnętrzna uśredniona z mniej więcej doby (po co najmniej 6 godzinach odczytów) jest równa progowi albo wyższa, i wraca, gdy średnia spadnie 2 °C poniżej progu. Prognoza nie pozwala włączyć ogrzewania, gdy najbliższe 12 godzin ma być ciepłe, i nie pozwala go wyłączyć, gdy ma być zimno; tak jak w budżecie ciepła liczy się tylko trend z prognozy. Średnia liczy się także wtedy, gdy SAT jest wyłączony, a po godzinie bez odczytów zaczyna od nowa. Ciepła woda działa cały czas. Atrybuty `warm_weather_shutdown` i `outside_temperature_mean`.
- **Obecność** (Presence): osoby, lokalizatory urządzeń, strefy (liczba osób) albo grupy. Gdy od 30 minut nikogo nie ma w domu, SAT przełącza się z braku presetu, Home albo Comfort na Away, a po czyimś powrocie wraca do poprzedniego presetu. Z czujnikiem odległości z integracji Proximity i ustawionym **Return distance** ogrzewanie wraca, gdy tylko ktoś jest w tej odległości. Atrybut `occupancy`. Dla wylewki ustaw preset Away łagodnie (na przykład 19 °C): podłoga potrzebuje godzin, żeby wrócić z domyślnych 10 °C.
- **Wykrywanie otwartego okna** (Detect open windows from the temperature): spadek temperatury w głównym pokoju o 0,8 °C w ciągu 10 minut przełącza na preset Activity na 30 minut, tak jak czujnik otwarcia. Chwilowy błąd czujnika wygląda tak samo jak okno. Atrybut `window_open_detected`.

## Ciepła woda

Dla kotłów, które przyjmują temperaturę zadaną ciepłej wody przez OpenTherm.

- **Hot water temperature** (0 = zostaw ciepłą wodę kotłowi) i **Hot water eco temperature**: z pomocnikiem harmonogramu **Hot water schedule** poza jego godzinami obowiązuje temperatura ekonomiczna. Chłodniejszy zasobnik traci mniej ciepła przez obudowę, a kocioł lepiej kondensuje, gdy go dogrzewa.
- **Przegrzew przeciw legionelli** (Legionella boost): w wybranym dniu i o wybranej godzinie zasobnik jest nagrzewany do 60 °C (albo do własnego maksimum kotła, jeśli jest niższe) i trzymany w tej temperaturze przez godzinę; po 4 godzinach przegrzew się poddaje. Jeden przegrzew na tydzień.
- SAT wysyła temperaturę zadaną, gdy jej wartość się zmienia, i raz po każdym starcie, więc temperatura ustawiona ręcznie zostaje do następnej zmiany. Nie sprawdza, czy kocioł ją przyjął. Atrybuty `hot_water_setpoint_sent`, `hot_water_legionella_boost` i `hot_water_last_boost_week`.

## Monitoring

Działa dla każdego wpisu, także gdy SAT jest wyłączony, więc liczy też letnią ciepłą wodę. Wstrzymuje się, gdy bramka nie ma łączności.

- **Liczniki**, które tylko rosną, do statystyk i panelu Energia: Burner starts (starty palnika), Burner hours (godziny pracy palnika), Heat for space heating (ciepło na ogrzewanie), Heat for hot water (ciepło na ciepłą wodę, kWh), Estimated gas use (szacowane zużycie gazu, m³), Heating degree days (stopniodni grzania, baza 18 °C), a po ustawieniu **Gas price** także sensor Estimated gas cost (szacowany koszt gazu). Ciepło i gaz wymagają znanej [mocy palnika](#moc-palnika).
- **Flame starts in the last hour** (starty palnika w ostatniej godzinie).
- **Estimated boiler efficiency** (szacowana sprawność kotła): bilans energii spalania odniesiony do ciepła spalania gazu (tego, co rozlicza gazomierz). Stratą jest ciepło uciekające ze spalinami i ciepło utajone pary, która się nie skropliła; poniżej punktu rosy (około 55 °C dla gazu ziemnego) część pary się skrapla i oddaje ciepło wodzie. Około 97% przy spalinach 30 °C, 91% przy 50 °C, 88% lub mniej bez kondensacji. Temperatura spalin pochodzi z kotła, jeśli ją podaje; w przeciwnym razie dla kotła kondensacyjnego przyjmuje się spaliny 4 K cieplejsze od powrotu, co jest trafne blisko mocy minimalnej, a zbyt optymistyczne przy dużej mocy. Nadmiar powietrza 1,3, powietrze do spalania 20 °C, straty przez obudowę i postojowe nie są wliczone; przy cieple z metra sześciennego gazu równym 18 kWh lub więcej przyjmuje się propan. Atrybuty `heating_average`, `hot_water_average` (średnie z czasu palenia z ostatniej doby) i `source`.
- **Estimated water flow** (szacowany przepływ wody): moc cieplna podzielona przez różnicę temperatur zasilania i powrotu w ustabilizowanych paleniach na ogrzewanie (co najmniej 3 minuty, różnica co najmniej 1,5 K); spadek pokazuje zamykanie się pętli.
- **Cylinder cooling after heating stops** (wychładzanie zasobnika po zakończeniu grzania): spadki temperatury zasobnika z ostatniej doby, które zaczęły się w ciągu 10 minut od końca zapotrzebowania na ogrzewanie. To znak, że wybieg pompy przepuszcza wodę grzewczą przez wężownicę zasobnika.
- Z termostatami pokojowymi albo grzejnikowymi: **Open loops** (otwarte pętle) oraz **Loops to rebalance** (pętle do wyregulowania), gdzie dla każdego pokoju jest udział doby z otwartym zaworem, o ile pokój był cieplejszy albo chłodniejszy od średniej z pokoi, przepływ jego pętli (znany, gdy pętla była widziana i otwarta, i zamknięta) oraz podpowiedź do rotametru (`reduce`, `increase`, `ok`). Podpowiedź zakłada, że pokoje mają być jednakowo ciepłe. `base_flow_lpm` to przepływ wszystkiego, czego nigdy nie widziano zamkniętego: pętli bez siłownika i pokoi, których zawór nigdy się nie zamknął, nie da się od siebie odróżnić.
- `suggested_heating_curve_coefficient` w atrybutach termostatu, gdy budżet ciepła jest gotowy: z H i przenikania ciepła podłogi nauczonego w ustabilizowanych paleniach (`floor_heat_transfer_w_per_k`) wyliczana jest temperatura zasilania, jakiej dom potrzebuje przy −15, −5 i 5 °C na zewnątrz, oraz współczynnik krzywej, który do niej pasuje. Przenikanie jest mierzone względem pokoju, a nie wylewki, więc to tylko zgrubna wskazówka. SAT sam nie zmienia krzywej.

Wartości, które zmieniają się z każdym odczytem (zapotrzebowanie na ciepło, kredyt ciepła, średnia dobowa temperatura zewnętrzna, różnica spaliny–powrót), nie są zapisywane w rejestratorze jako atrybuty termostatu, żeby nie rozdmuchiwać bazy danych.

## Komunikaty w Naprawach

Pojawiają się w **Ustawienia → Naprawy** i znikają same, gdy przyczyna ustąpi.

| Komunikat | Kiedy |
|---|---|
| Niskie ciśnienie wody | poniżej 0,8 bar przez 10 minut; znika przy 0,9 bar |
| Ciśnienie wody stale spada | średnie dobowe ciśnienie, skorygowane o temperaturę wody, spada o 0,05 bar na tydzień lub więcej przez co najmniej cztery dni, przy stracie 0,1 bar |
| Błąd kotła | kocioł zgłasza błąd przez minutę (z kodem producenta) |
| Brudny wymiennik ciepła | spaliny ponad 12 K cieplejsze od powrotu w ustabilizowanych paleniach blisko mocy minimalnej, średnio z doby palenia |
| Zasilanie za gorące dla podłogi | tylko podłogówka: zasilanie powyżej **Maximum flow for the screed** (55 °C) przez 3 minuty podczas ogrzewania; komunikat zostaje na dobę |
| Za mały przepływ wody | tylko podłogówka: zasilanie ponad 20 K cieplejsze od powrotu przez 5 minut w ustabilizowanych paleniach |
| Termin przeglądu kotła | **Last boiler service** plus **Service interval** |
| Wzrost zużycia gazu | gaz na ogrzewanie z ostatniego tygodnia jest o 30% wyższy, niż wynika z czterech poprzednich tygodni dla tej pogody |

Przy trzech z nich warto wyjaśnić, jak unikają fałszywych alarmów:

- **Spadające ciśnienie.** Ciśnienie w układzie zamkniętym zależy od temperatury wody, więc sam koniec sezonu grzewczego je obniża. SAT uczy się, o ile ciśnienie zmienia się na kelwin, z tego, jak obie wartości wahają się razem w ostatnich dniach, i porównuje dni przy jednej temperaturze. Wzrost o 0,15 bar z dnia na dzień to dolanie wody i początek nowej historii. Palenia na ciepłą wodę i pięć minut po nich są pomijane.
- **Brudny wymiennik.** Przy wyższej mocy spaliny z natury są wyraźnie cieplejsze od powrotu. Liczą się tylko palenia w dolnych 15% zakresu modulacji i tylko ze spalinami poniżej 90 °C (kondensacja). Kocioł, który nie podaje modulacji, nie jest oceniany.
- **Zużycie gazu.** Dzienne zużycie gazu na ogrzewanie rośnie liniowo z różnicą temperatur wewnątrz i na zewnątrz, ale nie od zera: słońce, ludzie i urządzenia grzeją za darmo. Dlatego gaz na stopniodzień rośnie przy każdym ochłodzeniu. SAT dopasowuje tę prostą do czterech poprzednich tygodni i porównuje ostatni tydzień z tym, co prosta przewiduje dla jego pogody; gaz na ciepłą wodę jest pomijany, a tydzień z pogodą odbiegającą o ponad 3 K od tamtych tygodni nie jest oceniany.

## Pomiar pętli

Akcja `sat.measure_loops` (Narzędzia deweloperskie → Akcje) mierzy przepływ wody w każdej pętli grzewczej. Wyłącza wszystkie termostaty pokojowe i uruchamia palnik na mocy minimalnej (do Twojej maksymalnej temperatury zadanej), żeby zmierzyć przepływ bazowy pętli bez siłownika. Potem otwiera pokoje po jednym (temperatura zadana 30 °C) i mierzy przyrost. Każdy krok czeka czas otwarcia zaworów (6 minut, jeśli nie jest ustawiony) plus 5 minut i zbiera 10 ustabilizowanych próbek, więc trwa około 15 minut na pokój. Termostaty wracają do poprzednich ustawień, a wynik przychodzi jako powiadomienie i w atrybucie `loop_measurement`. SAT musi być w trybie grzania; wyłączenie go przerywa pomiar. W trakcie pomiaru nie korzystaj z ciepłej wody.

Ustawienia termostatów są zapisywane, zanim cokolwiek zostanie zmienione. Jeśli Home Assistant zatrzyma się w środku pomiaru, przy następnym starcie termostaty wrócą do zapisanych ustawień.

## Po restarcie

Po restarcie Home Assistanta albo zmianie opcji zachowują się: liczniki, nauczone straty ciepła z oknem dobowym, nauczony czas dogrzewania, historia ciśnienia, historia gazu, średnia do wyłączania przy cieple (jeśli restart trwał krócej niż 6 godzin), preset Away ustawiony przez obecność, preset Activity ustawiony przez wykrywanie okna (jego 30 minut liczy się od nowa), tydzień ostatniego przegrzewu przeciw legionelli i ustawienia termostatów z trwającego pomiaru pętli.

Uczone od nowa: odczyt kotła na minimalnej modulacji, średnie i przepływy monitora pętli, przenikanie ciepła podłogi, średnie sprawności, kredyt ciepła i bieżący blok budżetu ciepła.

## Ograniczenia i to, czego nie sprawdzono

- Sprawdzone: testy jednostkowe i integracyjne w CI (ruff ze wszystkimi regułami, ty, pytest, hassfest) oraz symulacje budżetu ciepła na dwuwęzłowym modelu wylewki i pokoju.
- Niesprawdzone: zachowanie na jakimkolwiek prawdziwym kotle (dodatki powstały dla De Dietrich Lumea z OTGW w trybie szeregowym, ale jeszcze tam nie działały); połączenia MQTT, ESPHome i EMS; prawdziwe encje pogody i harmonogramów; pomiar pętli na prawdziwych siłownikach; dokładność szacunków sprawności, przepływu i krzywej.
- Szacunki są szacunkami: opierają się na mocy palnika, własnych czujnikach kotła i podręcznikowych wartościach spalania.
- Brak migracji wpisu konfiguracji: powrót do oryginalnego SAT v2 to kwestia podmiany plików.

---

Wróć: [README](../../README.pl.md) · Zobacz też: [Opcje](options.md) · [Jak działa SAT](how-it-works.md)
