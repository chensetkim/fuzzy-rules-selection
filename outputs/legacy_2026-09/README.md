# Legacy results (September 2026 settings)

These are the results quoted in `reports/` up to 2026-10-22. They were produced
with settings that the code **no longer uses**, so they are not reproducible with
the current `run_cars.sh` / `run_thfis.sh`:

- expert rules injected (R1-R18 into the CARS pool and starting population; the
  hand-crafted RA/SI/CX/TOP rules into the T-HFIS pools, and the T-HFIS TOP pool
  fitted against the hand-crafted layer-1 signals)
- rule budget 12-29 (now 12-35)
- High membership function 0 at 60 -> 100 at 90 (now 50 -> 80)
- T-HFIS LOSO: 100 generations (now 120, shared with CARS)

New runs go to `outputs/cars/run_<date>_<time>/` and `outputs/thfis/run_<date>_<time>/`.
Keep this folder until the reports have been updated with new results.
