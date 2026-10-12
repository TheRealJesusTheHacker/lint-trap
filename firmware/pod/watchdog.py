# Hardware watchdog backstop for the hoodie pod.
#
# The alert cycle has several spin loops (UART write stalls, the
# stuck-button wait in main.go_to_sleep, AT command polls). The alert
# logic feeds this watchdog in every loop; if any loop wedges, the WDT
# resets the board instead of sitting at full draw until the battery
# dies silently. MicroPython-compatible: on a non-device host
# (simulator / pytest) machine.WDT does not exist and feed() is a no-op.

try:
    import machine

    _HAVE_WDT = hasattr(machine, "WDT")
except ImportError:
    _HAVE_WDT = False

# 30s: longer than any single fed spin (AT timeouts, camera retries,
# PWRKEY pulse), short enough that a wedged pod reboots instead of
# draining the 2000mAh LiPo. Every loop that can block longer than
# this MUST call feed() per iteration — see esp32_hal._Uart.cmd,
# esp32_hal._Uart.write_all, main.run_alert_loop, main.go_to_sleep.
WDT_TIMEOUT_MS = 30000

_wdt = None


def init(timeout_ms=WDT_TIMEOUT_MS):
    """Arm the watchdog. Returns the WDT or None if unavailable.
    Best-effort: a board without WDT support still boots."""
    global _wdt
    if _HAVE_WDT:
        try:
            _wdt = machine.WDT(timeout=timeout_ms)
        except Exception as e:
            print("WDT unavailable: %r — running without backstop" % (e,))
            _wdt = None
    return _wdt


def feed():
    """Pat the dog. No-op when no WDT is armed (simulator/pytest)."""
    if _wdt is not None:
        _wdt.feed()
