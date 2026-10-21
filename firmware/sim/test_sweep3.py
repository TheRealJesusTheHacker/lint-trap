# Sweep #3 regression tests (2026-10-21).
#
# Pin: go_to_sleep() must reach deep sleep even when a PMU rail cut
# raises. Before the fix, the three rail cuts ran unguarded, so any
# exception from them (e.g. camera_power_off calling a PMU method the
# bench has not proven exists in XPowersLib) escaped go_to_sleep and
# main() — the pod stayed awake at full draw instead of parking, the
# exact failure main()'s PMU handling elsewhere is designed to avoid
# ("PMU failures must never veto sleep").

import os
import sys
import time
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from pod import main as pod_main  # noqa: E402


class _Slept(Exception):
    """Sentinel: sleep_until_button was reached."""


class _FakePin:
    IN = 0
    PULL_UP = 0

    def __init__(self, *args, **kwargs):
        pass

    def value(self):
        return 1  # not held (active-low button)


def _install_fakes(monkeypatch):
    machine = types.ModuleType("machine")
    machine.Pin = _FakePin
    monkeypatch.setitem(sys.modules, "machine", machine)

    class SimTime:
        @staticmethod
        def sleep_ms(ms):
            time.sleep(ms / 1000.0)

    monkeypatch.setattr(pod_main, "time", SimTime)

    def fake_sleep(board):
        raise _Slept

    monkeypatch.setattr(pod_main, "sleep_until_button", fake_sleep)


class _ExplodingPmu:
    def camera_power_off(self):
        raise AttributeError("disableALDO — simulated unproven PMU method")

    def gps_antenna(self, on):
        raise OSError("I2C wedged")

    def modem_rail(self, on):
        raise OSError("I2C wedged")


def test_go_to_sleep_survives_exploding_rail_cuts(monkeypatch, capsys):
    _install_fakes(monkeypatch)
    with pytest.raises(_Slept):
        pod_main.go_to_sleep(_ExplodingPmu(), cut_rails=True)
    out = capsys.readouterr().out
    # Every failure was logged, none vetoed the sleep.
    assert out.count("rail cut failed before sleep") == 3
    assert "sleeping anyway" in out


def test_go_to_sleep_happy_path_still_cuts_rails(monkeypatch):
    _install_fakes(monkeypatch)
    calls = []

    class GoodPmu:
        def camera_power_off(self):
            calls.append("camera")

        def gps_antenna(self, on):
            calls.append(("gps", on))

        def modem_rail(self, on):
            calls.append(("modem", on))

    with pytest.raises(_Slept):
        pod_main.go_to_sleep(GoodPmu(), cut_rails=True)
    assert calls == ["camera", ("gps", False), ("modem", False)]
