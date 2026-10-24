"""Rates with honest ranges.

The same Wilson score interval (z = 1.96) as workflow-eval-harness and the error-rate
calculator, so every rate in this project carries its likely range and reads the same way.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

Z = 1.96


@dataclass(frozen=True)
class Rate:
    n: int
    d: int

    @property
    def value(self) -> float | None:
        return None if self.d == 0 else self.n / self.d

    @property
    def low(self) -> float | None:
        return wilson(self.n, self.d)[0] if self.d else None

    @property
    def high(self) -> float | None:
        return wilson(self.n, self.d)[1] if self.d else None

    def text(self) -> str:
        if self.d == 0:
            return "not measured (0 cases)"
        return f"{100 * self.n / self.d:.1f}% ({self.n} of {self.d}; likely {100 * self.low:.1f}-{100 * self.high:.1f}%)"  # type: ignore[operator]

    def as_dict(self) -> dict[str, float | int | None]:
        return {"n": self.n, "d": self.d, "rate": self.value, "low": self.low, "high": self.high}


def wilson(n: int, d: int, z: float = Z) -> tuple[float, float]:
    if d == 0:
        raise ValueError("no cases")
    p = n / d
    z2 = z * z
    denom = 1 + z2 / d
    center = (p + z2 / (2 * d)) / denom
    half = z * math.sqrt(p * (1 - p) / d + z2 / (4 * d * d)) / denom
    return max(0.0, center - half), min(1.0, center + half)
