# Przykład: mieszkanie 87 m² z podłogówką i kotłem 33 kW

🇬🇧 [English version](../example.md)

> [!WARNING]
> Opis i liczby pochodzą z pierwszych tygodni pracy tego forka na jednej instalacji (listopad 2026).
> Kod napisał Claude, model AI; nie był sprawdzany przez człowieka. Wartości w innym domu będą inne.
> Przed i po: [Test na prawdziwym kotle](mpx.md#test-na-prawdziwym-kotle).

Ta strona pokazuje na jednym konkretnym mieszkaniu, co SAT robi z kotłem: kiedy i jak długo pali, co robi w przerwach, jak radzi sobie z ciepłą wodą i zanikami płomienia oraz czego uczy się o domu. Opis ogólny jest w [Jak działa SAT](how-it-works.md) i [Dodatki MPX](mpx.md).

- [Instalacja](#instalacja)
- [Problem: kocioł za duży dla domu](#problem-kocioł-za-duży-dla-domu)
- [Budżet ciepła: ile i kiedy](#budżet-ciepła-ile-i-kiedy)
- [Blok z bliska](#blok-z-bliska)
- [Przerwa między blokami](#przerwa-między-blokami)
- [Ciepła woda i zasobnik](#ciepła-woda-i-zasobnik)
- [Zaniki płomienia](#zaniki-płomienia)
- [Pętle i termostaty pokojowe](#pętle-i-termostaty-pokojowe)
- [Okno, awaria, ochrona wylewki](#okno-awaria-ochrona-wylewki)
- [Co pokazują sensory](#co-pokazują-sensory)
- [Ustawienia tej instalacji](#ustawienia-tej-instalacji)

## Instalacja

| | |
|---|---|
| Mieszkanie | 87 m² w bloku, budynek oddany w 2021 roku |
| Kocioł | De Dietrich Lumea MPX 28/33 BIC, kondensacyjny, z zasobnikiem 40 l (płyta tej samej rodziny co Baxi Luna Duo-Tec) |
| Moc kotła | 33 kW, minimum **4,7–5,1 kW** według danych technicznych; SAT liczy 33 kW × 16% = 5,3 kW |
| Ogrzewanie | podłogówka w wylewce, 8 pętli |
| Pętle | 4 z siłownikami Afriso (5–6 minut) i termostatami Heatit Z-Temp2, 4 zawsze otwarte |
| Połączenie | OpenTherm Gateway (OTGW) z modułem Ethernet, przez port szeregowy |
| Termostat | De Dietrich AD289 iSense na OpenTherm, przez bramkę; jego temperatura (0,1 °C) to główny czujnik SAT |

Parametry kotła (numer z iSense; na panelu kotła o jeden większy). SAT odczytuje je przez OpenTherm (sensor *Identyfikatory OpenTherm*):

| P | Znaczenie | Wartość |
|---|---|---|
| P09 | nastawa grzania z termostatu (OpenTherm) | 00 |
| P12 | maks. moc c.o. | 0 (około 5 kW, fabrycznie 80) |
| P13 | maks. moc c.w.u. | 39% (około 16 kW, fabrycznie 100) |
| P15 | maks. temperatura c.o. | 01 = 45 °C |
| P16 | wybieg pompy po c.o. | 1 min |
| P17 | blokada ponownego zapłonu w c.o. | 10 min |
| P30 | minimalna nastawa z termostatu | 25 °C |

## Problem: kocioł za duży dla domu

Przy 5–12 °C na zewnątrz mieszkanie potrzebuje na ogrzewanie **7–20 kWh na dobę**, czyli średnio 0,3–0,8 kW. Kocioł nie zejdzie poniżej 5,3 kW, więc zawsze musi pracować z przerwami. Moc 33 kW dobrano pod ciepłą wodę.

Mieszkanie w bloku dostaje sporo darmowego ciepła: od sąsiadów, ludzi, sprzętów i ciepłego zasobnika. Dlatego potrzeba jest mniejsza, niż wynikałoby ze strat przez ściany i okna. SAT uczy się **efektywnych** strat (tu 45–55 W/K), czyli tego, ile ciepła dom naprawdę potrzebuje od kotła.

Cel SAT: **mało startów, długie palenia na minimalnej mocy, jak najchłodniejsza woda.**

## Budżet ciepła: ile i kiedy

Krzywa grzewcza i PID nadal są liczone, ale dopóki budżet jest gotowy, nie sterują palnikiem.

1. **Potrzeba.** *H × (22 °C − temp. zewnętrzna) − słońce + korekta za błąd pokoju.* Każde 0,1 °C za ciepło lub za zimno zmienia potrzebę o około 40 W; część całkująca powoli wyrównuje to, czego model nie widzi.
2. **Kredyt.** Co godzinę potrzeba trafia do kredytu, a ciepło z palnika (bez ciepłej wody) go zmniejsza.
3. **Blok.** Gdy kredyt i potrzeba na godzinę dadzą co najmniej 10 minut palenia na minimum, rusza blok. Przy 0,4–0,6 kW wychodzi blok 12–15 minut co 2–3 godziny.
4. **Nauka.** Co godzinę zapisuje ciepło, różnicę temperatur, słońce i zmianę temperatury w pokoju. Straty liczy z godzin bez słońca, a zysk ze słońca osobno z godzin słonecznych.

Pokój ≥ 0,5 °C za ciepły nie dostaje nic; po obniżeniu celu budżet czeka, aż pokój zejdzie na 0,2 °C od nowego celu.

## Blok z bliska

| Czas | Co się dzieje |
|---|---|
| 0:00 | SAT wysyła 45 °C (ochrona przed przegrzaniem) i maks. modulację 0% |
| 0:05 | zapłon: modulacja 41%, wentylator 58 Hz (około 3500 obr/min) |
| 0:30–1:30 | kocioł sam schodzi z mocą: wentylator 40 → 33 → 24 → **19 Hz** (minimum, około 1150 obr/min) |
| 3:00 | zasilanie 35–40 °C, powrót 30–35 °C, spaliny kilka K nad powrotem: pełna kondensacja |
| 12:00–15:00 | blok dostarczył zaplanowane ciepło, SAT wysyła 10 °C, płomień gaśnie |

Woda nie dochodzi do 45 °C, więc kocioł nie przerywa palenia na limicie temperatury. Przez pierwsze 4 minuty SAT co 10 sekund pyta kocioł o kod usterki.

## Przerwa między blokami

- SAT wysyła 10 °C, kocioł podnosi to do swojego minimum **25 °C** (P30).
- **Ogrzewanie zostaje włączone** (*Nie wyłączaj ogrzewania między fazami PWM*): pompa krąży, a zawór trójdrogowy nie przełącza się na zasobnik po każdym bloku. Bez tego zasobnik tracił 2–3 K przy każdym cyklu i dogrzewał się kilka razy w nocy.
- Woda stygnie z około 35 do 26 °C. **Przy 26 °C SAT wyłącza ogrzewanie do następnego bloku**, bo przy 25 °C kocioł zapaliłby się na kilkanaście sekund.
- Jeśli kocioł mimo to zapali się w przerwie (np. gdy skończy mu się 10-minutowa blokada), krótkie palenie też wyłącza ogrzewanie do następnego bloku.

## Ciepła woda i zasobnik

- Kocioł ma pierwszeństwo c.w.u. i sam decyduje o dogrzaniu zasobnika (do 45 °C, moc do około 16 kW z P13). W 4 dni było 51 dogrzań, zwykle po 1,5–4 minuty.
- **Dogrzewanie bez flagi:** Lumea nie zawsze zgłasza grzanie wody. SAT rozpoznaje je po wodzie, która w 20 sekund rośnie o ponad 10 °C ponad nastawę.
- **Przejęcie:** gdy zasobnik potrzebuje ciepła w trakcie bloku, kocioł przerywa grzanie i dogrzewa zasobnik. SAT nie liczy tego jako przerwania ani zaniku płomienia, a blok trwa dalej po dogrzaniu.
- **Poranne prysznice:** czujnik zasobnika schodzi wtedy do 28–34 °C, bo 16 kW nie nadąża za poborem. Jeśli woda pod koniec prysznica robi się letnia, pomoże większe P13 (np. 60–70%) albo nastawa 50 °C.

## Zaniki płomienia

W 4 dni płomień zgasł w **10 z 39 startów** ogrzewania (26%). Kocioł zapala się ponownie po około 23 sekundach, czasem 3–4 razy pod rząd. Zaniki zdarzały się przy zimnym i przy ciepłym kotle, głównie wieczorem i rano, częściej w deszczu (36% wobec 20%). To wskazuje na spalanie: ciśnienie gazu w godzinach szczytu, recyrkulację spalin albo elektrodę jonizacyjną.

SAT:
- odróżnia zanik (zasilanie ponad 3 K poniżej nastawy) od przerwania na limicie temperatury;
- kończy blok dopiero po 4 zanikach, a niedostarczone ciepło przechodzi na następny blok;
- liczy zaniki w `flame_losses_24h` i przy 6 na dobę zgłasza komunikat w Naprawach.

Przez OpenTherm Lumea nie zgłasza tych zaników kodem usterki. Historię usterek widać tylko na panelu kotła (P32–P41).

## Pętle i termostaty pokojowe

Termostaty Z-Temp2 działają jak ograniczniki (sypialnia 22 °C, reszta 23 °C), a SAT reguluje według iSense. Z termostatów korzysta do:

- sprawdzenia, czy jakaś pętla przyjmie ciepło: przy wszystkich zamkniętych kocioł nie pali, a budżet nie nalicza kredytu;
- sensorów *Open loops* i *Loops to rebalance* oraz podpowiedzi do rotametrów;
- pomiaru pętli (`sat.measure_loops`).

## Okno, awaria, ochrona wylewki

- **Okno:** spadek o 0,3 °C w 30 minut albo o 0,8 °C w 10 minut wstrzymuje grzanie (preset Activity) na 30 minut po ostatnim spadku, najwyżej na 2 godziny. Przez 10 minut po starcie i przy skoku odczytu o ponad 1,5 °C SAT tego nie robi.
- **Awaria Home Assistanta:** po kilku minutach bramka oddaje kocioł iSense, który utrzymuje własną nastawę. Dlatego na iSense warto mieć stałe 20–21 °C, a nie 16 °C.
- **Wylewka:** kocioł ma maksimum 45 °C (P15), a SAT ostrzega, gdy zasilanie przez ponad 3 minuty przekracza 55 °C.

## Co pokazują sensory

Wartości z 21 listopada (+5 °C na zewnątrz):

| Sensor / atrybut | Wartość | Co znaczy |
|---|---|---|
| `heat_loss_w_per_k` | około 50 | efektywne straty domu |
| `heat_need_kw` | 0,76 | potrzeba w tej chwili |
| `heat_block_minutes` | 13 | długość następnego bloku |
| `flame_losses_24h` | 2–6 | zaniki płomienia w ostatniej dobie |
| `flue_return_gap` | 2,7 K | czysty wymiennik, pełna kondensacja |
| *Prędkość wentylatora* | 19–58 Hz | 19 Hz to minimum, 58 Hz zapłon |
| *Estimated water flow* | około 15 l/min | przy otwartych pętlach |
| *Identyfikatory OpenTherm* | 28 | identyfikatory, na które kocioł odpowiada; atrybuty: parametry kotła i kody usterek |

Lumea nie podaje liczników startów i godzin (ID 116–123 nieznane), temperatury wymiennika (34) ani prądu jonizacji (36). SAT liczy starty, godziny, ciepło i gaz sam.

## Ustawienia tej instalacji

| Menu → ustawienie | Wartość | Dlaczego |
|---|---|---|
| Instalacja grzewcza | Ogrzewanie podłogowe | wylewka |
| Krzywa grzewcza i PID → Tryb grzania | Eko | regulacja według iSense |
| Krzywa grzewcza i PID → Wartość ochrony przed przegrzaniem | 45 °C | skok przy zapłonie nie przerywa palenia |
| Kocioł i serwis → Blokada ponownego zapłonu w kotle | 10 min | tyle samo co P17 w kotle |
| Kocioł i serwis → Czas otwarcia siłowników | 6 min | siłowniki Afriso |
| Kocioł i serwis → Nie wyłączaj ogrzewania między fazami PWM | włączone | jedno dogrzanie zasobnika na noc zamiast pięciu |
| Budżet ciepła → Budżet ciepła | Włączony | bloki 12–15 min co 2–3 godziny |
| Budżet ciepła → Straty ciepła domu | 0 (nauka) | stała wartość tylko jako zabezpieczenie, wtedy około 45 W/K |
| Budżet ciepła → Wyłączenie przy ciepłej pogodzie | włączone | ogrzewanie wyłącza się przy ciepłej średniej dobowej |
| Obecność i okna → Wykrywaj otwarte okna po temperaturze | włączone | iSense podaje 0,1 °C |
| Kocioł i serwis → Ostatni przegląd kotła | przegląd do 1.10.2027 | przypomnienie w Naprawach |

Zalecane ustawienia termostatów Z-Temp2: raport co 300 s (parametr 1) i przy zmianie o 0,5 °C (parametr 2), histereza 0,5 °C (parametr 10).
