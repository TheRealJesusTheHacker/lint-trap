# CLI proof-model runner: simulates the full golden path on your PC.
#   python3 sim/run.py           -- normal: hold -> GPS -> photos -> MMS+SMS
#   python3 sim/run.py --no-mms  -- MMS fails: watch the SMS fallback
#   python3 sim/run.py --no-gps  -- no GPS fix: watch the no-fix fallback
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from pod import alert, button, config
from sim import mock_hal


def main(argv):
    fail_mms = "--no-mms" in argv
    gps_fail = "--no-gps" in argv

    pod_hal, clock, mock_btn = mock_hal.build_mock_hal(
        fail_mms=fail_mms, gps_fail=gps_fail
    )
    pod = alert.AlertPod(pod_hal, config, clock)
    pod.attach_button(
        button.PanicButton(pod_hal.button, config.BUTTON_HOLD_SECONDS, clock)
    )

    print("=== HOODIE POD PROOF MODEL ===")
    print("Simulating a 2-second panic-button hold in 1s...")
    time.sleep(1)
    mock_btn.held = True
    deadline = time.monotonic() + 240
    last_state = None
    alerts_done = 0
    while time.monotonic() < deadline and alerts_done < 1:
        pod.tick()
        if pod.state != last_state:
            print(
                "  state ->",
                {
                    0: "IDLE",
                    1: "ACQUIRING GPS",
                    2: "CAPTURING",
                    3: "SENDING",
                    4: "DONE",
                }[pod.state],
            )
            if pod.state == 4:
                alerts_done += 1
                mock_btn.held = False  # release so it doesn't re-trigger
            last_state = pod.state
        time.sleep(0.05)

    print("\nRESULT:", pod.last_result)
    print("\nAT log (what the SIM7080G would have done):")
    for line in pod_hal.modem.at_log:
        print("  " + line)
    print("\nOutbox:", os.listdir(mock_hal.OUTBOX))
    return pod.last_result


if __name__ == "__main__":
    main(sys.argv)
