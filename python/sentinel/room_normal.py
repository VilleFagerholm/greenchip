"""Room normal temperature and the cold-draft signal (research R5, data-model.md RoomNormal)."""

from collections import deque
from statistics import median

from sentinel import config


class RoomNormal:
    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self._recent: deque[tuple[float, float]] = deque()
        self._history: deque[tuple[float, float]] = deque()
        self._last_t: float | None = None
        self.current_c: float | None = None
        self.normal_c: float | None = None
        self.cold = False

    @property
    def drop_c(self) -> float:
        if self.normal_c is None or self.current_c is None:
            return 0.0
        return self.normal_c - self.current_c

    def update(self, t: float, temp_c: float, sensitivity_c: float, freeze: bool) -> None:
        dt = 0.0 if self._last_t is None else t - self._last_t
        self._last_t = t

        self._recent.append((t, temp_c))
        while t - self._recent[0][0] > config.CURRENT_WINDOW_S:
            self._recent.popleft()
        self.current_c = median(v for _, v in self._recent)

        if not freeze:
            self._history.append((t, self.current_c))
            while t - self._history[0][0] > config.NORMAL_WINDOW_S:
                self._history.popleft()
            if t - self._history[0][0] >= config.NORMAL_MIN_S:
                target = median(v for _, v in self._history)
                if self.normal_c is None or target <= self.normal_c:
                    self.normal_c = target
                else:
                    self.normal_c = min(target, self.normal_c + config.NORMAL_MAX_RISE_C_PER_MIN * dt / 60)

        drop = self.drop_c
        if self.cold:
            self.cold = drop >= sensitivity_c - config.COLD_HYSTERESIS_C
        else:
            self.cold = self.normal_c is not None and drop >= sensitivity_c
