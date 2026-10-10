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
#   ALDO1/2/4       -> camera rails (done in camera_power_on, only when needed)
#
# NEVER touch BLDO1. NEVER turn off DC1.

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
                "LilyGo-T-SIM7080G-MicroPython repo (MIT) onto the board.")
        import machine
        self._board = board
        self._i2c = machine.I2C(0, scl=machine.Pin(board.PMU_SCL_PIN),
                                sda=machine.Pin(board.PMU_SDA_PIN))
        self._pmu = XPowersLib.XPowersPMU()

    def begin(self):
        b = self._board
        ok = self._pmu.begin(self._i2c, XPowersLib.AXP2101_SLAVE_ADDRESS,
                             b.PMU_SDA_PIN, b.PMU_SCL_PIN)
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

    def camera_power_on(self):
        b, p = self._board, self._pmu
        p.setALDO1Voltage(b.RAIL_CAM_ALDO1_MV)
        p.enableALDO(1)
        p.setALDO2Voltage(b.RAIL_CAM_ALDO2_MV)
        p.enableALDO(2)
        p.setALDO4Voltage(b.RAIL_CAM_ALDO4_MV)
        p.enableALDO(4)

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
