# Opcje

🇬🇧 [English version](../options.md)

Otwórz stronę integracji i kliknij **Konfiguruj**. Ustawienia są podzielone na menu:

- [Krzywa grzewcza i PID](#krzywa-grzewcza-i-pid)
- [Tryby (presety)](#tryby-presety)
- [Sterowanie i PWM](#sterowanie-i-pwm)
- [Budżet ciepła](#budżet-ciepła)
- [Ciepła woda](#ciepła-woda)
- [Obecność i okna](#obecność-i-okna)
- [Kocioł i serwis](#kocioł-i-serwis)

Menu budżetu ciepła, ciepłej wody i obecności nie ma w trybie przełącznika (termostat PID włącz/wyłącz). Niektóre pola pojawiają się tylko wtedy, gdy dotyczą Twojej instalacji. Wartości domyślne pasują do większości domów.

Od wersji 5.2.0.32 ustawienia mają polskie nazwy, gdy Home Assistant jest po polsku. W nawiasach podane są nazwy angielskie. Ustawienia dodane przez ten fork oznaczone są ⓜ i wyjaśnione na stronie [Dodatki MPX](mpx.md).

## Krzywa grzewcza i PID

- **Regulator PID** (PID controller): Klasyczny, Ulepszony albo Adaptacyjny (domyślnie). Adaptacyjny stroi się sam; Klasyczny i Ulepszony korzystają z siły automatycznych wzmocnień.
- **Tryb grzania** (Heating mode): tylko z dodanymi pomieszczeniami. *Komfort* grzeje pod pomieszczenie, któremu najwięcej brakuje do temperatury docelowej, *Eko* tylko pod główne.
- **Maksymalna temperatura zasilania** (Maximum flow temperature): najgorętsza woda, o jaką SAT poprosi. Dla grzejników 55–75 °C, dla podłogówki 50 °C. Nie może być niższa od wartości ochrony przed przegrzaniem.
- **Wartość ochrony przed przegrzaniem** (Overshoot protection value): najniższa temperatura zasilania, jaką kocioł utrzymuje na minimalnej mocy. Ustawia ją [kalibracja](how-it-works.md#kalibracja) albo wpisujesz ją ręcznie. SAT wysyła ją w fazach palenia PWM.
- **Współczynnik krzywej grzewczej** (Heating curve coefficient): nachylenie [krzywej grzewczej](how-it-works.md#krzywa-grzewcza) (domyślnie 2,0). Zwiększ, gdy w mrozy jest za zimno, zmniejsz, gdy dom się przegrzewa.
- **Siła automatycznych wzmocnień** (Automatic gains value): jak mocno reagują regulatory Klasyczny i Ulepszony (domyślnie 2,0). Dobrze sprawdza się wartość równa współczynnikowi krzywej.
- **Waga czasowa członu różniczkującego** (Derivative time weight): jak SAT tłumi szybkie zmiany (domyślnie 2,5).
- **Proporcjonalne, Całkujące, Różniczkujące** (kP, kI, kD): własne wartości PID, widoczne, gdy automatyczne wzmocnienia są wyłączone.
- **Maksymalny cykl PWM** (Maximum PWM duty cycle): długość [cyklu przy małym obciążeniu](how-it-works.md#sterowanie-przy-małym-obciążeniu), gdy automatyczny cykl jest wyłączony (domyślnie 13 minut).
- **Czujniki okien i drzwi** (Window and door sensors): gdy któryś jest otwarty dłużej niż minimalny czas otwarcia, SAT przełącza się na tryb Aktywność, a po zamknięciu wraca do poprzedniej temperatury.

## Tryby (presety)

Temperatury docelowe od 5 do 35 °C:

| Tryb | Domyślnie |
|---|---|
| Aktywność (Activity; także przy otwartym oknie) | 10 °C |
| Poza domem (Away) | 10 °C |
| Sen (Sleep) | 15 °C |
| W domu (Home) | 18 °C |
| Komfort (Comfort) | 20 °C |

- **Przekazuj tryb termostatom pokojowym** (Pass the preset to the room thermostats): tryby Sen, Poza domem i Aktywność trafiają też do termostatów pokojowych.
- **Przekazuj temperaturę docelową termostatowi kotła** (Pass the target to the boiler's thermostat): termostat podłączony do kotła ma tę samą temperaturę docelową i przejmuje sterowanie, gdy Home Assistant przestanie działać.

## Sterowanie i PWM

- **Automatyczny cykl PWM** (Automatic PWM duty cycle): SAT sam dobiera długość [cyklu przy małym obciążeniu](how-it-works.md#sterowanie-przy-małym-obciążeniu). Po wyłączeniu długość pochodzi z menu Krzywa grzewcza i PID.
- **Cykle PWM na godzinę** (PWM cycles per hour): najwięcej startów palnika na godzinę. 3 albo 4 dla grzejników, 2 albo 3 dla pomp ciepła, ⓜ od 1 do 4 dla podłogówki (2 dla przewymiarowanego kotła). Budżet ciepła robi ich mniej.
- **Przekazuj tryb pracy termostatom pokojowym** (Pass the mode to the room thermostats): włączenie albo wyłączenie SAT robi to samo z podłączonymi termostatami.
- **Tryb po starcie bez zapisanego stanu** (Mode after a start without saved state): Grzanie albo Wyłączony, np. przy pierwszym uruchomieniu.
- ⓜ **Ochrona przed zamarzaniem przy wyłączonym SAT** (Frost protection while off): gdy SAT jest wyłączony, a w pokoju jest tak zimno, kocioł grzeje wodą 30 °C, aż będzie o 1 °C cieplej (domyślnie 6 °C; 0 wyłącza). Nie ma jej w trybie przełącznika.
- **Maksymalny wiek odczytu temperatury** (Maximum age of a temperature reading): starszy odczyt oznacza, że czujnik przestał raportować (domyślnie 6 godzin).
- **Minimalny czas otwarcia okna** (Minimum time a window is open): jak długo czujnik okna musi być otwarty, zanim grzanie zostanie wstrzymane (domyślnie 15 sekund).

### Zaawansowane

Sekcja jest domyślnie zwinięta.

- **Zawsze używaj PWM** (Always use PWM): cykle przy małym obciążeniu także wtedy, gdy kocioł mógłby zmodulować wystarczająco nisko. Tylko OpenTherm.
- ⓜ **Ucz się wartości ochrony przed przegrzaniem** (Learn the overshoot protection value, domyślnie wyłączone): [szczegóły](mpx.md#ustawienia-kotła). Bieżącą wartość pokazuje atrybut `minimum_setpoint`. Tylko OpenTherm.
- ⓜ **Przerwane palenia, po których kończy się faza PWM** (Cut-short burns before a PWM on-phase ends): ile paleń kocioł może sam przerwać w jednej fazie (domyślnie 2; dla przewymiarowanego kotła na podłogówce 1).
- **Maksymalna modulacja** (Maximum modulation): ogranicza moc kotła, w procentach (domyślnie 100).
- **Próg otwarcia zaworu termostatu pokojowego** (Room thermostat valve offset): dla termostatów, które nie podają, czy grzeją. Pokój chce ciepła, gdy jest co najmniej o tyle poniżej swojej temperatury docelowej (domyślnie 0).
- **Krok temperatury docelowej** (Target temperature step): domyślnie 0,5 °C.
- **Okres próbkowania PID** (PID sample time): najkrótszy czas między dwoma przeliczeniami PID (domyślnie 1 minuta).
- **Kalibracja: czekanie na płomień** i **czekanie na stałe zasilanie** (Calibration: wait for the flame / for a steady flow): jak długo [kalibracja](how-it-works.md#kalibracja) czeka na zapłon (domyślnie 10 minut) i na ustalenie temperatury wody (domyślnie 40 minut, co najmniej 5).
- **Temperatura odczuwalna** (Felt temperature): steruje według temperatury odczuwalnej (Summer Simmer Index) z temperatury i wilgotności. Wymaga czujnika wilgotności.
- **Symulacja** (Simulation): SAT wszystko liczy, ale nic nie wysyła do kotła.

## Budżet ciepła

ⓜ Dla wolnych instalacji, np. podłogówki w wylewce. [Szczegóły](mpx.md#budżet-ciepła).

> [!WARNING]
> Kod napisany przez AI i sprawdzany tylko na jednym kotle, zobacz [Dodatki MPX](mpx.md#test-na-prawdziwym-kotle). Przy wartościach domyślnych SAT steruje kotłem tak jak oryginalny SAT v2.

- **Budżet ciepła** (Heat budget): Wyłączony (domyślnie), Tylko nauka albo Włączony. Włączony steruje tylko ogrzewaniem podłogowym.
- **Straty ciepła domu** (Heat loss of the house): w W/K; 0 oznacza naukę (domyślnie, zalecane).
- **Okres** (Period): co tyle przybywa kredytu ciepła (domyślnie 60 minut).
- **Minimalne palenie** (Minimum burn): najkrótszy blok wart zapłonu (domyślnie 10 minut).
- **Prognoza pogody** (Weather forecast): encja pogody z prognozą godzinową; jej prędkość wiatru służy do nauki wpływu wiatru (np. Met.no albo Open-Meteo). Czujnik z samymi bieżącymi wartościami, np. Airly, się nie nadaje.
- ⓜ **Horyzont prognozy** (Forecast horizon): ile godzin do przodu liczy się prognozowana temperatura zewnętrzna (domyślnie 3). Wylewka oddaje ciepło przez wiele godzin; przy 6–8 budżet zaczyna grzać przed mroźną nocą.
- **Harmonogram komfortu** i **Obniżenie poza harmonogramem** (Comfort schedule / Setback outside the schedule): pomocnik harmonogramu włączony w godzinach komfortu i to, o ile chłodniej jest poza nimi (domyślnie 0).
- **Wyłączenie przy ciepłej pogodzie** (Warm weather shutdown): średnia dobowa temperatura zewnętrzna, przy której ogrzewanie się wyłącza (domyślnie 0: nigdy).

## Ciepła woda

ⓜ Dla kotłów, które przyjmują temperaturę ciepłej wody przez OpenTherm. [Szczegóły](mpx.md#ciepła-woda).

- **Temperatura ciepłej wody** (Hot water temperature): domyślnie 0, czyli ciepłą wodą zajmuje się kocioł.
- **Temperatura eko** (Eco temperature) i **Harmonogram ciepłej wody** (Hot water schedule): poza godzinami harmonogramu obowiązuje temperatura eko.
- **Licznik wody** (Water meter): licznik całkowitego zużycia wody (litry albo m³) do kontroli zasobnika: pomija starty ogrzewania przy odkręconym kranie i liczy dogrzania, których nie wyjaśnia zużycie wody.
- **Dzień przegrzewu (legionella)** i **Godzina przegrzewu** (Legionella boost day / start): domyślnie wyłączone.

## Obecność i okna

ⓜ [Szczegóły](mpx.md#harmonogramy-i-obecność).

- **Obecność** (Presence): kto liczy się jako obecny w domu. Po 30 minutach nieobecności wszystkich SAT przełącza się na Poza domem.
- **Odległość od domu** i **Odległość powrotu** (Distance to home / Return distance): opcjonalny czujnik z integracji Proximity i to, jak blisko ktoś musi być, żeby grzanie wróciło.
- **Wykrywaj otwarte okna po temperaturze** (Detect open windows from the temperature): domyślnie wyłączone.

## Kocioł i serwis

ⓜ [Szczegóły](mpx.md#ustawienia-kotła) i [Monitoring](mpx.md#monitoring).

- **Nie wyłączaj ogrzewania między fazami PWM** (Keep heating enabled between PWM on-phases, domyślnie wyłączone): dla kotłów dwufunkcyjnych, w których wybieg pompy wychładza zasobnik. Nie ma go w trybie przełącznika.
- **Blokada ponownego zapłonu w kotle** (Boiler anti-cycling time): własna przerwa kotła przed ponownym zapłonem z ustawień instalatora (domyślnie 0: nieustawiona).
- **Czas otwarcia siłowników** (Valve opening time): ile otwierają się siłowniki termostatów pokojowych (domyślnie 0: kocioł zapala się od razu).
- **Maksymalne zasilanie dla wylewki** (Maximum flow for the screed): tylko podłogówka (domyślnie 55 °C; 0 wyłącza).
- **Kocioł kondensacyjny** (Condensing boiler, domyślnie włączone): do szacowania sprawności bez czujnika spalin.
- **Zużycie gazu na minimalnej i maksymalnej mocy** (Gas use at minimum / maximum power): z instrukcji kotła, w m³/h. SAT szacuje z nich zużycie gazu oraz moc palnika, gdy kocioł jej nie podaje. Tylko OpenTherm.
- **Ciepło z metra sześciennego gazu** (Heat per cubic metre of gas): domyślnie 10,2 kWh/m³ dla gazu ziemnego, około 24 dla propanu. Tylko OpenTherm.
- **Cena gazu za metr sześcienny** (Gas price per cubic metre): dodaje sensor kosztu gazu (domyślnie 0: wyłączone).
- **Ostatni przegląd kotła** i **Odstęp między przeglądami** (Last boiler service / Service interval): do przypomnienia o przeglądzie w Naprawach.

---

Wróć: [Konfiguracja](setup.md) · Dalej: [Jak działa SAT](how-it-works.md)
