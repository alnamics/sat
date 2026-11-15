# Konfiguracja

🇬🇧 [English version](../setup.md)

Dodaj SAT w **Ustawienia → Urządzenia oraz usługi → Dodaj integrację** i wyszukaj „Smart Autotune Thermostat”. Jeśli SAT znajdzie w sieci albo na brokerze MQTT bramkę OpenTherm Gateway lub EMS-ESP, pojawi się tam także jako wykryte urządzenie.

Konfiguracja pyta o:

1. [Połączenie](#połączenie)
2. [Czujniki](#czujniki)
3. [System grzewczy](#system-grzewczy)
4. [Strefy](#strefy)
5. [Kalibrację](#kalibracja)
6. [Producenta](#producent)

**Skonfiguruj ponownie** na stronie integracji uruchamia te kroki jeszcze raz, od czujników. Wszystko inne jest w [Opcjach](options.md).

Ekrany konfiguracji są po angielsku, dlatego nazwy pól podane są w oryginale.

## Połączenie

Wybierz, jak SAT komunikuje się z kotłem:

| Wybór | Do czego | Co wpisujesz |
|---|---|---|
| MQTT Gateway | OTGW albo EMS-ESP po MQTT | Tryb (OpenTherm albo EMS-ESP), nazwę i temat MQTT. Dla OTGW także identyfikator urządzenia (`otgw-XXXXXXXXXXXX`). |
| Serial Gateway | OTGW po łączu szeregowym albo sieci | Nazwę i adres URL bramki |
| ESPHome | Urządzenie ESPHome OpenTherm | Nazwę i urządzenie |
| PID Thermostat | `switch`, `valve` albo `input_boolean` | Nazwę, encję i temperaturę wody, z jaką pracuje ogrzewanie (domyślnie 50 °C) |
| Simulated Gateway | Tylko do programowania | |

Dla OTGW temat MQTT to *MQTT Top Topic* z ustawień firmware OTGW. Dla EMS-ESP to temat bazowy EMS-ESP.

### ESPHome

Wybierz główne urządzenie ESPHome, a nie jedno z jego urządzeń podrzędnych. SAT znajduje encje OpenTherm po nazwie, więc YAML ESPHome musi używać dokładnie tych nazw:

<details>
<summary>Minimalny YAML dla ESPHome</summary>

```yaml
# Tu wstaw zwykłą konfigurację esphome (board, api, ota itd.)

opentherm:
  in_pin: # wstaw pin wejściowy
  out_pin: # wstaw pin wyjściowy
  ch_enable: true
  dhw_enable: true

number:
  - platform: opentherm
    t_dhw_set:
      name: t_dhw_set
      step: 1
      restore_value: true
      initial_value: 45
    t_set:
      name: t_set
      restore_value: true
      initial_value: 10
    max_t_set:
      name: max_t_set
      step: 1
      restore_value: true
    max_rel_mod_level:
      name: max_rel_mod_level
      min_value: 0
      max_value: 100
      step: 1
      initial_value: 100
      restore_value: true

sensor:
  - platform: opentherm
    rel_mod_level:
      name: rel_mod_level
    device_id:
      name: device_id
    t_boiler:
      name: t_boiler
    t_ret:
      name: t_ret
    max_capacity:
      name: max_capacity
    min_mod_level:
      name: min_mod_level
    t_dhw_set_lb:
      name: t_dhw_set_lb
    t_dhw_set_ub:
      name: t_dhw_set_ub

binary_sensor:
  - platform: opentherm
    flame_on:
      name: flame_on
    dhw_active:
      name: dhw_active

switch:
  - platform: opentherm
    dhw_enable:
      name: dhw_enable
    ch_enable:
      name: ch_enable
```

Pozostałe encje wymienia [dokumentacja ESPHome OpenTherm](https://esphome.io/components/opentherm.html).

</details>

## Czujniki

- **Inside sensor**: temperatura pokoju, którym steruje SAT. Najlepiej działa czujnik podający dwa miejsca po przecinku i aktualizujący się co 30 sekund.
- **Outside sensor**: czujnik temperatury albo encja pogody. Możesz wybrać kilka, a SAT użyje pierwszego, który ma odczyt.
- **Humidity sensor** (opcjonalnie): używany tylko przez [Thermal Comfort](options.md#advanced).

## System grzewczy

Grzejniki, ogrzewanie podłogowe albo pompa ciepła. Od tego zależy [krzywa grzewcza](how-it-works.md#krzywa-grzewcza) i początkowe ustawienia PID, więc wybierz to, co masz. Termostat dwustanowy pomija ten krok.

## Strefy

Pomiń ten krok, jeśli SAT jest Twoim jedynym termostatem.

- **Thermostat**: termostat ścienny. Gdy zmienisz jego temperaturę zadaną, SAT pójdzie za nią.
- **Radiators**: termostaty grzejnikowe (głowice) w tym samym pokoju co czujnik wewnętrzny.
- **Rooms**: termostaty w innych pokojach, każdy z własną temperaturą zadaną. SAT grzeje, gdy którykolwiek z nich woła o ciepło.

Gdy dodane są pokoje, [Heating Mode](options.md#general) decyduje, czy SAT grzeje też pod pozostałe pokoje, czy tylko pod główny.

## Kalibracja

Tylko dla OpenTherm i EMS-ESP. Wybierz jedno:

- **Calibrate and determine your overshoot protection value** (zalecane): SAT uruchamia kocioł na najniższej mocy i mierzy temperaturę wody, na której się ustala. Trwa to do około 50 minut. Zobacz [Kalibracja](how-it-works.md#kalibracja).
- **Manually enter the overshoot protection value**: jeśli już znasz tę wartość. [Ta dyskusja](https://github.com/Alexwijn/SAT/discussions/36) wyjaśnia, jak znaleźć ją ręcznie.
- **Manually enter PID values**: niezalecane. Tylko dla osób, które znają się na strojeniu PID.

Kalibrację możesz powtórzyć w dowolnej chwili przyciskiem **Calibrate overshoot protection**.

Termostat dwustanowy pyta zamiast tego o **Automatic Gains**. Zostaw je włączone albo wyłącz i wpisz wartości PID w [Opcjach](options.md#general).

## Producent

Gdy SAT pyta o producenta kotła, podpowiada tego, którego wykrył. Zmień go, jeśli się pomylił, bo niektóre marki wymagają specjalnej obsługi.

---

Dalej: [Opcje](options.md) · [Jak działa SAT](how-it-works.md)
