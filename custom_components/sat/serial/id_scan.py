"""Find out which OpenTherm data IDs the boiler answers.

After a start SAT asks the boiler for every readable data ID once, through the gateway's priority
message (PM=<id>), and records the answer: Read-Ack with a value, Data-Invalid (the ID is known but
has no value now) or Unknown-DataId. pyotgw drops the answers it does not decode, so the scan
listens to the raw messages for its duration.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

_LOGGER: logging.Logger = logging.getLogger(__name__)

READ_ACK = 4
WRITE_ACK = 5
DATA_INVALID = 6
UNKNOWN_DATA_ID = 7

SUPPORTED = "supported"
INVALID = "invalid"
UNKNOWN = "unknown"
NO_ANSWER = "no_answer"

# A read of these carries the thermostat's own flags or is write-only: reading them with zero data
# would, for one message, tell the boiler heating and hot water are off. They are never asked.
NEVER_ASKED = frozenset({0, 1, 2, 4, 7, 8, 14, 16, 23, 24, 37, 70, 71, 101, 124, 126})
SCANNED_IDS: tuple[int, ...] = tuple(i for i in range(1, 128) if i not in NEVER_ASKED)

# The gateway sends a priority message at its next free slot, within a few seconds
ANSWER_TIMEOUT_SECONDS = 15.0
PAUSE_SECONDS = 1.0

FRAME_LENGTH = 8
VENTILATION_IDS = range(71, 92)
SOLAR_STORAGE_IDS = range(102, 109)

# OpenTherm 2.2 to 4.x names; manufacturers may use some IDs differently
NAMES: dict[int, str] = {
    3: "Slave configuration",
    5: "Fault flags / OEM fault code",
    6: "Remote parameter flags",
    9: "Remote override room setpoint",
    10: "Number of transparent parameters",
    11: "Transparent parameter entry",
    12: "Number of fault history entries",
    13: "Fault history entry",
    15: "Maximum capacity / minimum modulation",
    17: "Relative modulation level",
    18: "Central heating water pressure",
    19: "Hot water flow rate",
    20: "Day of week and time",
    21: "Date",
    22: "Year",
    25: "Boiler water temperature",
    26: "Hot water temperature",
    27: "Outside temperature",
    28: "Return water temperature",
    29: "Solar storage temperature",
    30: "Solar collector temperature",
    31: "Central heating 2 flow temperature",
    32: "Hot water 2 temperature",
    33: "Exhaust temperature",
    34: "Heat exchanger temperature",
    35: "Fan speed (setpoint / actual)",
    36: "Flame current",
    38: "Relative humidity",
    39: "Remote override room setpoint 2",
    48: "Hot water setpoint bounds",
    49: "Maximum heating setpoint bounds",
    50: "Heating curve ratio bounds",
    56: "Hot water setpoint",
    57: "Maximum heating water setpoint",
    58: "Heating curve ratio",
    93: "Brand name",
    94: "Brand version",
    95: "Brand serial number",
    96: "Cooling operation hours",
    97: "Power cycles",
    98: "RF sensor status",
    99: "Remote override operating mode",
    100: "Remote override function",
    109: "Electricity producer starts",
    110: "Electricity producer hours",
    111: "Electricity production",
    112: "Cumulative electricity production",
    113: "Unsuccessful burner starts",
    114: "Flame signal too low",
    115: "OEM diagnostic code",
    116: "Burner starts",
    117: "Heating pump starts",
    118: "Hot water pump/valve starts",
    119: "Hot water burner starts",
    120: "Burner hours",
    121: "Heating pump hours",
    122: "Hot water pump/valve hours",
    123: "Hot water burner hours",
    125: "Slave OpenTherm version",
    127: "Slave product version",
}


def describe(data_id: int) -> str:
    """Return the ID with its OpenTherm name."""
    if (name := NAMES.get(data_id)) is not None:
        return f"{data_id} {name}"
    if data_id in VENTILATION_IDS:
        return f"{data_id} Ventilation / heat recovery"
    if data_id in SOLAR_STORAGE_IDS:
        return f"{data_id} Solar storage"
    return str(data_id)


def decode(raw: str) -> str:
    """Show a 16-bit value in the ways OpenTherm uses it; which one applies depends on the ID."""
    value = int(raw, 16)
    high, low = value >> 8, value & 0xFF
    signed = value - 0x10000 if value & 0x8000 else value
    return f"{raw} (u16 {value}, f8.8 {signed / 256:.2f}, hb {high}, lb {low})"


@dataclass(slots=True)
class Answer:
    kind: str
    raw: str | None = None


class OpenThermIdScan:
    """Ask the boiler for each data ID and keep its answers."""

    def __init__(self, ids: tuple[int, ...] = SCANNED_IDS) -> None:
        self._ids = ids
        self.answers: dict[int, Answer] = {}
        self.running = False
        self.finished = False
        self._waiting: int | None = None
        self._answered = asyncio.Event()

    def observe(self, source: str, frame: str) -> None:
        """Record a raw message from the gateway (source letter and 8 hex digits)."""
        if source != "B" or len(frame) != FRAME_LENGTH:
            return
        try:
            data = bytes.fromhex(frame)
        except ValueError:
            return

        message_type = (data[0] >> 4) & 0x7
        data_id = data[1]
        if message_type in (READ_ACK, WRITE_ACK):
            answer = Answer(SUPPORTED, frame[4:].upper())
        elif message_type == DATA_INVALID:
            answer = Answer(INVALID)
        elif message_type == UNKNOWN_DATA_ID:
            answer = Answer(UNKNOWN)
        else:
            return

        # The boiler's answers to the thermostat count too; a later value replaces an older one
        previous = self.answers.get(data_id)
        if previous is None or previous.kind != SUPPORTED or answer.kind == SUPPORTED:
            self.answers[data_id] = answer

        if data_id == self._waiting:
            self._answered.set()

    async def async_run(
        self,
        ask: Callable[[int], Awaitable[Any]],
        answer_seconds: float = ANSWER_TIMEOUT_SECONDS,
        pause: float = PAUSE_SECONDS,
    ) -> None:
        """Ask for every ID that has not been answered yet, one at a time."""
        self.running = True
        try:
            for data_id in self._ids:
                if data_id in self.answers:
                    continue

                self._waiting = data_id
                self._answered.clear()
                try:
                    await ask(data_id)
                    await asyncio.wait_for(self._answered.wait(), answer_seconds)
                except TimeoutError:
                    self.answers[data_id] = Answer(NO_ANSWER)
                finally:
                    self._waiting = None

                await asyncio.sleep(pause)
        finally:
            self.running = False

        self.finished = True
        _LOGGER.info("OpenTherm ID scan: %s", self.summary())

    def ids(self, kind: str) -> list[int]:
        return sorted(data_id for data_id, answer in self.answers.items() if answer.kind == kind)

    def supported(self) -> dict[str, str]:
        return {
            describe(data_id): decode(raw)
            for data_id, answer in sorted(self.answers.items())
            if answer.kind == SUPPORTED and (raw := answer.raw) is not None
        }

    def summary(self) -> str:
        return (
            f"supported {self.ids(SUPPORTED)}, data invalid {self.ids(INVALID)}, "
            f"unknown {self.ids(UNKNOWN)}, no answer {self.ids(NO_ANSWER)}"
        )

    def answer(self, data_id: int) -> str | None:
        """Return how the boiler answered an ID, or None when it was not asked yet."""
        if (answer := self.answers.get(data_id)) is None:
            return None
        return answer.kind
