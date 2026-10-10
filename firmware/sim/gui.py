# GUI proof model: a big red panic button you press and HOLD with the mouse.
# Watch the whole golden path play out live: GPS fix -> photos -> MMS + SMS.
#   python3 sim/gui.py
import os, sys, time, tkinter as tk
from tkinter import scrolledtext

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from pod import config, alert, button
from sim import mock_hal

pod_hal, clock, mock_btn = mock_hal.build_mock_hal()
pod = alert.AlertPod(pod_hal, config, clock)
pod.attach_button(button.PanicButton(pod_hal.button, config.BUTTON_HOLD_SECONDS))

root = tk.Tk()
root.title("Hoodie Pod — Proof Model")
root.configure(bg="#0a0e18")
root.geometry("560x640")

tk.Label(root, text="HOODIE POD — PROOF MODEL", bg="#0a0e18", fg="#00d4ff",
         font=("DejaVu Sans", 16, "bold")).pack(pady=12)
tk.Label(root, text="Press and HOLD the button for 2 seconds",
         bg="#0a0e18", fg="#a0acbe",
         font=("DejaVu Sans", 11)).pack()

progress = tk.DoubleVar(value=0)
bar = tk.Scale(root, variable=progress, from_=0, to=100, orient="horizontal",
               length=400, showvalue=0, bg="#0a0e18", fg="#00d4ff",
               troughcolor="#16202c", highlightthickness=0)
bar.pack(pady=6)

btn = tk.Button(root, text="PANIC", bg="#c81e1e", fg="white",
                activebackground="#ff2a2a",
                font=("DejaVu Sans", 28, "bold"), width=14, height=3,
                relief="raised", bd=4)
btn.pack(pady=10)

def press(_e):
    mock_btn.held = True
def release(_e):
    mock_btn.held = False
btn.bind("<ButtonPress-1>", press)
btn.bind("<ButtonRelease-1>", release)

log = scrolledtext.ScrolledText(root, height=14, bg="#101828", fg="#e8ecf4",
                                font=("DejaVu Sans Mono", 10))
log.pack(fill="both", expand=True, padx=12, pady=8)

led_lbl = tk.Label(root, text="LED: green", bg="#0a0e18", fg="#50dc90",
                   font=("DejaVu Sans", 11, "bold"))
led_lbl.pack(pady=6)

STATES = {0: "IDLE", 1: "ACQUIRING GPS", 2: "CAPTURING PHOTOS",
          3: "SENDING ALERT", 4: "DONE"}
last_state, last_led, last_prog = None, None, -1

def say(msg):
    log.insert("end", msg + "\n")
    log.see("end")

def loop():
    global last_state, last_led, last_prog
    pod.tick()
    now = clock.now_ms()
    prog = int(pod._button.hold_progress(now) * 100)
    if prog != last_prog:
        progress.set(prog)
        last_prog = prog
    if pod.state != last_state:
        say("[%s] -> %s" % (time.strftime("%H:%M:%S"), STATES[pod.state]))
        if pod.state == 4:
            say("RESULT: " + pod.last_result)
            say("Outbox files: sim/outbox/")
            for line in pod_hal.modem.at_log[-6:]:
                say("  AT: " + line)
        last_state = pod.state
    if pod_hal.led.color != last_led:
        led_lbl.config(text="LED: " + pod_hal.led.color)
        last_led = pod_hal.led.color
    root.after(50, loop)

say("Ready. Hold PANIC for 2 seconds to fire the alert pipeline.")
loop()
root.mainloop()
