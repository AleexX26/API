"""Pauses between the steps of a collection: random, never the same twice.

Every collector waits between one step and the next (a page, a list, a quantity). The wait is a random time between a lower and an
upper bound (30 and 60 seconds by default), so a long run is slow and irregular like a person reading and choosing, and it is far
gentler on the site than a fixed rhythm. It is NOT a way past a block: a challenge, a captcha or an HTTP error still stops the run.

Change it with `--pausa-min` / `--pausa-max` on a collector, or with the environment variables PAUSA_MIN / PAUSA_MAX (seconds).
It can never be lower than the project rule of 5 seconds between requests.
"""
import os
import random
import time

FLOOR = 5.0
DEFAULT = (30.0, 60.0)
_chosen: list[float] = []  # set by a command line flag; takes precedence over the environment


def validated(low: float, high: float) -> tuple[float, float]:
    if low < FLOOR:
        raise ValueError(f"La pausa mínima no puede bajar de {FLOOR:g} segundos")
    if high < low:
        raise ValueError("La pausa máxima no puede ser menor que la mínima")
    return float(low), float(high)


def bounds() -> tuple[float, float]:
    if _chosen:
        return _chosen[0], _chosen[1]
    low = float(os.environ.get("PAUSA_MIN", DEFAULT[0]))
    high = float(os.environ.get("PAUSA_MAX", DEFAULT[1]))
    return validated(low, high)


def configure(low: float | None = None, high: float | None = None) -> None:
    """Fix the bounds for this run (None keeps the other bound as it is now)."""
    now_low, now_high = bounds()
    low = now_low if low is None else low
    high = max(now_high, low) if high is None else high
    _chosen[:] = list(validated(low, high))


def reset() -> None:
    _chosen.clear()


def next_pause(rng=random) -> float:
    low, high = bounds()
    return round(rng.uniform(low, high), 1)


def human_pause(rng=random) -> float:
    """Wait a random time within the bounds and return how long it was."""
    seconds = next_pause(rng)
    time.sleep(seconds)
    return seconds


def add_arguments(cli) -> None:
    cli.add_argument("--pausa-min", type=float, help=f"pausa mínima entre pasos, en segundos (por defecto {DEFAULT[0]:g}; nunca menos de {FLOOR:g})")
    cli.add_argument("--pausa-max", type=float, help=f"pausa máxima entre pasos, en segundos (por defecto {DEFAULT[1]:g})")


def apply(args) -> None:
    if args.pausa_min is not None or args.pausa_max is not None:
        configure(args.pausa_min, args.pausa_max)
