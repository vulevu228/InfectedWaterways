# Validation: Haiti 2010 (out of sample)

Generated 2026-11-17 by `build/validate_haiti.py`. Haiti was not used to fit the travel-time model (v = 0.10 · Q^0.30, calibrated on spills only - see CALIBRATION.md), and the pass/fail criteria were fixed in the script before the run.

Observed facts: Piarroux et al. 2011, *Emerging Infectious Diseases* 17(7), doi:10.3201/eid1707.110059. Incubation: Azman et al. 2013, *J Infect* 66:432-8 (5 % by 0.5 d, median 1.4 d, 95 % by 4.4 d).

Trace from Meille (UN camp stream): 118.4 km to the sea in 3.41 d, mean flow 1.4 -> 134.9 m³/s (dilution ×96.4), 598,619 people within 5 km.

| Test | Result | What the model says |
|---|---|---|
| P1 timing | **PASS** | front reaches Desarmes after 1.46 d; a delta onset on Oct 19 implies a release between 2010-10-13 and 2010-10-18 (central 2010-10-17); the camp was contaminating Oct 12-19. Any travel time up to 6.5 d would pass, so this test only rules out a much slower river. |
| P2 simultaneity | **FAIL** | front at Desarmes after 1.46 d, at the sea after 3.41 d: a spread of 1.95 d across the delta, observed ≤ 1 d. |
| P3 exposure contrast | **FAIL** | 5,446 people per river-km in the delta vs 3,044 on the middle stretch: ×1.79 (needed ×3; observed cases: thousands vs 0-2). |
| P4 flow | **PASS** | mean flow at the mouth 134.9 m³/s (paper: usually >100 m³/s in October). |

## Criteria (fixed before the run)

- **P1** Timing: the release dates the model implies for a delta onset on Oct 19 (incubation 0.5-4.4 d, travel x/÷ the calibration error) overlap the window in which the camp was demonstrably contaminating (Oct 12-19).
- **P2** Simultaneity: the model front reaches every point from Desarmes to the sea within 1 day (observed: alerts from Desarmes to the seashore within 24 h).
- **P3** Exposure contrast: people per river-km within 5 km are at least 3x higher in the delta (Desarmes -> sea) than on the middle stretch (Mirebalais -> Desarmes), where almost no cases were reported.
- **P4** Flow: the model's mean flow at the mouth is above 100 m3/s (paper: usually >100 m3/s in October).

## Places along the trace

| Place | Distance to the traced river | River km from Meille | Model arrival |
|---|---|---|---|
| Mirebalais | 0.4 km | 3.3 | 0.27 d |
| Saut-d'Eau | 5.9 km | 14.8 | 0.62 d |
| Boucan-Carre | 6.6 km | 16.4 | 0.67 d |
| La Chapelle | 2.0 km | 31.8 | 1.08 d |
| Desarmes | 2.3 km | 45.6 | 1.46 d |
| Verrettes | 2.9 km | 56.8 | 1.76 d |
| Petite-Riviere-de-l'Artibonite | 0.5 km | 65.7 | 2.0 d |
| Pont-Sonde | 0.6 km | 83.4 | 2.48 d |
| Saint-Marc | 10.3 km | 86.0 | 2.55 d |
| Dessalines | 11.1 km | 92.8 | 2.73 d |
| L'Estere | 9.0 km | 99.7 | 2.91 d |
| Desdunes | 6.0 km | 106.4 | 3.09 d |
| Grande Saline | 0.2 km | 118.4 | 3.41 d |

## What this means

- Path: the trace runs from Meille past Mirebalais, through the thinly settled middle valley, into the delta and out at Grande Saline, the coastal commune the paper names; every delta place lies along it in the right order.
- Timing (passed) is only a weak test, because the release date is not known to the day: anything up to 6.5 d would have passed.
- Simultaneity failed: one channel's front needs 1.95 d to cross the delta, but the delta fell ill within a day. In the delta, irrigation canals take river water to rice fields and villages at the same time (67 % of early patients drank untreated river or canal water, CDC MMWR 2010), which a single-channel model cannot show.
- Exposure contrast failed (×1.79, needed ×3): a flat 5 km band does not capture who drinks the river. 4 of the 7 struck delta communes have their town 6-11.1 km from the main channel (Saint-Marc, Dessalines, L'Estere, Desdunes), outside the band, while hill villages inside the band on the middle stretch stayed almost free of cases. The paper's own risk factor is 'coastal plain' (RR 4.60).
- Consequence for the map: path and travel time are shown as tested; exposure is shown only as a relative index with ranges and its known blind spots (canals, floodplains), never as a count of the ill or the dead.
