# Smart Autotune Thermostat v2 — edycja MPX

[![hacs][hacs-badge]][hacs-url]
![build][build-badge]

🇬🇧 [English version](README.md)

> [!WARNING]
> **Kod eksperymentalny, napisany przez AI i niesprawdzony. Używasz na własne ryzyko.**
>
> Dodatki w tym forku (wersje z czwartą liczbą, np. `5.2.0.5`) napisał
> [Claude](https://claude.ai), model AI firmy Anthropic, w rozmowie z właścicielem forka.
> Przechodzą testy automatyczne (testy jednostkowe, ruff, ty, hassfest), ale **nikt ich nie
> sprawdził ręcznie ani nie uruchamiał dłużej na prawdziwym kotle**. Sterują kotłem gazowym:
> błąd może oznaczać zimny dom, zmarnowany gaz, przegrzaną podłogę albo blokadę kotła.
> Przeczytaj kod, zanim go użyjesz, zrób kopię zapasową, obserwuj kocioł po instalacji i miej
> pod ręką oryginalny [SAT v2](https://github.com/bellini666/SAT), żeby móc do niego wrócić.
> Autorzy SAT nie mają z tymi dodatkami nic wspólnego i ich nie popierają.

SAT to inteligentny termostat dla Home Assistanta, który steruje kotłem.

Zwykły termostat włącza i wyłącza kocioł, a kocioł grzeje wodę do stałej, często wysokiej temperatury. SAT wylicza najniższą temperaturę wody, która utrzyma w domu temperaturę zadaną, na podstawie temperatury zewnętrznej i tego, ile brakuje w każdym pokoju, i wysyła ją do kotła. Chłodniejsza woda to mniej gazu i mniej włączeń kotła.

Ten fork powstał na bazie [SAT v2 Thiago Belliniego Ribeiro](https://github.com/bellini666/SAT), który sam jest forkiem oryginalnego [Smart Autotune Thermostat](https://github.com/Alexwijn/SAT) autorstwa [Alexa Wijnholdsa](https://github.com/Alexwijn). Został napisany dla przewymiarowanego kotła kondensacyjnego z zasobnikiem (De Dietrich Lumea, 33 kW, minimum około 5 kW) pracującego na ogrzewanie podłogowe w wylewce, za bramką OpenTherm Gateway. Dodaje to, czego taka instalacja potrzebuje, żeby kocioł przestał taktować i zużywał mniej gazu. Wszystko, co nowe, jest wyłączone albo tylko informuje, dopóki tego nie włączysz.

## Co dodaje ten fork

Wszystko jest opisane na stronie [Dodatki MPX][mpx].

**Sterowanie** (domyślnie wyłączone)
- 🔋 **Budżet ciepła**: uczy się strat ciepła domu i spala ciepło potrzebne na każdą godzinę w jednym długim bloku na mocy minimalnej, zamiast w kilku krótkich cyklach PWM. Oddaje sterowanie zwykłej modulacji, gdy dom potrzebuje więcej niż moc minimalna.
- 🌤️ **Prognoza pogody i słońce**: budżet ciepła uwzględnia trend z prognozy, wysokość słońca i zachmurzenie.
- ⏰ **Harmonogram komfortu** z nauczonym wcześniejszym dogrzewaniem i wcześniejszym zakończeniem.
- ☀️ **Wyłączanie ogrzewania przy cieple** według średniej dobowej temperatury zewnętrznej.
- 🚿 **Harmonogram ciepłej wody** z temperaturą ekonomiczną i cotygodniowym przegrzewem przeciw legionelli.
- 🏃 **Obecność**: preset Away, gdy nikogo nie ma, i wcześniejszy powrót grzania w zadanej odległości od domu.
- 🪟 **Wykrywanie otwartego okna** po szybkim spadku temperatury, bez czujników otwarcia.
- ⚙️ Ustawienia dla konkretnego kotła: czas antytaktowania, czas otwarcia zaworów, liczba przerwanych paleń w fazie PWM, utrzymanie ogrzewania włączonego między fazami PWM, uczona wartość ochrony przed przegrzaniem.

**Monitoring** (włączony, tylko informuje)
- 📈 Liczniki do panelu Energia: starty i godziny pracy palnika, ciepło na ogrzewanie i ciepłą wodę, gaz, stopniodni grzania, koszt gazu.
- 🍃 **Szacowana sprawność kotła** z temperatury spalin albo powrotu.
- 💧 **Szacowany przepływ wody**, otwarte pętle i podpowiedź do rotametru dla każdego pokoju; akcja `sat.measure_loops` mierzy przepływ każdej pętli.
- 🚨 Komunikaty w Naprawach: niskie lub spadające ciśnienie wody, błąd kotła, brudny wymiennik, przegrzanie wylewki, za mały przepływ, termin przeglądu, wzrost zużycia gazu.
- 📐 Sugerowany współczynnik krzywej grzewczej na podstawie tego, czego SAT się nauczył.

## Czego potrzebujesz

- **Home Assistant 2026.11 lub nowszy.**
- Kocioł, z którym Home Assistant może się porozumieć przez:
  - [OpenTherm Gateway (OTGW)](https://otgw.tclcode.com/), po MQTT albo łączu szeregowym
  - [ESPHome OpenTherm](https://esphome.io/components/opentherm.html)
  - [EMS-ESP](https://emsesp.org/), po MQTT
  - adaptery OpenTherm, takie jak [DIYLess](https://diyless.com/) Master OpenTherm Shield, adapter [Ihora Melnyka](http://ihormelnyk.com/opentherm_adapter) albo nakładka Arduino [Jiříego Prausa](https://www.tindie.com/products/jiripraus/opentherm-gateway-arduino-shield/)
- Albo dowolny `switch`, `valve` lub `input_boolean`, który włącza i wyłącza ogrzewanie. SAT działa wtedy jako inteligentny termostat dwustanowy (większość dodatków wymaga kotła, który przyjmuje temperaturę zadaną).
- Czujnik temperatury w pokoju oraz czujnik temperatury zewnętrznej albo encja pogody.

Dodatki powstawały dla OTGW w trybie szeregowym. Pozostałe połączenia korzystają z tego samego kodu, ale były sprawdzane jeszcze mniej.

## Instalacja

Najpierw **zrób kopię zapasową** Home Assistanta i zanotuj obecne ustawienia SAT.

### Przez HACS

1. Jeśli SAT albo SAT v2 jest już zainstalowany przez HACS, otwórz go w HACS i wybierz **⋮ → Usuń**. Usuwa to pliki, a nie Twój wpis SAT i jego ustawienia. Jeszcze nie restartuj.
2. W HACS wybierz **⋮ → Niestandardowe repozytoria** i dodaj `https://github.com/alnamics/sat` z typem **Integracja**.
3. Otwórz w HACS **Smart Autotune Thermostat v2 (MPX)** i wybierz **Pobierz**. Dopóki fork nie ma wydań, HACS instaluje aktualny stan gałęzi `main` i jako wersję pokazuje jej commit.
4. Zrestartuj Home Assistanta.

[![Otwórz repozytorium w HACS w swoim Home Assistancie.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=alnamics&repository=sat&category=integration)

Domena integracji to nadal `sat`, więc istniejący wpis zachowuje ustawienia, a edycja MPX zajmuje miejsce dotychczasowego SAT. HACS może mieć zainstalowany tylko jeden z nich naraz.

### Ręcznie

Pobierz repozytorium (**Code → Download ZIP** na [GitHubie][repository]), skopiuj z niego folder `custom_components/sat` do swojego folderu `custom_components`, zastępując istniejący SAT, i zrestartuj Home Assistanta.

Nową instalację dodasz potem w **Ustawienia → Urządzenia oraz usługi → Dodaj integrację → Smart Autotune Thermostat**; [przewodnik po konfiguracji][setup] prowadzi przez każdy krok.

### Bezpieczne wdrażanie

1. Przez dzień lub dwa zostaw wszystkie nowe opcje wyłączone. SAT steruje wtedy kotłem tak jak oryginalny SAT v2; dochodzą tylko nowe sensory i komunikaty w Naprawach. Sprawdź logi pod kątem `sat` i wykresy kotła.
2. Włącz ustawienia kotła, które znasz (czas antytaktowania, czas otwarcia zaworów).
3. Ustaw budżet ciepła na **Learn only (shadow)** na dwa–trzy dni. Gdy `heat_budget_ready` ma wartość true, a sensor strat ciepła domu się ustabilizuje, przełącz na **On**.
4. Pozostałe funkcje włączaj po jednej, żeby było widać, co robi każda z nich.

### Powrót do oryginału

W HACS usuń edycję MPX i pobierz ponownie SAT v2 (albo ręcznie skopiuj oryginał do `custom_components/sat`), a potem zrestartuj. Ten fork nie dodaje własnej migracji wpisu konfiguracji, więc SAT v2 w wersji 5.2.0 lub nowszej wczyta wpis ponownie. Starszy SAT tego nie zrobi, bo Home Assistant nie wczytuje wpisu zapisanego przez nowszą wersję. Dodatkowe opcje są ignorowane, a dodatkowe encje zostają osierocone (usuniesz je w **Ustawienia → Encje**).

## Dokumentacja

- [Dodatki MPX][mpx]: każdy dodatek tego forka, co robi, jakie ma wartości domyślne i ograniczenia
- [Konfiguracja][setup]: o co pyta każdy krok konfiguracji
- [Opcje][options]: każde ustawienie, zakładka po zakładce
- [Jak działa SAT][how-it-works]: krzywa grzewcza, korekta z pokoju, sterowanie przy małym obciążeniu, budżet ciepła i kalibracja
- [Różnice względem oryginalnego SAT][differences]

Nazwy ustawień w interfejsie integracji są po angielsku, dlatego dokumentacja podaje je w oryginale.

## Autorzy

SAT to dzieło [Alexa Wijnholdsa](https://github.com/Alexwijn), [Thiago Belliniego Ribeiro](https://github.com/bellini666) i współtwórców. Dodatki MPX napisał Claude dla [alnamics](https://github.com/alnamics); problemy z nimi zgłaszaj tutaj, a nie autorom oryginału.

<!-- Badges -->

[hacs-url]: https://hacs.xyz/docs/faq/custom_repositories/
[hacs-badge]: https://img.shields.io/badge/hacs-custom-orange.svg?style=for-the-badge
[build-badge]: https://img.shields.io/github/actions/workflow/status/alnamics/sat/pytest.yml?branch=main&style=for-the-badge

<!-- References -->

[repository]: https://github.com/alnamics/sat
[mpx]: docs/pl/mpx.md
[setup]: docs/pl/setup.md
[options]: docs/pl/options.md
[how-it-works]: docs/pl/how-it-works.md
[differences]: docs/pl/differences.md
