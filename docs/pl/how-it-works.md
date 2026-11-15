# Jak działa SAT

🇬🇧 [English version](../how-it-works.md)

SAT decyduje, jak gorąca ma być woda płynąca do grzejników albo podłogi, i przekazuje to kotłowi. Współpracują ze sobą trzy części: krzywa grzewcza, korekta z pokoju i sterowanie przy małym obciążeniu.

## Krzywa grzewcza

Krzywa grzewcza zamienia temperaturę zewnętrzną na temperaturę wody: im zimniej na zewnątrz, tym cieplejsza woda. Gdy na zewnątrz jest tak ciepło jak temperatura zadana, krzywa robi się płaska.

**Heating Curve Coefficient** ustala, jak stroma jest krzywa. Gdy jest dobrana do domu, temperatura w pokoju trzyma się blisko zadanej przy niewielkiej pomocy korekty z pokoju. Zwiększ współczynnik, jeśli w zimne dni w domu jest za zimno, zmniejsz, jeśli dom się przegrzewa.

SAT używa jednej krzywej z innym przesunięciem dla ogrzewania podłogowego. Możesz się nią pobawić tutaj (*a* to współczynnik, *b* temperatura zadana w pokoju):

- [Grzejniki i pompy ciepła](https://www.desmos.com/calculator/spfvsid4ds)
- [Ogrzewanie podłogowe](https://www.desmos.com/calculator/i7f7uuyaoz)

> [!TIP]
> Żeby pokazać wykres na dashboardzie, dodaj kartę iframe:
> ```yaml
> type: iframe
> url: https://www.desmos.com/calculator/spfvsid4ds
> allow_open_top_navigation: true
> allow: fullscreen
> aspect_ratio: 130%
> ```

## Korekta z pokoju

Krzywa daje wynik zbliżony do potrzebnego, a resztę robi regulator PID. Porównuje temperaturę w pokoju z zadaną i podnosi albo obniża temperaturę wody, aż się zrównają.

Regulator PID potrzebuje trzech ustawień, zwanych wzmocnieniami. Z włączonym **Automatic Gains** (domyślnie) SAT ustawia je za Ciebie:

- Regulator **Adaptive** (domyślny) stroi je w trakcie pracy.
- Regulatory **Classic** i **Improved** uzależniają je od krzywej grzewczej, więc działają mocniej, gdy na zewnątrz robi się zimniej.

Możesz też wyłączyć Automatic Gains i wpisać własne wartości w [Opcjach](options.md#general). Warto to robić tylko wtedy, gdy znasz się na strojeniu PID.

Przy kilku pokojach [Heating Mode](options.md#general) decyduje, których pokoi SAT słucha.

## Sterowanie przy małym obciążeniu

Każdy kocioł ma moc minimalną. W łagodne dni dom potrzebuje mniej ciepła, więc kocioł przegrzewa wodę, wyłącza się i po kilku minutach startuje ponownie. Takie taktowanie marnuje gaz i zużywa kocioł.

Gdy temperatura wody, której chce SAT, jest niższa od tej, którą kocioł potrafi utrzymać, SAT przechodzi na zaplanowane cykle (modulacja szerokości impulsu, PWM): przez część każdego cyklu kocioł pracuje z niską temperaturą wody, a potem odpoczywa. Udział czasu pracy zależy od tego, ile ciepła potrzebuje dom. Z włączonym Automatic duty cycle (domyślnie) cykl to godzina podzielona przez [liczbę cykli na godzinę](options.md#system-configuration), czyli 15 minut przy 4 cyklach na godzinę.

Niska temperatura wody, z którą kocioł wtedy pracuje, to **wartość ochrony przed przegrzaniem** (overshoot protection value), którą mierzy [kalibracja](#kalibracja).

Termostat dwustanowy (switch, valve albo input_boolean) zawsze działa w ten sposób, bo nie może ustawić temperatury wody.

## Budżet ciepła (MPX)

> [!WARNING]
> Część dodatków tego forka, napisanych przez AI i niesprawdzonych. Zobacz [Dodatki MPX](mpx.md).

Przy ogrzewaniu podłogowym w wylewce i przewymiarowanym kotle PWM nadal zapala kocioł kilka razy na godzinę. Budżet ciepła zastępuje wypełnienie cyklu bilansem energii: SAT uczy się, ile watów dom traci na każdy stopień różnicy temperatur wewnątrz i na zewnątrz, wylicza ciepło potrzebne na następną godzinę z temperatury zadanej, temperatury zewnętrznej, prognozy i słońca, i spala je w jednym bloku na mocy minimalnej. Powolna podłoga nie zauważa różnicy, a kocioł startuje kilka razy rzadziej na godzinę. Gdy dom potrzebuje więcej niż moc minimalna, sterowanie wraca do krzywej grzewczej i modulacji kotła. Szczegóły na stronie [Dodatki MPX](mpx.md#budżet-ciepła).

## Kalibracja

Wartość ochrony przed przegrzaniem to temperatura wody, na której kocioł się ustala, gdy pracuje na najniższej mocy. SAT mierzy ją tak:

1. Ustawia kocioł na najniższą moc i prosi o 62 °C (grzejniki), 45 °C (podłogówka) albo 40 °C (pompa ciepła), nie więcej niż Twoja maksymalna temperatura zadana.
2. Ustawia termostaty grzejnikowe i pokojowe na grzanie, żeby woda miała dokąd płynąć.
3. Czeka, aż temperatura wody przestanie się zmieniać, i zapisuje ją jako wartość.
4. Przywraca termostaty do poprzednich ustawień i wraca do zwykłego sterowania.

Na zapłon palnika czeka do 10 minut, a na ustabilizowanie temperatury wody do 40 minut. Oba czasy można zmienić w [opcjach zaawansowanych](options.md#advanced). Jeśli kalibracja się nie uda, SAT podaje przyczynę, a przy przekroczeniu czasu także najwyższą osiągniętą temperaturę.

Uruchom ją podczas konfiguracji albo w dowolnej chwili przyciskiem **Calibrate overshoot protection**. Jeśli wciąż się nie udaje, [ta dyskusja](https://github.com/Alexwijn/SAT/discussions/36) wyjaśnia, jak znaleźć wartość ręcznie.

## Gdy coś pójdzie nie tak

Z bramką OpenTherm Gateway SAT oddaje sterowanie podłączonemu do niej termostatowi, gdy:

- SAT zostanie wyłączony, integracja zostanie wyładowana albo Home Assistant się zatrzyma
- czujnika, którego SAT potrzebuje, brakuje od 10 minut

Przejmuje sterowanie z powrotem, gdy wszystko wróci.

## Monitoring (MPX)

Ten fork prowadzi też liczniki (starty, godziny pracy palnika, ciepło, gaz, koszt, stopniodni), szacuje sprawność kotła i przepływ wody, obserwuje pętle w pokojach i zgłasza w Naprawach spadające ciśnienie, brudny wymiennik, przegrzaną podłogę i inne problemy. Zobacz [Dodatki MPX](mpx.md#monitoring).

## Więcej do poczytania

[Ten wpis w dyskusjach](https://github.com/Alexwijn/SAT/discussions/40) autorstwa critictidier opisuje SAT dogłębnie, z prawdziwymi obserwacjami (po angielsku).

---

Wróć: [Opcje](options.md) · Zobacz też: [Konfiguracja](setup.md)
