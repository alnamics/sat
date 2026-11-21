# Opcje

🇬🇧 [English version](../options.md)

Otwórz stronę integracji i kliknij **Konfiguruj**. Ustawienia są w trzech menu: [General](#general), [Presets](#presets) i [System Configuration](#system-configuration). Niektóre ustawienia pojawiają się tylko wtedy, gdy dotyczą Twojej instalacji.

Nazwy ustawień w interfejsie są po angielsku, dlatego tutaj podane są w oryginale.

Wartości domyślne pasują do większości domów.

Ustawienia dodane przez ten fork są wymienione w sekcji [Zaawansowane: dodatki MPX](#zaawansowane-dodatki-mpx) i wyjaśnione na stronie [Dodatki MPX](mpx.md).

## General

- **PID Controller Version**: Classic, Improved albo Adaptive (domyślnie). Adaptive stroi się sam. Classic i Improved korzystają z ustawienia Automatic Gains Value poniżej.
- **Heating Mode**: tylko gdy dodane są pokoje. *Comfort* grzeje pod pokój, któremu najwięcej brakuje do temperatury zadanej. *Eco* grzeje tylko pod główny pokój.
- **Maximum Setpoint**: najgorętsza woda, o jaką SAT może poprosić. Dla grzejników pasuje 55–75 °C, dla ogrzewania podłogowego 50 °C. Wyższa wartość szybciej nagrzewa dom. Nie może być niższa od wartości ochrony przed przegrzaniem.
- **Overshoot protection value**: najniższa temperatura wody, jaką kocioł potrafi utrzymać. Ustawia ją [kalibracja](how-it-works.md#kalibracja) albo wpisujesz ją ręcznie.
- **Heating Curve Coefficient**: jak stroma jest [krzywa grzewcza](how-it-works.md#krzywa-grzewcza) (domyślnie 2,0). Zwiększ, jeśli w zimne dni w domu jest za zimno, zmniejsz, jeśli dom się przegrzewa.
- **Automatic Gains Value**: jak mocno reagują regulatory Classic i Improved (domyślnie 2,0). Dobrze sprawdza się wartość równa współczynnikowi krzywej grzewczej.
- **Derivative Time Weight**: dostraja, jak SAT tłumi szybkie zmiany (domyślnie 2,5).
- **Proportional, Integral, Derivative**: własne wartości PID, widoczne, gdy Automatic Gains jest wyłączone.
- **Maximum Duty Cycle for Pulse Width Modulation**: długość [cyklu przy małym obciążeniu](how-it-works.md#sterowanie-przy-małym-obciążeniu), gdy Automatic duty cycle jest wyłączone (domyślnie 13 minut).
- **Contact Sensors**: czujniki otwarcia drzwi i okien. Gdy któryś jest otwarty dłużej niż minimalny czas otwarcia, SAT przełącza się na preset Activity, a po zamknięciu przywraca poprzednią temperaturę zadaną.

## Presets

Temperatury zadane od 5 do 35 °C:

| Preset | Domyślnie |
|---|---|
| Activity (Aktywność; używany także przy otwartym oknie) | 10 °C |
| Away (Poza domem) | 10 °C |
| Sleep (Sen) | 15 °C |
| Home (W domu) | 18 °C |
| Comfort (Komfort) | 20 °C |

- **Synchronize climates with preset**: stosuje presety Sleep, Away i Activity także do termostatów pokojowych.
- **Synchronize with thermostat attached to the boiler**: wysyła temperaturę zadaną SAT do termostatu ściennego.

## System Configuration

- **Automatic duty cycle**: SAT sam dobiera długość [cyklu przy małym obciążeniu](how-it-works.md#sterowanie-przy-małym-obciążeniu) z liczby cykli na godzinę. Po wyłączeniu długość pochodzi z menu General.
- **Duty Cycles per hour**: największa liczba cykli kotła na godzinę. 3 albo 4 dla grzejników, 2 albo 3 dla pomp ciepła, od 1 do 4 dla ogrzewania podłogowego (dla przewymiarowanego kotła pasuje 2).
- **Synchronize climates with mode**: włączenie albo wyłączenie SAT robi to samo z każdym podłączonym termostatem.
- **Temperature Sensor maximum value age**: jak długo odczyt czujnika uznaje się za aktualny (domyślnie 6 godzin).
- **Mode when nothing can be restored**: czy SAT startuje w trybie grzania, czy wyłączony, gdy nie ma zapisanego stanu, na przykład przy pierwszym uruchomieniu.
- **Minimum time for window to be open**: jak długo czujnik otwarcia musi być otwarty, zanim SAT zareaguje (domyślnie 15 sekund).

### Advanced

Ta sekcja jest domyślnie zwinięta.

- **Thermal Comfort**: steruje według temperatury odczuwalnej (Summer Simmer Index), wyliczanej z temperatury i wilgotności. Wymaga czujnika wilgotności.
- **Force Pulse Width Modulation**: zawsze używa [cykli przy małym obciążeniu](how-it-works.md#sterowanie-przy-małym-obciążeniu), nawet gdy kocioł sam utrzymałby temperaturę. Tylko OTGW.
- **Minimum Consumption** i **Maximum Consumption**: zużycie gazu przez kocioł na najniższej i najwyższej mocy, z instrukcji kotła. SAT szacuje z nich zużycie gazu oraz moc palnika, gdy kocioł nie podaje swojej mocy.
- **Climate valve offset**: dla termostatów pokojowych, które nie informują, czy grzeją. Pokój liczy się jako wołający o ciepło, gdy jest co najmniej o tyle poniżej swojej temperatury zadanej (domyślnie 0).
- **Target Temperature Step**: krok temperatury zadanej SAT (domyślnie 0,5 °C).
- **Maximum Relative Modulation**: ogranicza moc kotła, w procentach (domyślnie 100).
- **Sample Time**: najkrótszy czas między dwiema aktualizacjami PID (domyślnie 1 minuta).
- **Calibration flame timeout** i **Calibration plateau timeout**: jak długo [kalibracja](how-it-works.md#kalibracja) czeka na zapłon palnika (domyślnie 10 minut) i na ustabilizowanie temperatury wody (domyślnie 40 minut, co najmniej 5).

### Zaawansowane: dodatki MPX

> [!WARNING]
> Kod napisany przez AI i niesprawdzony, zobacz [Dodatki MPX](mpx.md). Przy wartościach domyślnych SAT steruje kotłem tak jak oryginalny SAT v2.

Poniżej jest tylko to, czym jest każde ustawienie; jak działają funkcje, wyjaśnia strona [Dodatki MPX](mpx.md). Te ustawienia też są w sekcji Advanced.

**Kocioł** ([szczegóły](mpx.md#ustawienia-kotła))

- **Heat per cubic metre of gas**: ile kWh daje kotłowi metr sześcienny gazu (domyślnie 10,2 dla gazu ziemnego; około 24 dla propanu).
- **Condensing boiler** (domyślnie włączone): do szacowania sprawności kotła, który nie podaje temperatury spalin. Wyłącz dla kotła niekondensacyjnego.
- **Cut-short burns before ending the PWM on-phase**: ile paleń kocioł może sam przerwać w jednym cyklu przy małym obciążeniu, zanim SAT zakończy fazę ON (domyślnie 2; dla przewymiarowanego kotła na podłogówce 1).
- **Boiler anti-cycling time**: własny czas oczekiwania kotła przed ponownym zapłonem, z ustawień instalatora (domyślnie 0: nie ustawiono).
- **Learn overshoot protection value** (domyślnie wyłączone): koryguje skalibrowaną wartość na podstawie tego, jak kończą się palenia przy małym obciążeniu, w zakresie od 30 °C do maksymalnej temperatury zadanej minus 3 °C. Bieżącą wartość pokazuje atrybut `minimum_setpoint`.
- **Valve opening time**: ile trwa otwarcie siłowników termostatów pokojowych (domyślnie 0: zapalaj kocioł od razu).
- **Keep heating enabled between PWM on-phases** (domyślnie wyłączone): dla kotłów dwufunkcyjnych, w których wybieg pompy wychładza zasobnik ciepłej wody. Niedostępne w trybie przełącznika.
- **Duty Cycles per hour**: ogrzewanie podłogowe może zejść do 1.

**Budżet ciepła** ([szczegóły](mpx.md#budżet-ciepła))

- **Heat budget**: `Off` (domyślnie), `Learn only (shadow)` albo `On`. `On` steruje tylko ogrzewaniem podłogowym.
- **Heat budget period**: jeden blok grzania na okres (domyślnie 60 minut).
- **Heat budget minimum burn**: najkrótszy blok wart zapłonu (domyślnie 10 minut).
- **Heat loss of the house**: straty ciepła domu w W/K; 0 oznacza naukę (domyślnie).
- **Weather forecast**: encja pogody z prognozą godzinową (na przykład Met.no albo Open-Meteo). Używa jej także wyłączanie ogrzewania przy cieple. Czujnik podający tylko bieżące wartości, taki jak Airly, się tu nie nadaje.
- **Comfort schedule** i **Setback**: pomocnik harmonogramu, który jest włączony w godzinach komfortu, oraz to, o ile temperatura zadana spada poza nimi (domyślnie 0: bez obniżenia).

**Harmonogramy i obecność** ([szczegóły](mpx.md#harmonogramy-i-obecność))

- **Warm weather shutdown**: średnia dobowa temperatura zewnętrzna, przy której centralne ogrzewanie się wyłącza (domyślnie 0: nigdy).
- **Presence**, **Distance to home** i **Return distance**: kto liczy się jako obecny w domu, opcjonalny czujnik odległości z integracji Proximity oraz to, jak blisko ktoś musi być, żeby ogrzewanie wróciło.
- **Detect open windows from the temperature** (domyślnie wyłączone).

**Ciepła woda** ([szczegóły](mpx.md#ciepła-woda))

- **Hot water temperature** (domyślnie 0: zostaw ciepłą wodę kotłowi), **Hot water eco temperature** i **Hot water schedule**.
- **Legionella boost day** (domyślnie wyłączone) i **start**.

**Monitoring** ([szczegóły](mpx.md#monitoring))

- **Maximum flow for the screed**: tylko ogrzewanie podłogowe (domyślnie 55 °C; 0 wyłącza sprawdzanie).
- **Last boiler service** i **Service interval**: do przypomnienia o przeglądzie.
- **Gas price per cubic metre**: dodaje sensor kosztu gazu (domyślnie 0: wyłączone).

---

Wróć: [Konfiguracja](setup.md) · Dalej: [Jak działa SAT](how-it-works.md)
