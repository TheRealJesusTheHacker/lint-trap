# main.py — copy onto the ESP32-S3 as main.py. Runs the pod forever.
# Fill in pod/config.py (parent number, carrier APN/MMSC) before flashing.

import time
from pod import config, alert, button
from pod.esp32_hal import build_pod

pod_hal, clock = build_pod(config)
pod = alert.AlertPod(pod_hal, config, clock)
pod.attach_button(button.PanicButton(pod_hal.button,
                                     config.BUTTON_HOLD_SECONDS,
                                     config.BUTTON_DEBOUNCE_MS))

while True:
    pod.tick()
    time.sleep_ms(20)
