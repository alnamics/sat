# Różnice względem oryginalnego SAT

🇬🇧 [English version](../differences.md)

> [!NOTE]
> Ta strona opisuje, czym SAT v2 autorstwa bellini666 różni się od oryginalnego SAT. Dodatki
> tego forka, napisane przez AI, są opisane osobno na stronie [Dodatki MPX](mpx.md).

SAT v2 to fork [Alexwijn/SAT](https://github.com/Alexwijn/SAT) autorstwa [Alexa Wijnholdsa](https://github.com/Alexwijn), odgałęziony od commita [`7d43560`](https://github.com/Alexwijn/SAT/commit/7d43560) oryginału. Każdą zmianę pokazuje [historia commitów](https://github.com/bellini666/SAT/compare/7d43560...main).

Domena integracji to nadal `sat`, więc SAT v2 zastępuje oryginał w tym samym miejscu. Istniejące wpisy konfiguracji są migrowane przy pierwszym uruchomieniu.

## Bezpieczniejsze sterowanie

- SAT oddaje kocioł jego termostatowi, gdy zostanie wyłączony albo wyładowany, gdy Home Assistant się zatrzyma albo gdy wymaganego czujnika brakuje od 10 minut. Przejmuje sterowanie z powrotem, gdy wszystko wróci.
- OTGW: SAT wstrzymuje pracę, gdy bramka nie ma łączności, i ponownie ustawia kocioł, gdy bramka wróci.
- Po restarcie PID wznawia pracę bez skoku temperatury zadanej.
- Wiek odczytu czujnika liczy się od jego ostatniego raportu, więc stała wartość pozostaje aktualna. Wartości nieliczbowe liczą się jako brak odczytu, a SAT przechodzi do następnego czujnika zewnętrznego.

## Równiejsze grzanie

- PWM ma margines 2 °C przed wyłączeniem (bez dynamicznej minimalnej temperatury zadanej), a limit cykli na godzinę obowiązuje także po resetach.
- Zmiana temperatury zadanej w pokoju i pobór ciepłej wody nie zakłócają cyklu PWM, a zamknięte zawory nie wyłączają PWM.
- Gdy kocioł wciąż przerywa palenia, PWM wcześniej kończy fazę ON.
- Poprawki PID: człon różniczkujący wygasa, zamiast się zawieszać, małe zmiany w obrębie czasu próbkowania nie giną, a systemy podłogowe dostają wzmocnienia dla podłogówki.
- Krzywa grzewcza jest płaska, gdy na zewnątrz jest tak ciepło jak temperatura zadana.

## Kalibracja

- Przycisk **Calibrate overshoot protection** uruchamia ją w dowolnej chwili, w tle.
- Czeka na naprawdę płaską temperaturę zasilania, z ustawianymi limitami czasu, i wyjaśnia, dlaczego się nie udała.
- Wartość można edytować w opcjach.
- Termostaty pokojowe są na czas kalibracji ustawiane na grzanie, a potem przywracane. Pobór ciepłej wody ją wstrzymuje.

## Monitorowanie kotła

- Nowe encje: błąd kotła, kod błędu kotła, problem ze sterowaniem ogrzewaniem.
- Ostrzeżenia o taktowaniu i przegrzaniu liczą tylko palenia na ogrzewanie przerwane przez kocioł. Palenia na ciepłą wodę, także te, których kocioł nie oznacza, są pomijane.
- Statystyki płomienia przetrwają restart, a przerwa w łączności z bramką nie liczy się jako koniec palenia.
- Sensory mają długoterminowe statystyki z poprawnymi jednostkami, a często zmieniające się atrybuty nie trafiają do rejestratora.

## Konfiguracja i opcje

- Ustawienia zaawansowane to zwinięta sekcja w System Configuration, zawsze dostępna.
- Nowa opcja: „Mode when nothing can be restored”.
- Producent jest podpowiadany, konfiguracja ponawia próby, aż MQTT będzie dostępne, i można pobrać diagnostykę.
- Usunięcie wpisu usuwa jego zapisane dane.

## Platforma

- Wymaga Home Assistanta 2026.11 lub nowszego i `pyotgw>=2.2.3`.
- Nowoczesne narzędzia: zależności zarządzane przez `uv`, lint i formatowanie przez `ruff` (wszystkie reguły), sprawdzanie typów przez `ty`.
- Kod w pełni otypowany.
- 223 testy zamiast 7, wszystkie uruchamiane w CI razem z hassfest i walidacją HACS.
