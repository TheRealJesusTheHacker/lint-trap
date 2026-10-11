# Bench bring-up for the parts-list hardware, in the buy list's order.
# Run each step from the MicroPython REPL over USB-C:
#
#   from pod import bringup
#   bringup.step1_power()    # -> then step2, step3, ...
#
# Do NOT skip steps. Each one proves a subsystem before the next depends on it.
# NOTE: if the board's root main.py is the pod firmware, power-on gives you
# a 5s Ctrl+C window for REPL — use the mechanical switch to power-cycle
# if you miss it.

from . import config as C
from . import lilygo_board as B
from .pmu import PowerUnit

_pmu = None


def _pmu():
    global _pmu
    if _pmu is None:
        _pmu = PowerUnit(B)
        _pmu.begin()
    return _pmu


def step1_power():
    """Power + battery/charging check. VERIFY JST POLARITY FIRST (red/black)
    — reversed polarity kills the board."""
    p = _pmu()
    print("PMU ok")
    print("battery connected:", p.battery_connected())
    print("battery: %d mV (%d%%)" % (p.battery_mv(), p.battery_percent()))
    if p.battery_mv() < B.BATT_LOW_MV:
        print("WARNING: low battery — charge before cellular tests")
    print("step1 PASS: board alive on PMU power")


def step2_camera():
    """OV2640 still to flash — proves the camera before anything cellular."""
    import camera

    p = _pmu()
    p.camera_power_on()
    import time

    time.sleep_ms(500)
    ok = False
    for _ in range(5):
        try:
            camera.deinit()
        except Exception:
            pass
        if camera.init(0, format=camera.JPEG, framesize=camera.FRAME_VGA):
            ok = True
            break
        time.sleep_ms(2000)
    assert ok, "camera init failed — reseat the camera connector"
    img = camera.capture()
    with open("photo_test.jpg", "wb") as f:
        f.write(img)
    print("captured photo_test.jpg (%d bytes)" % len(img))
    print("step2 PASS: camera works")


def step3_sms():
    """SIM in, Cat-M1 attach, one SMS to the parent number."""
    from .esp32_hal import LilyGoModem

    m = LilyGoModem(B, _pmu())
    assert m.send_sms(
        C.PARENT_NUMBER, "hoodie pod alive — SMS path ok"
    ), "SMS failed — check SIM, APN/bands, antenna"
    print("step3 PASS: SMS delivered")


def step4_gps():
    """GNSS fix on the bench. Note the time-to-fix."""
    import time

    from .esp32_hal import LilyGoModem

    m = LilyGoModem(B, _pmu())
    m.power_on()
    t0 = time.ticks_ms()
    fix = None
    while time.ticks_diff(time.ticks_ms(), t0) < C.GPS_FIX_TIMEOUT_S * 1000:
        fix = m.get_fix(timeout_s=10)
        if fix:
            break
        print("waiting for fix...")
    m.power_off()
    assert fix, (
        "no fix in %ds — take the board near a window/outside" % C.GPS_FIX_TIMEOUT_S
    )
    dt = time.ticks_diff(time.ticks_ms(), t0) // 1000
    print("fix: %.6f, %.6f in %ds" % (fix[0], fix[1], dt))
    print("step4 PASS: GNSS works (time-to-fix %ds — write it down)" % dt)


def step5_golden():
    """The golden path on real hardware: hold the button 2s -> fix ->
    3 JPEGs -> MMS + SMS to the parent number."""
    import time

    from . import alert, button
    from .esp32_hal import build_lilygo_pod

    pod_hal, clock, _btn_pin = build_lilygo_pod(B, _pmu())
    pod = alert.AlertPod(pod_hal, C, clock)
    pod.attach_button(
        button.PanicButton(
            pod_hal.button, C.BUTTON_HOLD_SECONDS, clock, C.BUTTON_DEBOUNCE_MS
        )
    )
    print("hold the panic button 2 seconds...")
    last_seen = ""
    while True:
        pod.tick()
        if pod.last_result and pod.last_result != last_seen:
            last_seen = pod.last_result
            print("RESULT:", last_seen)
            break
        time.sleep_ms(20)
    print("step5 PASS: golden path complete — %s" % last_seen)
