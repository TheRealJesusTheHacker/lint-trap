# main.py — copy pod/ onto the board, copy LilyGo's lib/XPowersLib.py (MIT)
# next to it, then copy THIS file as the board's root main.py.
#
# Power design: the pod spends its life in deep sleep (microamps). It wakes
# ONLY on the panic button (EXT0), runs the hold timer, and either fires
# the alert or goes back to sleep on a short press. Modem/GPS/camera rails
# are cut in sleep — the 2000mAh LiPo lasts months, not hours.

import time

from pod import alert, button
from pod import config as C
from pod import lilygo_board as B
from pod.esp32_hal import build_lilygo_pod, sleep_until_button
from pod.pmu import PowerUnit


def run_alert(pmu):
    """Woke by the button. Returns the alert result string, or '' if the
    press was too short to trigger (false wake)."""
    pod_hal, clock, _btn_pin = build_lilygo_pod(B, pmu)
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
    pod = alert.AlertPod(pod_hal, C, clock)
    pod.attach_button(
        button.PanicButton(
            pod_hal.button, C.BUTTON_HOLD_SECONDS, clock, C.BUTTON_DEBOUNCE_MS
        )
    )
    t0 = clock.now_ms()
    last_seen = ""
    while True:
        try:
            pod.tick()
        except Exception as e:
            print("alert crashed mid-run: %r" % (e,))
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


def go_to_sleep(pmu):
    import machine

    # Never arm wake while the button is still held — EXT0 on an
    # already-low pin wakes instantly and we'd reboot-loop / double-alert.
    held = machine.Pin(B.PIN_BUTTON, machine.Pin.IN, machine.Pin.PULL_UP)
    while held.value() == 0:
        time.sleep_ms(50)
    pmu.camera_power_off()
    pmu.gps_antenna(False)
    pmu.modem_rail(False)
    time.sleep_ms(100)
    sleep_until_button(B)  # never returns; wake = reboot into main()


def main():
    import machine

    print("hoodie pod booting...")
    pmu = PowerUnit(B)
    pmu.begin()
    mv = pmu.battery_mv()
    print("battery: %d mV (%d%%)" % (mv, pmu.battery_percent()))
    if mv < B.BATT_LOW_MV:
        print("WARNING: low battery — alert will still send, charge soon")
    for problem in C.validate():
        print("WARNING: config problem — %s" % problem)

    if machine.reset_cause() == machine.DEEPSLEEP_RESET:
        # Button wake: no delays, every second counts.
        print("woke by button — arming hold timer")
        result = run_alert(pmu)
        if result == "pod-error":
            print("alert FAILED (pod error) — check the log above")
        elif result:
            print("alert complete: %s" % result)
        else:
            print("short press — back to sleep")
    else:
        # Power-on boot: bench window. Without this, the board sleeps
        # before you can get a REPL, and bringup.py becomes unreachable
        # (deep sleep eats Ctrl+C). Ctrl+C here drops to REPL instead.
        print("power-on boot: 5s REPL window (Ctrl+C), then sleep")
        try:
            for _ in range(50):
                time.sleep_ms(100)
        except KeyboardInterrupt:
            print("REPL mode — pod NOT armed; run: from pod import bringup")
            return
    go_to_sleep(pmu)


if __name__ == "__main__":
    main()
