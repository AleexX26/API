import random

import pytest

from app.collectors import pacing


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    pacing.reset()
    monkeypatch.delenv("PAUSA_MIN", raising=False)
    monkeypatch.delenv("PAUSA_MAX", raising=False)
    yield
    pacing.reset()


def test_the_default_pause_is_random_between_30_and_60_seconds_and_never_the_same():
    rng = random.Random(1)
    pauses = [pacing.next_pause(rng) for _ in range(50)]
    assert all(30 <= p <= 60 for p in pauses)
    assert len(set(pauses)) > 40  # irregular, not a fixed rhythm
    assert max(pauses) - min(pauses) > 15


def test_human_pause_waits_that_long(monkeypatch):
    waited = []
    monkeypatch.setattr(pacing.time, "sleep", waited.append)
    seconds = pacing.human_pause(random.Random(7))
    assert waited == [seconds] and 30 <= seconds <= 60


def test_bounds_can_be_changed_by_flags_or_environment(monkeypatch):
    monkeypatch.setenv("PAUSA_MIN", "10")
    monkeypatch.setenv("PAUSA_MAX", "20")
    assert pacing.bounds() == (10.0, 20.0)
    pacing.configure(40, 90)  # a flag wins over the environment
    assert pacing.bounds() == (40.0, 90.0)
    pacing.configure(low=50)  # the other bound stays (raised if needed)
    assert pacing.bounds() == (50.0, 90.0)


def test_it_never_goes_below_the_project_rule_of_5_seconds_or_inverts_the_bounds():
    with pytest.raises(ValueError):
        pacing.configure(2, 10)
    with pytest.raises(ValueError):
        pacing.configure(30, 20)


def test_the_command_line_flags_are_applied():
    import argparse
    cli = argparse.ArgumentParser()
    pacing.add_arguments(cli)
    pacing.apply(cli.parse_args(["--pausa-min", "6", "--pausa-max", "9"]))
    assert pacing.bounds() == (6.0, 9.0)
    pacing.reset()
    pacing.apply(cli.parse_args([]))
    assert pacing.bounds() == pacing.DEFAULT
