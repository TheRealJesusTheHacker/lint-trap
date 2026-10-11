## What changed

## Why

## Verification

- [ ] `python3 -m pytest sim/ -v` passes from `firmware/`
- [ ] `python3 -m ruff check pod/ sim/` passes
- [ ] `python3 -m black --check pod/ sim/` passes
- [ ] Sim scenarios re-run if alert flow changed (`run.py`, `--no-mms`, `--no-gps`)

## Notes for review

- No function signatures changed
- No features stripped or neutered
- AT sequences still marked DRAFT where unvalidated on hardware
- Hardware claims match bench reality (or say "not yet validated")
