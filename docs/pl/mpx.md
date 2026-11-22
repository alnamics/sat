# Dodatki MPX

🇬🇧 [English version](../mpx.md)

> [!WARNING]
> Wszystko na tej stronie napisał Claude, model AI, i nie sprawdził tego człowiek. Kod
> przechodzi testy automatyczne i od połowy listopada 2026 pracuje na jednym prawdziwym kotle
> (zob. [Test na prawdziwym kotle](#test-na-prawdziwym-kotle)); niczego innego nie próbowano.
> Używasz na własne ryzyko; włączaj funkcje po jednej i obserwuj kocioł.

Ta strona opisuje, co ten fork (wersje z czwartą liczbą, np. 5.2.0.5) dodaje do [SAT v2](https://github.com/bellini666/SAT). Same ustawienia są w [Opcjach](options.md) (menu Sterowanie i PWM, Budżet ciepła, Ciepła woda, Obecność i okna, Kocioł i serwis); tutaj jest wyjaśnione, co robią i jak się ze sobą łączą.

**Wartości domyślne.** Gdy wszystkie nowe opcje mają wartości domyślne, SAT steruje kotłem dokładnie tak jak oryginalny SAT v2. Wyjątkiem jest ochrona przed zamarzaniem, która grzeje tylko przy wyłączonym SAT i temperaturze w pokoju 6 °C. Niezależnie od ustawień działają liczniki, szacowanie sprawności i przepływu, monitor pętli i komunikaty w Naprawach: czytają dane kotła i zgłaszają problemy, ale niczym nie sterują. Błąd w którymkolwiek z nich jest raz zapisywany w logu, a sterowanie ogrzewaniem działa dalej bez niego.

- [Po co](#po-co)
- [Ustawienia kotła](#ustawienia-kotła)
- [Budżet ciepła](#budżet-ciepła)
- [Harmonogramy i obecność](#harmonogramy-i-obecność)
- [Ciepła woda](#ciepła-woda)
- [Monitoring](#monitoring)
- [Komunikaty w Naprawach](#komunikaty-w-naprawach)
- [Pomiar pętli](#pomiar-pętli)
- [Po restarcie](#po-restarcie)
- [Test na prawdziwym kotle](#test-na-prawdziwym-kotle)
- [Ograniczenia i to, czego nie sprawdzono](#ograniczenia-i-to-czego-nie-sprawdzono)

## Po co

Kocioł kondensacyjny dwufunkcyjny o mocy 25–35 kW ma moc minimalną około 4–6 kW. Dobrze ocieplone mieszkanie z ogrzewaniem podłogowym w wylewce potrzebuje przez większość sezonu 1–4 kW, więc kocioł nie może pracować bez przerwy: nagrzewa wodę, wyłącza się, odczekuje czas antytaktowania i zapala ponownie. Każdy start to przedmuch komory spalania i kilka minut rozgrzewania, a do tego zużycie kotła.

Wylewka jest powolna: magazynuje ciepło na godziny. Dla pokoju nie ma znaczenia, czy ciepło z jednej godziny dotrze w czterech paleniach po 7 minut, czy w jednym trwającym 28 minut, ale kocioł ma wtedy trzy starty mniej. To właśnie robi budżet ciepła. Pozostałe dodatki wynikają z tej samej instalacji: mierzą, co robi kocioł, wcześnie wychwytują problemy i nie grzeją, gdy nikt tego nie potrzebuje.

## Ustawienia kotła

| Opcja | Domyślnie | Co robi |
|---|---|---|
| Blokada ponownego zapłonu w kotle | 0 | Własny czas oczekiwania kotła przed ponownym zapłonem (ustawienie instalatora, np. P17 w De Dietrich). SAT czeka tyle plus minutę, zanim uzna, że płomień się nie zapala, kalibracja czeka tyle plus dwie minuty na zapłon, a budżet ciepła nie planuje przerwy krótszej niż ten czas. Przy 0 budżet ciepła uczy się go sam: z ponownego zapłonu po paleniu na ogrzewanie, które kocioł wstrzymywał mimo zapotrzebowania co najmniej przez minutę; mediana z ostatnich dziesięciu, gdy są co najmniej trzy (2–30 minut, atrybut `minimum_pause_minutes`); do tego czasu 10 minut. |
| Czas otwarcia siłowników | 0 | Ile trwa otwarcie siłowników termostatów pokojowych (siłowniki termiczne: 3–6 minut). Gdy pokój zaczyna wołać o ciepło, a wcześniej nie wołał żaden, SAT czeka tyle przed zapaleniem kotła. Nie dotyczy to kotła, który już pali. |
| Przerwane palenia, po których kończy się faza PWM | 2 | Ile paleń kocioł może sam przerwać z powodu przegrzania wody w jednej fazie ON cyklu PWM. Dla przewymiarowanego kotła na podłogówce pasuje 1. |
| Ucz się wartości ochrony przed przegrzaniem | wył. | Koryguje wartość ochrony przed przegrzaniem na podstawie tego, jak kończą się palenia PWM: o 1 °C w górę, gdy kocioł przerywa palenie albo palnik się nie zapala, bo woda jest już cieplejsza od temperatury zadanej; o 0,5 °C w dół, gdy palenie trwające co najmniej 10 minut ustala się 2 °C lub więcej poniżej niej. Wartość pozostaje między 30 °C a maksymalną temperaturą zadaną minus 3 °C; ponowna kalibracja albo ręczna zmiana wartości zaczyna naukę od nowa. |
| Nie wyłączaj ogrzewania między fazami PWM | wył. | W fazach OFF cyklu PWM zostawia centralne ogrzewanie włączone z minimalną temperaturą zadaną, żeby kocioł dwufunkcyjny nie przestawiał zaworu trójdrogowego na zasobnik ciepłej wody, gdzie długi wybieg pompy wychładzałby zasobnik. Wiele kotłów podnosi niską temperaturę zadaną do własnego minimum (Lumea i inne płyty Baxi do 25 °C, podawane jako ID 49 i jako nastawa przyjęta przez kocioł) i zapala palnik, gdy woda do niego wystygnie. SAT wyłącza ogrzewanie do końca fazy OFF, gdy woda zbliży się do tego minimum na 1 K; jeśli palnik mimo to zapali się później niż 90 sekund po rozpoczęciu fazy OFF, krótkie palenie (skończyła się blokada przed ponownym zapłonem kotła) wyłącza ogrzewanie do końca tej fazy OFF, a dłuższe na godzinę, z ostrzeżeniem. Gdy palenie z fazy ON trwa dalej w fazie OFF (kocioł obniża nastawę stopniowo i gasi kilka kelwinów nad nią, minutę do trzech później), SAT pozwala mu zgasnąć samemu i nie traktuje go jako zapłonu; wyłączenie ogrzewania, żeby je przerwać, przestawiłoby zawór kotła dwufunkcyjnego na zasobnik. Palenie, które trwa jeszcze po 10 minutach, jest kończone wyłączeniem ogrzewania. Krótki wybieg pompy ustawiony w kotle rozwiązuje ten sam problem prościej. |
| Cykle PWM na godzinę (podłogówka) | 1–4 | Ogrzewanie podłogowe może zejść do jednego cyklu na godzinę. |
| Ciepło z metra sześciennego gazu | 10,2 | kWh/m³ do szacowania gazu, ciepła i sprawności; dla propanu około 24. |
| Kocioł kondensacyjny | wł. | Do szacowania sprawności kotła bez czujnika temperatury spalin. |

### Moc palnika

Liczniki ciepła i gazu, przepływ wody i budżet ciepła potrzebują mocy cieplnej palnika. SAT bierze ją z mocy maksymalnej kotła i minimalnego poziomu modulacji, jeśli kocioł je podaje (OpenTherm), a w przeciwnym razie z ustawień **Zużycie gazu na minimalnej i maksymalnej mocy**. Gdy nie jest znane ani jedno, ani drugie, liczniki ciepła i gazu stoją na zerze, zamiast pokazywać wymyślone wartości; budżet ciepła nadal działa i liczy w jednostkach mocy minimalnej.

OpenTherm definiuje modulację względną jako udział w zakresie między mocą minimalną a maksymalną, ale wiele kotłów podaje udział w mocy maksymalnej i na minimum pokazuje na przykład 16%. Odczytane jako udział w zakresie, prawie podwoiłoby to moc na minimum. Dlatego SAT uczy się, co kocioł pokazuje, gdy jest trzymany na minimalnej modulacji w ustabilizowanych paleniach, i liczy od tej wartości. Kocioł, którego najniższy odczyt z wielu paleń równa się jego własnemu minimalnemu poziomowi modulacji, też jest rozpoznawany. Zanim SAT zobaczy takie palenia, przyjmuje znaczenie z OpenTherm.

## Budżet ciepła

Wyłączony, Tylko nauka albo Włączony. Dla powolnych odbiorników (ogrzewanie podłogowe w wylewce) z kotłem, którego moc minimalna jest większa od tego, czego dom zwykle potrzebuje. Włączony steruje tylko ogrzewaniem podłogowym; z grzejnikami albo pompą ciepła budżet tylko się uczy, jak w trybie Tylko nauka, bo godzinne bloki powodowałyby wahania temperatury przy szybkich odbiornikach.

**Model.** Co godzinę SAT zapisuje ciepło spalone na ogrzewanie, różnicę temperatur wewnątrz i na zewnątrz, nasłonecznienie i zmianę temperatury wewnętrznej. Z bieżącej doby takich godzin dopasowuje równanie *ciepło + S × słońce = H × (wewnątrz − na zewnątrz) × godziny + ciepło zmagazynowane* w dwóch krokach, każdy metodą rekurencyjnych najmniejszych kwadratów: H, straty ciepła domu (W/K), z godzin bez słońca (co najmniej 8), a potem S, ciepło z pełnego słońca, z godzin wyraźnie słonecznych przy znanym H, raz na każdą nową taką godzinę i dopiero przy co najmniej godzinie pełnego słońca w dobie. W szary dzień odrobina słońca przypisałaby słońcu całe darmowe ciepło od gotowania i ludzi; słońce nauczone przed 5.2.0.35 dlatego zaczyna od zera. Uczone razem z jednej doby, w której słońce świeci w najcieplejszych godzinach, oba parametry przepychały się nawzajem (S rosło do granicy, H spadało). H jest wartością efektywną: ciepło od sąsiadów, ludzi, sprzętów i ciepłego zasobnika ją obniża, a tego właśnie potrzebuje budżet. Doba uśrednia ciepło, które wylewka magazynuje i oddaje. Ciepło magazynowane na kelwin, C, zaczyna od 4 kWh/K i jest uczone razem z H z dni, w których temperatura w pokoju się zmieniała (nowa temperatura docelowa, obniżenie); w stałe dni zostaje bez zmian (`heat_capacity_kwh_per_k`, 1–20 kWh/K). Murowany dom z wylewkami ma zwykle 5–8. Godzina zmierzona co najmniej w połowie jest przeskalowana do pełnej, krótsza jest pomijana, a okno przetrwa restart. Pierwsze dopasowanie następuje po 20 godzinach danych, a budżet jest gotowy po dwunastu dopasowaniach, czyli mniej więcej półtorej doby po włączeniu (`heat_budget_ready`). Z ustawionymi na stałe **Stratami ciepła domu** jest gotowy od razu.

**Rozdzielanie ciepła.** Ciepło potrzebne na następny okres to *H × (temperatura zadana − zewnętrzna) − S × słońce*, plus korekta PI błędu temperatury w pokoju, liczona jako przesunięcie temperatury zewnętrznej: 8 K na każdy kelwin błędu w pokoju oraz człon całkujący 1 K na 1,5 kelwinogodziny (najwyżej ±8 K), który przejmuje to, w czym model się myli. Człon całkujący działa tylko w zakresie 0,5 °C od temperatury zadanej i dopiero gdy budżet jest gotowy, więc zmiana temperatury zadanej go nie rozkręca. W symulacji temperatura zadana przesunięta o 1 °C jest osiągana po około 6–8 godzinach. Z prognozą pogody temperatura zewnętrzna to wartość zmierzona plus trend z prognozy na najbliższe 3 godziny (najwyżej ±5 K), więc prognoza, która jest cieplejsza albo zimniejsza od Twojego czujnika, nie zafałszowuje ilości ciepła. To ciepło jest spalane w jednym bloku na mocy minimalnej:

- kredyt co **Okres** budżetu (60 minut: mniej więcej jeden zapłon na godzinę);
- potrzeba mniejsza niż **Minimalne palenie** przechodzi na następny okres (`heat_credit_kwh`), tak samo jak to, czego blok nie zdążył dostarczyć, do wysokości jednego okresu na mocy minimalnej;
- pobór ciepłej wody nie skraca bloku: blok trwa, aż dostarczy swoje ciepło;
- dwa palenia przerwane przez kocioł z powodu przegrzania kończą blok; cztery zaniki płomienia (palenia kończące się daleko poniżej nastawy, zob. Monitoring) też go kończą, a niedostarczone ciepło przechodzi dalej;
- dogrzanie ciepłej wody w ostatniej tercji okresu od razu rozpoczyna następny blok, póki kocioł jest ciepły (`hot_water_piggybacks`);
- przerwa krótsza niż czas antytaktowania nie jest warta zapłonu, więc blok trwa dalej;
- pokój cieplejszy o ponad 0,5 °C od temperatury zadanej nie dostaje ciepła: trwający blok się kończy i nic nie przechodzi na później (`heat_budget_room_too_warm`);
- po obniżeniu temperatury zadanej o 0,2 °C lub więcej dom stygnie swobodnie: nic się nie pali, dopóki pokój nie zejdzie na 0,2 °C od nowego celu (`heat_budget_coasting`);
- gdy wszystkie zawory pokojowe są zamknięte, budżet nie nalicza zaległego ciepła, więc po ich otwarciu nie odrabia czasu, w którym były zamknięte.

Dopóki budżet nie jest gotowy, działa zwykłe sterowanie z własnym ustawieniem Zawsze używaj PWM. Gdy jest gotowy, SAT zawsze używa cykli przy małym obciążeniu, tak jak przy Zawsze używaj PWM.

**Wiatr.** Z encją prognozy pogody, która podaje prędkość wiatru, SAT uczy się też, o ile więcej ciepła dom traci przy wietrze: z godzin bez słońca porównuje to, czego nie tłumaczy H, z wiatrem powyżej jego zwykłego poziomu (średnia z około czterech dni). Nauczony udział na 10 km/h pokazuje atrybut `wind_heat_loss_percent_per_10kmh`, a bieżący wiatr `wind_speed_kmh`. Zapotrzebowanie uwzględnia go (`wind_correction_active`) dopiero po dwóch dobach dopasowań, gdy godzinny wiatr zmieniał się o co najmniej 4 km/h, i przy co najmniej 3% na 10 km/h; korekta mieści się między −20% a +50%. Szczelny dom z sąsiadami z niektórych stron często zostanie poniżej tego progu, a resztę i tak wyrównuje człon całkujący. Wersja 5 SAT wiatr tylko mierzy; tutaj jest używany, gdy jego wpływ jest wyraźny.

**Przeciążenie.** Budżet pali tylko na mocy minimalnej. Gdy potrzeba przez dwie godziny przekracza ją o 10%, a w pokoju jest co najmniej 0,2 °C poniżej temperatury zadanej (zimny dzień w większym albo słabiej ocieplonym domu), SAT oddaje sterowanie krzywej grzewczej z własną modulacją kotła i przejmuje je z powrotem, gdy potrzeba przez godzinę jest poniżej 85% mocy minimalnej (`heat_budget_overloaded`).

**Harmonogram komfortu i obniżenie.** Z pomocnikiem harmonogramu, który jest włączony w godzinach komfortu, budżet ciepła poza nimi obniża swoją temperaturę zadaną o wartość **Obniżenie poza harmonogramem**. Dogrzewanie zaczyna się wcześniej o nauczony czas (Seem i in.: *godziny = a × wzrost temperatury + b × niedawne obciążenie*), a komfort kończy się godzinę wcześniej, bo wylewka grzeje dalej. Obniżenie działa tylko wtedy, gdy steruje budżet ciepła.

**Tryb Tylko nauka** uczy się i pokazuje plan, podczas gdy działa zwykłe sterowanie. Historię mają dwa sensory: **Zapotrzebowanie na ciepło** (kW, z kredytem ciepła i długością bloku w atrybutach) oraz **Straty ciepła domu** (W/K). `next_block_start` i `next_block_end` podają, kiedy planowany jest następny blok, jeśli potrzeba się nie zmieni (dogrzanie ciepłej wody pod koniec okresu może go przyspieszyć). Resztę pokazują atrybuty termostatu (`heat_budget_ready`, `solar_gain_kw`, `heat_block_active`, `heat_budget_target`, `learning_samples`). Używaj go przez kilka dni przed przełączeniem na Włączony.

W symulacji mieszkania 87 m² (H = 0,12 kW/K, moc minimalna 5,3 kW) budżet zmniejszył liczbę startów palnika z około 60–75 do około 26 na dobę przy tym samym zużyciu gazu, a temperatura w pokoju trzymała się przeważnie w granicach około ±0,5 °C od zadanej. Symulacja to nie dom.

## Harmonogramy i obecność

- **Ochrona przed zamarzaniem** (domyślnie 6 °C, w menu Sterowanie i PWM): gdy SAT jest wyłączony, a w pokoju spadnie do tej temperatury, kocioł grzeje wodą 30 °C, aż będzie o 1 °C cieplej; potem sterowanie wraca do bramki i podłączonego do niej termostatu. W tym czasie encja klimatu pokazuje grzanie, a atrybut `frost_protection_active` jest włączony. 0 wyłącza.
- **Wyłączanie ogrzewania przy cieple** (Wyłączenie przy ciepłej pogodzie): centralne ogrzewanie wyłącza się, gdy temperatura zewnętrzna uśredniona z mniej więcej doby (po co najmniej 6 godzinach odczytów) jest równa progowi albo wyższa, i wraca, gdy średnia spadnie 2 °C poniżej progu. Prognoza nie pozwala włączyć ogrzewania, gdy najbliższe 12 godzin ma być ciepłe, i nie pozwala go wyłączyć, gdy ma być zimno; tak jak w budżecie ciepła liczy się tylko trend z prognozy. Średnia liczy się także wtedy, gdy SAT jest wyłączony, a po godzinie bez odczytów zaczyna od nowa. Ciepła woda działa cały czas. Atrybuty `warm_weather_shutdown` i `outside_temperature_mean`.
- **Obecność**: osoby, lokalizatory urządzeń, strefy (liczba osób) albo grupy. Gdy od 30 minut nikogo nie ma w domu, SAT przełącza się z braku presetu, Home albo Comfort na Away, a po czyimś powrocie wraca do poprzedniego presetu. Z czujnikiem odległości z integracji Proximity i ustawioną **Odległością powrotu** ogrzewanie wraca, gdy tylko ktoś jest w tej odległości. Atrybut `occupancy`. Dla wylewki ustaw preset Away łagodnie (na przykład 19 °C): podłoga potrzebuje godzin, żeby wrócić z domyślnych 10 °C.
- **Wykrywanie otwartego okna** (Wykrywaj otwarte okna po temperaturze): spadek temperatury w głównym pokoju o 0,8 °C w ciągu 10 minut albo o 0,3 °C w ciągu 30 minut przełącza na preset Activity, tak jak czujnik otwarcia. Każdy kolejny spadek o 0,1 °C w ciągu 25 minut przedłuża przerwę; kończy się ona 30 minut po ostatnim spadku i najpóźniej po 2 godzinach. Pomieszczenie z podłogówką samo stygnie wolniej niż 0,3 °C na godzinę, więc tak szybko obniża temperaturę tylko napływające zimne powietrze. Czujnik w pokoju musi podawać dziesiąte części stopnia. Przez 10 minut po starcie odczyty tylko się ustalają, a odczyt różniący się od poprzedniego o 1,5 °C lub więcej jest traktowany jako błąd czujnika, a nie spadek. Atrybut `window_open_detected`.

## Ciepła woda

Dla kotłów, które przyjmują temperaturę zadaną ciepłej wody przez OpenTherm.

- **Temperatura ciepłej wody** (0 = zostaw ciepłą wodę kotłowi) i **Temperatura eko**: z pomocnikiem **Harmonogram ciepłej wody** poza jego godzinami obowiązuje temperatura ekonomiczna. Chłodniejszy zasobnik traci mniej ciepła przez obudowę, a kocioł lepiej kondensuje, gdy go dogrzewa.
- **Przegrzew przeciw legionelli** (Dzień i godzina przegrzewu): w wybranym dniu i o wybranej godzinie zasobnik jest nagrzewany do 60 °C (albo do własnego maksimum kotła, jeśli jest niższe) i trzymany w tej temperaturze przez godzinę; po 4 godzinach przegrzew się poddaje. Jeden przegrzew na tydzień.
- SAT wysyła temperaturę zadaną, gdy jej wartość się zmienia, i raz po każdym starcie, więc temperatura ustawiona ręcznie zostaje do następnej zmiany. Nie sprawdza, czy kocioł ją przyjął. Atrybuty `hot_water_setpoint_sent`, `hot_water_legionella_boost` i `hot_water_last_boost_week`.
- **Dogrzewanie bez flagi**: niektóre kotły, w tym De Dietrich Lumea, dogrzewają zasobnik bez ustawiania flagi ciepłej wody. Palenie, w którym woda wzrosła o ponad 10 °C od zapłonu i jest o ponad 10 °C cieplejsza od temperatury zadanej i od najniższej nastawy ogrzewania kotła (ID 49, a bez niej 25 °C), po 20 sekundach liczy się jako ciepła woda. Korzystają z tego utrzymanie grzania między fazami PWM, budżet ciepła, liczniki, sprawność i pomiar pętli, a palenie na ogrzewanie, które kocioł przerwał dla takiego dogrzania do 5 minut później, nie liczy się jako przerwane.

## Monitoring

Działa dla każdego wpisu, także gdy SAT jest wyłączony, więc liczy też letnią ciepłą wodę. Wstrzymuje się, gdy bramka nie ma łączności.

- **Liczniki**, które tylko rosną, do statystyk i panelu Energia: Starty palnika, Godziny pracy palnika, Ciepło na ogrzewanie, Ciepło na ciepłą wodę (kWh), Szacowane zużycie gazu (m³), Stopniodni grzania (baza 18 °C), a po ustawieniu **Ceny gazu** także Szacowany koszt gazu. Ciepło i gaz wymagają znanej [mocy palnika](#moc-palnika).
- **Zapłony w ostatniej godzinie**.
- **Szacowana sprawność kotła**: bilans energii spalania odniesiony do ciepła spalania gazu (tego, co rozlicza gazomierz). Stratą jest ciepło uciekające ze spalinami i ciepło utajone pary, która się nie skropliła; poniżej punktu rosy (około 55 °C dla gazu ziemnego) część pary się skrapla i oddaje ciepło wodzie. Około 97% przy spalinach 30 °C, 91% przy 50 °C, 88% lub mniej bez kondensacji. Temperatura spalin pochodzi z kotła, jeśli ją podaje; w przeciwnym razie dla kotła kondensacyjnego przyjmuje się spaliny 4 K cieplejsze od powrotu, co jest trafne blisko mocy minimalnej, a zbyt optymistyczne przy dużej mocy. Nadmiar powietrza 1,3, powietrze do spalania 20 °C, straty przez obudowę i postojowe nie są wliczone; przy cieple z metra sześciennego gazu równym 18 kWh lub więcej przyjmuje się propan. Atrybuty `heating_average`, `hot_water_average` (średnie z czasu palenia z ostatniej doby) i `source`.
- **Szacowany przepływ wody**: moc cieplna podzielona przez różnicę temperatur zasilania i powrotu w ustabilizowanych paleniach na ogrzewanie (co najmniej 3 minuty, różnica co najmniej 1,5 K); spadek pokazuje zamykanie się pętli.
- **Wychładzanie zasobnika przez ogrzewanie**: spadki temperatury zasobnika z ostatniej doby, które zaczęły się w ciągu 10 minut od początku albo końca zapotrzebowania na ogrzewanie. To znak, że zawór trójdrogowy przepuszcza wodę grzewczą przez wężownicę zasobnika. Atrybuty rozbijają liczbę na `after_heating_start` i `after_heating_stop` oraz podają `all_drops_24h` do porównania. Jeśli liczba rośnie z każdym cyklem grzania, także w nocy, przyczyną jest kocioł; wypróbuj **Nie wyłączaj ogrzewania między fazami PWM**.
- Z termostatami pokojowymi albo grzejnikowymi: **Otwarte pętle** oraz **Pętle do wyregulowania**, gdzie dla każdego pokoju jest udział doby z otwartym zaworem, o ile pokój był cieplejszy albo chłodniejszy od średniej z pokoi, przepływ jego pętli (znany, gdy pętla była widziana i otwarta, i zamknięta) oraz podpowiedź do rotametru (`reduce`, `increase`, `ok`). Podpowiedź zakłada, że pokoje mają być jednakowo ciepłe. `base_flow_lpm` to przepływ wszystkiego, czego nigdy nie widziano zamkniętego: pętli bez siłownika i pokoi, których zawór nigdy się nie zamknął, nie da się od siebie odróżnić.
- **Temperatura wymiennika** ( tylko OpenTherm Gateway przez port szeregowy): temperatura wymiennika głównego kotła, identyfikator danych OpenTherm 34 (w Lumei pozycja 08 menu informacyjnego na panelu). Termostaty rzadko o nią pytają, więc SAT co minutę każe bramce zapytać kocioł wiadomością priorytetową (`PM=34`). Sensor pojawia się po pierwszej odpowiedzi. Kocioł, który nie zna tego identyfikatora, odpowiada Unknown-DataId: po 5 zapytaniach bez wartości SAT zapisuje to w logu i pyta raz na godzinę.
- **Zaniki płomienia**: palenie na ogrzewanie, które kończy się w fazie ON przy zasilaniu niższym o ponad 3 K od nastawy, straciło płomień (kocioł sam zapala się ponownie); nie jest to przerwanie na limicie temperatury, więc nie skraca cyklu PWM i nie wywołuje porady o ochronie przed przegrzaniem. Budżet ciepła kończy blok po 4 zanikach i zachowuje niedostarczone ciepło na następny blok. `flame_losses_24h` w atrybutach termostatu liczy zaniki; wiele dziennie wskazuje na elektrodę jonizacyjną, recyrkulację spalin albo zasilanie gazem.
- **Usterki kotła przy starcie palenia** (tylko OpenTherm Gateway przez port szeregowy): płomień utracony wkrótce po zapłonie może zostawić kod usterki tylko na kilka sekund, a termostaty pokojowe pytają o niego mniej więcej co 45 s. Od każdego zapłonu do czterech minut palenia (albo minuty po zgaśnięciu płomienia) SAT pyta o kod usterki (ID 5) co 10 sekund. Każda usterka zgłoszona przez kocioł, także poza tymi oknami, trafia do logu jako ostrzeżenie i do atrybutu `fault_events` sensora Identyfikatory OpenTherm (czas, kod jak na panelu kotła, flagi; ostatnie 20).
- **Prędkość wentylatora** i **Zadana prędkość wentylatora** ( tylko OpenTherm Gateway przez port szeregowy, Hz): identyfikator danych OpenTherm 35, o który wiele bramek pyta samo. Sensory pojawiają się po pierwszej odpowiedzi. Nastawę przyjętą przez kocioł pokazuje sensor *Nastawa zasilania (Boiler)*; kocioł podnosi nastawę niższą od swojego minimum (ID 49) do tego minimum.
- **Identyfikatory OpenTherm** (sensor diagnostyczny, tylko OpenTherm Gateway przez port szeregowy), wypełniany przyciskiem **Skanuj identyfikatory OpenTherm**: SAT pyta kocioł raz o każdy identyfikator danych, który da się odczytać (PM=<id>, po jednym, w sumie około 10 minut), i wypisuje odpowiedzi: `supported` z surową wartością pokazaną jako liczba bez znaku, f8.8 i dwa bajty (który zapis pasuje, zależy od identyfikatora), `data_invalid` (kocioł zna identyfikator, ale teraz nie ma wartości), `unknown` (Unknown-DataId) i `no_answer`. Identyfikatory, których odczyt niesie flagi termostatu (0, 70, 101), oraz te tylko do zapisu nie są odpytywane. `parameters` wypisuje parametry przezroczyste kotła jako numer: wartość (w kotłach Remeha i De Dietrich to parametry instalatora; numer nie zawsze odpowiada numerowi P na panelu). SAT słyszy je zawsze, gdy przechodzą przez bramkę, także poza skanowaniem: wystarczy otworzyć menu parametrów termostatu pokojowego, a ten odczyta je wszystkie; zmiana zrobiona w termostacie trafia do logu jako `Boiler parameter 12 (OpenTherm TSP) changed: 7 -> 10`. Niektóre bramki same czytają je wszystkie po pytaniu skanowania o ich liczbę (ID 10). Stan to liczba obsługiwanych identyfikatorów. Ostatnie skanowanie jest pamiętane po restarcie; odpowiedź Unknown-DataId na ID 34 kończy pytanie o temperaturę wymiennika. Z pozostałych wartości SAT na razie nie korzysta.
- `suggested_heating_curve_coefficient` w atrybutach termostatu, gdy budżet ciepła jest gotowy: z H i przenikania ciepła podłogi nauczonego w ustabilizowanych paleniach (`floor_heat_transfer_w_per_k`) wyliczana jest temperatura zasilania, jakiej dom potrzebuje przy −15, −5 i 5 °C na zewnątrz, oraz współczynnik krzywej, który do niej pasuje. Przenikanie jest mierzone względem pokoju, a nie wylewki, więc to tylko zgrubna wskazówka. SAT sam nie zmienia krzywej.

Wartości, które zmieniają się z każdym odczytem (zapotrzebowanie na ciepło, kredyt ciepła, średnia dobowa temperatura zewnętrzna, różnica spaliny–powrót), nie są zapisywane w rejestratorze jako atrybuty termostatu, żeby nie rozdmuchiwać bazy danych.

## Komunikaty w Naprawach

Pojawiają się w **Ustawienia → System → Naprawy** (i jako baner na górze Ustawień) i znikają same, gdy przyczyna ustąpi.

| Komunikat | Kiedy |
|---|---|
| Niskie ciśnienie wody | poniżej 0,8 bar przez 10 minut; znika przy 0,9 bar |
| Ciśnienie wody stale spada | średnie dobowe ciśnienie, skorygowane o temperaturę wody, spada o 0,05 bar na tydzień lub więcej przez co najmniej cztery dni, przy stracie 0,1 bar |
| Błąd kotła | kocioł zgłasza błąd przez minutę (z kodem producenta) |
| Kocioł często traci płomień | 6 lub więcej paleń na ogrzewanie straciło płomień w ostatniej dobie; znika przy 2 |
| Ogrzewanie wychładza zasobnik | bez poboru wody zasobnik traci 2 K lub więcej w pierwszych 10 minutach palenia na ogrzewanie (mediana z ostatnich 10 paleń, co najmniej 5); znika przy 1 K. Zwykle zawór trójdrogowy, który wpuszcza wodę grzewczą do wężownicy zasobnika. Atrybut `cylinder_drop_at_heating_start`. Z **licznikiem wody** (menu Ciepła woda) starty przy odkręconym kranie są pomijane, a `cylinder_reheats_24h` i `cylinder_reheats_without_draw_24h` liczą dogrzania zasobnika i te, których nie wyjaśnia zużycie wody |
| Brudny wymiennik ciepła | spaliny ponad 12 K cieplejsze od powrotu w ustabilizowanych paleniach blisko mocy minimalnej, średnio z doby palenia |
| Zasilanie za gorące dla podłogi | tylko podłogówka: zasilanie powyżej **Maksymalnego zasilania dla wylewki** (55 °C) przez 3 minuty podczas ogrzewania; komunikat zostaje na dobę |
| Za mały przepływ wody | tylko podłogówka: zasilanie ponad 20 K cieplejsze od powrotu przez 5 minut w ustabilizowanych paleniach |
| Termin przeglądu kotła | **Ostatni przegląd kotła** plus **Odstęp między przeglądami** |
| Wzrost zużycia gazu | gaz na ogrzewanie z ostatniego tygodnia jest o 30% wyższy, niż wynika z czterech poprzednich tygodni dla tej pogody |

Przy trzech z nich warto wyjaśnić, jak unikają fałszywych alarmów:

- **Spadające ciśnienie.** Ciśnienie w układzie zamkniętym zależy od temperatury wody, więc sam koniec sezonu grzewczego je obniża. SAT uczy się, o ile ciśnienie zmienia się na kelwin, z tego, jak obie wartości wahają się razem w ostatnich dniach, i porównuje dni przy jednej temperaturze. Wzrost o 0,15 bar z dnia na dzień to dolanie wody i początek nowej historii. Palenia na ciepłą wodę i pięć minut po nich są pomijane.
- **Brudny wymiennik.** Przy wyższej mocy spaliny z natury są wyraźnie cieplejsze od powrotu. Liczą się tylko palenia w dolnych 15% zakresu modulacji i tylko ze spalinami poniżej 90 °C (kondensacja). Kocioł, który nie podaje modulacji, nie jest oceniany.
- **Zużycie gazu.** Dzienne zużycie gazu na ogrzewanie rośnie liniowo z różnicą temperatur wewnątrz i na zewnątrz, ale nie od zera: słońce, ludzie i urządzenia grzeją za darmo. Dlatego gaz na stopniodzień rośnie przy każdym ochłodzeniu. SAT dopasowuje tę prostą do czterech poprzednich tygodni i porównuje ostatni tydzień z tym, co prosta przewiduje dla jego pogody; gaz na ciepłą wodę jest pomijany, a tydzień z pogodą odbiegającą o ponad 3 K od tamtych tygodni nie jest oceniany.

## Pomiar pętli

Akcja `sat.measure_loops` (Narzędzia deweloperskie → Akcje) mierzy przepływ wody w każdej pętli grzewczej. Wyłącza wszystkie termostaty pokojowe i uruchamia palnik na mocy minimalnej (do Twojej maksymalnej temperatury zadanej), żeby zmierzyć przepływ bazowy pętli bez siłownika. Potem otwiera pokoje po jednym (temperatura zadana 30 °C) i mierzy przyrost. Każdy krok czeka czas otwarcia zaworów (6 minut, jeśli nie jest ustawiony) plus 5 minut i zbiera 10 ustabilizowanych próbek, więc trwa około 15 minut na pokój. Termostaty wracają do poprzednich ustawień, a wynik przychodzi jako powiadomienie i w atrybucie `loop_measurement`. SAT musi być w trybie grzania; wyłączenie go przerywa pomiar. W trakcie pomiaru nie korzystaj z ciepłej wody.

Ustawienia termostatów są zapisywane, zanim cokolwiek zostanie zmienione. Jeśli Home Assistant zatrzyma się w środku pomiaru, termostaty zostają tak, jak są, i wracają do zapisanych ustawień po następnym starcie, gdy tylko każdy z nich znów będzie dostępny (termostaty Z-Wave potrafią potrzebować kilku minut). Nowy pomiar czeka, aż to się skończy.

## Po restarcie

Po restarcie Home Assistanta albo zmianie opcji zachowują się: liczniki, nauczone straty ciepła z oknem dobowym, nauczony czas dogrzewania, historia ciśnienia, historia gazu, średnia do wyłączania przy cieple (jeśli restart trwał krócej niż 6 godzin), preset Away ustawiony przez obecność, preset Activity ustawiony przez wykrywanie okna (jego 30 minut liczy się od nowa), tydzień ostatniego przegrzewu przeciw legionelli, ustawienia termostatów z trwającego pomiaru pętli, szacowany przepływ wody, różnica spaliny–powrót i oddawanie ciepła przez podłogę. Mierzona godzina budżetu ciepła jest zapisywana co 5 minut i jest kontynuowana po restarcie trwającym do 15 minut.

Uczone od nowa: odczyt kotła na minimalnej modulacji, średnie i przepływy monitora pętli, przenikanie ciepła podłogi, średnie sprawności, kredyt ciepła i bieżący blok budżetu ciepła.

## Test na prawdziwym kotle

Od połowy listopada 2026 dodatki pracują na jednej instalacji: dwupoziomowe mieszkanie 87 m² z 2021 roku w budynku wielorodzinnym (sąsiad z boku i pod spodem), podłogówka w wylewce z 8 pętlami, kocioł De Dietrich Lumea MPX 28/33 BIC (33 kW, minimum około 5 kW, zasobnik 40 l) za bramką OpenTherm Gateway na porcie szeregowym i termostat De Dietrich iSense jako czujnik w pokoju. Całość opisuje [Przykład](example.md). Liczby poniżej pochodzą z historii kotła w Home Assistancie, przy 3–8 °C na zewnątrz.

| | Przed: PWM bez budżetu ciepła (16–17 listopada) | Z budżetem ciepła (20–22 listopada) |
|---|---|---|
| Starty palnika na ogrzewanie | około 27 na dobę | 8–10 na dobę |
| Typowe palenie na ogrzewanie | 2–3 minuty, dwie trzecie krótsze niż 5 | 12–23 minuty, mniej więcej jeden blok co 2 godziny |
| Temperatura zasilania | do granicy 45 °C | 35–44 °C; spaliny 2–3 K nad powrotem (pełna kondensacja) |
| Palenia krótsze niż 5 minut | około 18 na dobę | 1–2 na dobę, głównie zaniki płomienia; 19 listopada, przed poprawką dla 25 °C, 16 |
| Temperatura w pokoju przy docelowej 22 °C | | 21,6–22,3 °C |

Dogrzewania zasobnika to decyzja kotła i zostały na poziomie 11–16 na dobę, po 2–3 minuty.

Co pokazał dopiero prawdziwy kocioł i co się przez to zmieniło:

- **Kocioł podnosi niską nastawę do swojego minimum.** Przy ogrzewaniu włączonym między blokami Lumea zamieniała nastawę 10 °C na 25 °C i zapalała się na kilka sekund, gdy woda do niej wystygła. SAT odczytuje teraz to minimum (ID 49 i nastawę potwierdzoną przez kocioł) i wyłącza ogrzewanie 1 K nad nim (5.2.0.27–28).
- **Dogrzewanie zasobnika bez flagi.** Lumea często grzeje zasobnik, nie zgłaszając tego. SAT rozpoznaje takie palenia po wodzie i nie liczy ich jako ogrzewania ani przerwań.
- **Zaniki płomienia.** Mniej więcej co czwarty start na ogrzewanie tracił płomień w ciągu kilku minut, a kocioł zapalał się sam. Na początku SAT brał to za przerwania i kończył bloki. Teraz je rozróżnia i liczy (`flame_losses_24h`). Blok kończy się dopiero po 4 zanikach, a przy 6 na dobę pojawia się komunikat w Naprawach (5.2.0.29–30). Przyczyna jest wciąż niewyjaśniona, potrzebna jest wizyta serwisu.
- **Wspólna nauka strat i słońca nie działała.** Z jednej doby danych słońce rosło do granicy 3 kW, a H spadało. Teraz są uczone z osobnych godzin (5.2.0.30). Efektywne straty mieszkania wyszły 45–55 W/K, mniej niż wynikałoby z samych ścian, bo dochodzi ciepło od sąsiadów.
- **Restart wyglądał jak otwarte okno**, bo pierwsze odczyty skaczą. Teraz przez pierwsze 10 minut po starcie okno nie jest wykrywane (5.2.0.30).
- **Modulacja przy rozgrzewaniu nic nie dawała.** OpenTherm pozwala tylko ograniczyć maksymalną modulację, a Lumea i tak schodzi na minimum w 90 sekund. Usunąłem ją razem z dynamiczną minimalną nastawą, którą budżet uczynił zbędną (5.2.0.30–31).
- **Ogrzewanie wychładza zasobnik.** W nocnych logach zasobnik tracił 3–4 K w ciągu kilku minut od każdego startu ogrzewania, choć nikt nie odkręcał wody, a kocioł od razu go dogrzewał. SAT teraz to mierzy i zgłasza w Naprawach (5.2.0.31). Prawdopodobna przyczyna to zawór trójdrogowy, który przełącza się nieczysto.
- **Odczyt kotła.** Przez OpenTherm Lumea odpowiada na 28 identyfikatorów danych, podaje parametry instalatora (ID 10/11), prędkość wentylatora (ID 35) i kody usterek, ale nie temperaturę wymiennika (ID 34), liczniki ani prąd jonizacji.

## Ograniczenia i to, czego nie sprawdzono

- Sprawdzone: testy jednostkowe i integracyjne w CI (ruff ze wszystkimi regułami, ty, pytest, hassfest), symulacje budżetu ciepła na dwuwęzłowym modelu wylewki i pokoju oraz około tygodnia na jednym prawdziwym kotle ([Test na prawdziwym kotle](#test-na-prawdziwym-kotle)): budżet ciepła z nauką, utrzymanie ogrzewania między blokami, śledzenie płomienia, ciepłej wody i usterek, skanowanie i parametry OpenTherm, wykrywanie okna i komunikaty w Naprawach, z prognozą Met.no.
- Niesprawdzone: inne kotły i marki; połączenia MQTT, ESPHome i EMS; cały sezon grzewczy (mrozy, przekazanie modulacji przy przeciążeniu); harmonogram komfortu, obecność, harmonogram ciepłej wody i przegrzew przeciw legionelli, ochrona przed zamarzaniem i nauka wiatru, których instalacja testowa jeszcze nie używa albo które doszły na końcu; pomiar pętli na prawdziwych siłownikach; dokładność szacunków sprawności, gazu i przepływu (w testowym mieszkaniu nie ma gazomierza w Home Assistancie).
- Szacunki są szacunkami: opierają się na mocy palnika, własnych czujnikach kotła i podręcznikowych wartościach spalania.
- Brak migracji wpisu konfiguracji: powrót do oryginalnego SAT v2 to kwestia podmiany plików.

---

Wróć: [README](../../README.pl.md) · Zobacz też: [Opcje](options.md) · [Jak działa SAT](how-it-works.md)
