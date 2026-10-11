# Panic button: debounced, hold-to-trigger.
# A kid bumps into things all day — a tap must NEVER fire an alert.
# Only a deliberate hold of BUTTON_HOLD_SECONDS triggers.


class PanicButton:
    def __init__(self, hal, hold_s, clock, debounce_ms=50):
        self._hal = hal
        self._hold_ms = int(hold_s * 1000)
        self._debounce_ms = debounce_ms
        self._clock = clock
        self._press_start = None
        self._last_change = 0
        self._stable = False
        self._fired = False

    def update(self, now_ms):
        """Call every tick. Returns True exactly once per qualifying hold."""
        diff = self._clock.diff_ms
        raw = self._hal.is_pressed()
        if raw != self._stable and diff(now_ms, self._last_change) >= self._debounce_ms:
            self._stable = raw
            self._last_change = now_ms
            if raw:
                self._press_start = now_ms
                self._fired = False
            else:
                self._press_start = None
                self._fired = False
        if self._stable and not self._fired and self._press_start is not None:
            if diff(now_ms, self._press_start) >= self._hold_ms:
                self._fired = True
                return True
        return False

    def hold_progress(self, now_ms):
        """0.0–1.0 progress toward trigger (drives the kid-facing LED)."""
        if not self._stable or self._press_start is None:
            return 0.0
        return min(1.0, self._clock.diff_ms(now_ms, self._press_start) / self._hold_ms)
