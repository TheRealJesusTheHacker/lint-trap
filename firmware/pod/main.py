# main.py — copy pod/ onto the board, copy LilyGo's lib/XPowersLib.py (MIT)
# next to it, then copy THIS file as the board's root main.py.
# Runs the pod forever.
#
# Boot: PMU power-up -> modem/camera rails ready -> alert loop.
# After each alert: deep sleep until the panic button is pressed.
# (The PMU keeps rails up in sleep; the modem re-attaches on wake.)

import time
from pod import lilygo_board as B
from pod import config as C
from pod import alert, button
from pod.pmu import PowerUnit
from pod.esp32_hal import build_lilygo_pod, sleep_until_button


def main():
    print("hoodie pod booting...")
    pmu = PowerUnit(B)
    pmu.begin()
    mv = pmu.battery_mv()
    print("battery: %d mV (%d%%)" % (mv, pmu.battery_percent()))
    if mv < B.BATT_LOW_MV:
        print("WARNING: low battery — alert will still send, charge soon")

    pod_hal, clock, _btn_pin = build_lilygo_pod(B, pmu)
    pod = alert.AlertPod(pod_hal, C, clock)
    pod.attach_button(button.PanicButton(pod_hal.button,
                                         C.BUTTON_HOLD_SECONDS,
                                         C.BUTTON_DEBOUNCE_MS))

    last_seen = ""
    while True:
        pod.tick()
        # tick() moves DONE->IDLE internally, so detect completion by result
        if pod.last_result and pod.last_result != last_seen:
            last_seen = pod.last_result
            print("alert complete: %s" % last_seen)
            if C.DEEP_SLEEP_BETWEEN_ALERTS:
                print("sleeping until button press...")
                time.sleep_ms(500)
                sleep_until_button(B)  # wakes -> reboot -> main.py again
            # if deep sleep disabled, the pod is already back at IDLE
        time.sleep_ms(20)


if __name__ == "__main__":
    main()
