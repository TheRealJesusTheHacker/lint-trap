# AXP2101 power management for the T-SIM7080G-S3.
#
# SETUP REQUIRED: copy lib/XPowersLib.py from LilyGo's MIT-licensed repo
# (https://github.com/Xinyuan-LilyGO/LilyGo-T-SIM7080G-MicroPython)
# onto the board's filesystem before running. This module wraps it with
# the pod's exact power-up sequence — nothing more.
#
# Sequence (from LilyGo's own MicroPython power example):
#   DC3 3000mV on  -> modem lives
#   BLDO2 3300mV on -> GPS antenna lives
#   TS detect off   -> battery actually charges (no NTC on board)
#   ADCs on         -> battery / VBUS / system voltage readable
#
# Camera rails (ALDO1/2/4) are driven via raw registers below, because
# LilyGo's MicroPython XPowersLib has NO setALDOxVoltage/enableALDO —
# their own camera example calls methods that don't exist. Register map
# is the published AXP2101 layout (matches XPowers' Arduino driver).
#
# NEVER touch BLDO1. NEVER turn off DC1.

# AXP2101 LDO registers (published hardware map)
_REG_LDO_ONOFF_CTRL0 = 0x90
_ALDO_ENABLE_BIT = {1: 0, 2: 1, 4: 3}
_ALDO_VOL_REG = {1: 0x92, 2: 0x93, 4: 0x95}  # LDO_VOL0/1/3_CTRL
_ALDO_VOL_MIN = 500
_ALDO_VOL_STEP = 100

try:
    import XPowersLib

    _HAVE_XP = True
except ImportError:
    _HAVE_XP = False


class PowerUnit:
    def __init__(self, board):
        if not _HAVE_XP:
            raise RuntimeError(
                "XPowersLib missing: copy lib/XPowersLib.py from LilyGo's "
                "LilyGo-T-SIM7080G-MicroPython repo (MIT) onto the board."
            )
        import machine

        self._board = board
        self._i2c = machine.I2C(
            0, scl=machine.Pin(board.PMU_SCL_PIN), sda=machine.Pin(board.PMU_SDA_PIN)
        )
        self._pmu = XPowersLib.XPowersPMU()

    def begin(self):
        b = self._board
        ok = self._pmu.begin(
            self._i2c, XPowersLib.AXP2101_SLAVE_ADDRESS, b.PMU_SDA_PIN, b.PMU_SCL_PIN
        )
        if not ok:
            raise RuntimeError("AXP2101 not responding on I2C")
        p = self._pmu
        p.setDC3Voltage(b.RAIL_MODEM_DC3_MV)
        p.enableDC3()
        p.setBLDO2Voltage(b.RAIL_GPS_BLDO2_MV)
        p.enableBLDO2()
        p.disableTSPinMeasure()
        p.enableBattDetection()
        p.enableVbusVoltageMeasure()
        p.enableBattVoltageMeasure()
        p.enableSystemVoltageMeasure()
        return True

    # -- modem / GPS rails (sleep control) --
    def modem_rail(self, on):
        p = self._pmu
        if on:
            p.setDC3Voltage(self._board.RAIL_MODEM_DC3_MV)
            p.enableDC3()
        else:
            p.disableDC(3)

    def gps_antenna(self, on):
        p = self._pmu
        if on:
            p.setBLDO2Voltage(self._board.RAIL_GPS_BLDO2_MV)
            p.enableBLDO2()
        else:
            p.disableBLDO(2)

    # -- camera rails (raw registers — see module docstring) --
    def _set_aldo(self, n, mv):
        if mv % _ALDO_VOL_STEP or not (_ALDO_VOL_MIN <= mv <= 3500):
            raise ValueError("ALDO%d bad voltage %d" % (n, mv))
        p = self._pmu
        reg = _ALDO_VOL_REG[n]
        val = p.readRegister(reg) & 0xE0
        val |= (mv - _ALDO_VOL_MIN) // _ALDO_VOL_STEP
        p.writeRegister(reg, val)
        p.setRegisterBit(_REG_LDO_ONOFF_CTRL0, _ALDO_ENABLE_BIT[n])

    def camera_power_on(self):
        b = self._board
        self._set_aldo(1, b.RAIL_CAM_ALDO1_MV)
        self._set_aldo(2, b.RAIL_CAM_ALDO2_MV)
        self._set_aldo(4, b.RAIL_CAM_ALDO4_MV)

    def camera_power_off(self):
        for n in (1, 2, 4):
            self._pmu.disableALDO(n)

    # -- battery --
    def battery_mv(self):
        return self._pmu.getBattVoltage()

    def battery_percent(self):
        try:
            return self._pmu.getBatteryPercent()
        except Exception:
            return -1

    def battery_connected(self):
        try:
            return self._pmu.isBatteryConnect()
        except Exception:
            return False
