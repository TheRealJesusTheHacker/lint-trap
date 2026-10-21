# main.py — copy pod/ onto the board, copy LilyGo's lib/XPowersLib.py (MIT)
# next to it, then copy THIS file as the board's root main.py.
#
# Power design: the pod spends its life in deep sleep (microamps). It wakes
# ONLY on the panic button (EXT0), runs the hold timer, and either fires
# the alert or goes back to sleep on a short press. Modem/GPS/camera rails
# are cut in sleep — the 2000mAh LiPo lasts months, not hours.

import time

from pod import alert, button, watchdog
from pod import config as C
from pod import lilygo_board as B
from pod.esp32_hal import build_lilygo_pod, sleep_until_button
from pod.pmu import PowerUnit


def _crash_result(pod_hal, e):
    """Shared crash path for run_alert_loop: log, best-effort bare SMS
    (only when a HAL exists to send it with), red LED, 'pod-error'."""
    print("alert crashed mid-run: %r" % (e,))
    if pod_hal is not None:
        try:
            pod_hal.modem.send_sms(
                C.PARENT_NUMBER,
                "HOODIE ALERT from your child. Pod error mid-alert "
                "- call your child now.",
            )
        except Exception:
            pass
        try:
            pod_hal.led.set("red")
        except Exception:
            pass
    return "pod-error"


def run_alert(pmu):
    """Woke by the button. Returns the alert result string, or '' if the
    press was too short to trigger (false wake)."""
    try:
        pod_hal, clock, _btn_pin = build_lilygo_pod(B, pmu)
    except Exception as e:
        # Peripheral construction (UART/Pin setup) can fail on a sick
        # board. run_alert_loop's NEVER-raises contract starts here:
        # without a HAL there is nothing to send the bare SMS with, but
        # returning 'pod-error' still lets main() log the failure and
        # park the pod in deep sleep instead of dying on a traceback
        # at full draw.
        return _crash_result(None, e)
    return run_alert_loop(pod_hal, clock)


def run_alert_loop(pod_hal, clock):
    """Drive one wake cycle: hold timer -> alert -> result.

    Returns the alert result string, '' on a false wake, or 'pod-error'
    if the alert crashed mid-run. NEVER raises: an uncaught exception
    here (e.g. GPS power-on against a dead modem) would escape main()
    and the alert would die silently — on the board, the reboot lands in
    the power-on branch and the pod sleeps without ever sending. So on a
    crash we attempt a best-effort bare SMS first, then report the
    failure so the boot log shows it.
    """
    try:
        pod = alert.AlertPod(pod_hal, C, clock)
        pod.attach_button(
            button.PanicButton(
                pod_hal.button, C.BUTTON_HOLD_SECONDS, clock, C.BUTTON_DEBOUNCE_MS
            )
        )
    except Exception as e:
        # Setup is part of the NEVER-raises contract too: a bad tunable
        # reaching PanicButton (int(hold_s * 1000)) or a HAL whose
        # constructor touches hardware must take the same crash path
        # as a mid-run tick failure — bare SMS, then 'pod-error' — not
        # escape main() and leave the pod awake on a traceback.
        return _crash_result(pod_hal, e)
    t0 = clock.now_ms()
    last_seen = ""
    while True:
        watchdog.feed()  # WDT backstop: any wedge below reboots the pod
        try:
            pod.tick()
        except Exception as e:
            return _crash_result(pod_hal, e)
        if pod.last_result and pod.last_result != last_seen:
            return pod.last_result
        # false wake: released, nothing triggered within 10s
        if (
            clock.diff_ms(clock.now_ms(), t0) > 10000
            and pod.state == alert.IDLE
            and not pod_hal.button.is_pressed()
        ):
            return ""
        time.sleep_ms(20)


def go_to_sleep(pmu, cut_rails=True):
    import machine

    # Never arm wake while the button is still held — EXT0 on an
    # already-low pin wakes instantly and we'd reboot-loop / double-alert.
    # KEPT even though the watchdog backstops it: a stuck-shorted button
    # is a hardware fault, and sleeping with the pin low would burn the
    # battery on wake-reboot loops. The WDT fires first only if the pin
    # never releases.
    held = machine.Pin(B.PIN_BUTTON, machine.Pin.IN, machine.Pin.PULL_UP)
    while held.value() == 0:
        watchdog.feed()
        time.sleep_ms(50)
    if cut_rails:
        # Best-effort, like PMU init in main(): a rail that refuses to
        # cut (a PMU method the bench hasn't proven exists, a wedged
        # I2C bus) must never veto sleep — a pod that can't park drains
        # its battery at full draw, which is the worst failure this
        # function can produce. Log each failure and sleep anyway.
        for cut in (
            pmu.camera_power_off,
            lambda: pmu.gps_antenna(False),
            lambda: pmu.modem_rail(False),
        ):
            try:
                cut()
            except Exception as e:
                print("rail cut failed before sleep: %r — sleeping anyway" % (e,))
        time.sleep_ms(100)
    sleep_until_button(B)  # never returns; wake = reboot into main()


def main():
    import machine

    # Hardware watchdog: any wedge (wedged UART, stuck button, hung PMU
    # I2C) reboots the pod instead of draining the battery at full draw.
    watchdog.init()

    print("hoodie pod booting...")
    # PMU failures must never veto sleep: deepsleep needs no PMU, and a
    # pod that can't talk to its power chip must park, not spin.
    pmu_ok = True
    pmu = None
    try:
        pmu = PowerUnit(B)
        pmu.begin()
        mv = pmu.battery_mv()
    except Exception as e:
        pmu_ok = False
        mv = None
        print("PMU init failed: %r — skipping alert, sleeping anyway" % (e,))
    if pmu_ok:
        print("battery: %d mV (%d%%)" % (mv, pmu.battery_percent()))
        if mv < B.BATT_LOW_MV:
            print("WARNING: low battery — alert will still send, charge soon")
    for problem in C.validate():
        print("WARNING: config problem — %s" % problem)

    if machine.reset_cause() == machine.DEEPSLEEP_RESET and pmu_ok:
        # Button wake: no delays, every second counts.
        print("woke by button — arming hold timer")
        result = run_alert(pmu)
        if result == "pod-error":
            print("alert FAILED (pod error) — check the log above")
        elif result:
            print("alert complete: %s" % result)
        else:
            print("short press — back to sleep")
    elif machine.reset_cause() != machine.DEEPSLEEP_RESET:
        # Power-on boot: bench window. Without this, the board sleeps
        # before you can get a REPL, and bringup.py becomes unreachable
        # (deep sleep eats Ctrl+C). Ctrl+C here drops to REPL instead.
        print("power-on boot: 5s REPL window (Ctrl+C), then sleep")
        try:
            for _ in range(50):
                watchdog.feed()
                time.sleep_ms(100)
        except KeyboardInterrupt:
            print("REPL mode — pod NOT armed; run: from pod import bringup")
            return
    elif not pmu_ok:
        print("PMU down on button wake — alert needs the rails, sleeping")
    go_to_sleep(pmu, cut_rails=pmu_ok)


if __name__ == "__main__":
    main()
