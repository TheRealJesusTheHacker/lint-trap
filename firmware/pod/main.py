# main.py — copy pod/ onto the board, copy LilyGo's lib/XPowersLib.py (MIT)
# next to it, then copy THIS file as the board's root main.py.
#
# Power design: the pod spends its life in deep sleep (microamps). It wakes
# ONLY on the panic button (EXT0), runs the hold timer, and either fires
# the alert or goes back to sleep on a short press. Modem/GPS/camera rails
# are cut in sleep — the 2000mAh LiPo lasts months, not hours.

import time
from pod import lilygo_board as B
from pod import config as C
from pod import alert, button
from pod.pmu import PowerUnit
from pod.esp32_hal import build_lilygo_pod, sleep_until_button


def run_alert(pmu):
    """Woke by the button. Returns the alert result string, or '' if the
    press was too short to trigger (false wake)."""
    pod_hal, clock, _btn_pin = build_lilygo_pod(B, pmu)
    pod = alert.AlertPod(pod_hal, C, clock)
    pod.attach_button(button.PanicButton(pod_hal.button,
                                         C.BUTTON_HOLD_SECONDS, clock,
                                         C.BUTTON_DEBOUNCE_MS))
    t0 = clock.now_ms()
    last_seen = ""
    while True:
        pod.tick()
        if pod.last_result and pod.last_result != last_seen:
            return pod.last_result
        # false wake: released, nothing triggered within 10s
        if clock.diff_ms(clock.now_ms(), t0) > 10000 \
                and pod.state == alert.IDLE \
                and not pod_hal.button.is_pressed():
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

    if machine.reset_cause() == machine.DEEPSLEEP_RESET:
        print("woke by button — arming hold timer")
        result = run_alert(pmu)
        print("alert complete: %s" % result if result
              else "short press — back to sleep")
    else:
        print("power-on boot — sleeping until the button is pressed")
    go_to_sleep(pmu)


if __name__ == "__main__":
    main()
