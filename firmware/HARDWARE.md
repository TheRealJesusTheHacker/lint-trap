# Hoodie Pod — Hardware Architecture (Skyler, 2026-10-10)

## The design: one motherboard + wired peripherals

- **Single motherboard** — everything lives on one PCB: MCU (ESP32-S3),
  cellular (SIM7080G), GNSS, SIM holder, power management, status LED.
- **Wired hidden camera** — small camera module on a flex ribbon back to the
  board. The lens peeks through the fabric; the board sits elsewhere.
- **Wired panic button** — 12mm metal button on an insulated wire pair back
  to the board. Button lives in the sleeve; board lives in the body.
- **Removable for washing** — the board slides into a waterproof zip pouch
  sewn into the hoodie. Pop the pouch out, hoodie goes in the wash.
  (Alternative: conformal-coat the board for splash resistance, but the
  removable pouch is the primary answer — a washing machine kills everything.)

## Why this beats the pod-module concept

- One board = one thing to seal, one thing to remove, one thing to replace.
- Wired peripherals let each piece sit where it works best: lens where it
  can see, button where a kid's hand naturally is, board where it's
  comfortable and protected.
- Connectors (not soldered) on camera/button leads = field-replaceable.

## Phase plan still holds

- Phase 1 (dev boards): prove the golden path on the LILYGO T-SIM7080G-S3.
  The dev board IS a single-board equivalent — camera and button wire to it
  the same way.
- Phase 2 (custom): lay out the real single motherboard from the proven
  circuit. The firmware in `pod/` ports over unchanged — it only talks to
  the HAL, never to specific pins.
