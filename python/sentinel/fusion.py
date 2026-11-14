"""Multi-signal fusion (constitution II; research R7, R12): any 2 of cold, window, noise."""

from dataclasses import dataclass

from sentinel import config
from sentinel.occupancy import EMPTY, OCCUPIED

IDLE, SUSPECT, DRAFT = "idle", "suspect", "draft"
COLD, WINDOW, NOISE = "cold", "window", "noise"
SIGNAL_BITS = {COLD: 1, WINDOW: 2, NOISE: 4}


@dataclass(frozen=True)
class FusionResult:
    state: str
    signals: frozenset
    blocked_by: str | None = None

    @property
    def signal_bits(self) -> int:
        return sum(SIGNAL_BITS[s] for s in self.signals)


def fuse(occupancy: str, cold: bool, window_signal: bool, thermo_ok: bool, window_ready: bool,
         noise_signal: bool = False, mic_ok: bool = False) -> FusionResult:
    signals = set()
    if thermo_ok and cold:
        signals.add(COLD)
    if window_ready and window_signal:
        signals.add(WINDOW)
    if mic_ok and noise_signal:
        signals.add(NOISE)
    signals = frozenset(signals)
    if not signals:
        return FusionResult(IDLE, signals)
    if occupancy == OCCUPIED:
        return FusionResult(SUSPECT, signals, "occupied")
    if occupancy != EMPTY:
        return FusionResult(SUSPECT, signals, "occupancy_unknown")
    if len(signals) >= config.MIN_SIGNALS_FOR_DRAFT:
        return FusionResult(DRAFT, signals)
    if not thermo_ok:
        return FusionResult(SUSPECT, signals, "thermo_missing")
    if not window_ready:
        return FusionResult(SUSPECT, signals, "setup_needed")
    return FusionResult(SUSPECT, signals)
