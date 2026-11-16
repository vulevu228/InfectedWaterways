# Travel-time calibration

Generated 2026-11-16 by `build/build_events.py` from the reported arrival dates in `build/events.json`.

Reach velocity model: **v = a · Q^b** (m/s), Q = long-term mean discharge of the reach (HydroRIVERS, m³/s);
travel time = Σ reach length / v. Downstream hydraulic geometry (Leopold & Maddock 1953) gives b ≈ 0.1.

**Used by the map: a = 0.10, b = 0.30** - in-sample RMS log error 0.103 (typical factor 1.11 between model and observed).

Model choice by leave-one-out cross-validation (each checkpoint predicted by a fit made without it):

| Model | Parameters (all points) | In-sample factor | Leave-one-out factor |
|---|---|---|---|
| b fixed at 0.1 (textbook downstream exponent) | a = 0.34 | ×1.21 | ×1.26 |
| a and b free | a = 0.10, b = 0.30 | ×1.11 | ×1.17 |

Chosen: **a and b free** (lower leave-one-out error).

| Event | Checkpoint | Distance along river | Observed | Model (a=0.10, b=0.30) | Model (uncalibrated a=0.30, b=0.10) |
|---|---|---|---|---|---|
| Cyanide spill, Baia Mare | Szolnok (Tisza) | 494 km | 10 d | 10.7 d | 10.8 d |
| Cyanide spill, Baia Mare | Hungary-Serbia border (Tisza) | 666 km | 12 d | 13.6 d | 14.3 d |
| Cyanide spill, Baia Mare | Belgrade (Danube) | 880 km | 15 d | 16.5 d | 18.3 d |
| Benzene spill, Songhua River | Harbin | 572 km | 11 d | 9.3 d | 11.5 d |
| Tailings dam collapse, Rio Doce | Rio Doce mouth, Regência | 598 km | 17 d | 15.7 d | 13.5 d |
| Rhine water transit (reference) | Lobith (Dutch border) | 736 km | 9 d | 9.3 d | 13.6 d |

Caveats: only 6 checkpoints (3 spills + 1 reference transit time). The Songhua slick moved under forming ice; the Rio Doce mud was a dense
tailings flow held back by hydropower reservoirs (Candonga); dates are front arrivals reported to the day.
Mean-flow speeds ignore floods, tides and lakes (lake residence time is listed, not added).
Treat every trace time as an order-of-magnitude estimate, not a forecast.
