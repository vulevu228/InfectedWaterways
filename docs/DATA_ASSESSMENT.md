# Data assessment (2026-11-16)

## 1. Are the login-only sources worth it?

### Copernicus GloFAS archive (EWDS, needs account + token): **not now**
- Open-Meteo's Flood API serves the same GloFAS model discharge without a login: daily, 0.05° (~5 km) grid,
  1984-01-01 up to 7 months of forecast. Tested on 2026-11-16 for 1984, Nov 2005 and Oct 2010.
- Pitfall found: at 5 km the nearest grid cell is often **not the river channel**. The raw point at Harbin gave
  3.2 m³/s on 2005-11-20. Fix: query a 9 × 9 cell window (±0.2°) and take the cell with the highest discharge.
  Results after snapping:
  | River point | Date | Raw nearest cell | Snapped (max of 81 cells) |
  |---|---|---|---|
  | Songhua at Harbin | 2005-11-20 | 3.2 m³/s | 661 m³/s |
  | Artibonite near mouth, Haiti | 2010-10-15 | 0.6 m³/s | 222 m³/s |
  | Mekong at Phnom Penh | 2025-09-15 | not checked | 35,317 m³/s |
- The login is only worth it if we later need full gridded daily fields for a whole continent at once.
  Open-Meteo's cap of 10,000 calls/day is enough for ~1,000 river nodes per basin.

### GRDC measured gauges (form + contact details, no API, non-commercial): **later, optional, one-time**
- Gives *measured* discharge. Useful only to check Open-Meteo's *modelled* discharge at a handful of gauges in
  Milestone 4 (Songhua/Amur, Mekong, Artibonite). Because there is no API it can't feed a pipeline.
  Coverage for Chinese stations may be thin (to verify on the portal).

### JMP WASH (no login, but no API): **yes, in Milestone 2, as a one-time manual download**

## 2. Can the WEL "Outbreaks since 2000" history data be used?

File: `WorldEventsMap/function_app/site/geo/outbreaks.json`, built by `tools/build_outbreaks.py` (updated 2026-10-20).
Contents: 10 hand-checked outbreaks, each with origin point, countries (ISO3, cases, deaths, role
origin/spread/imported/treated), totals, routes of spread, symptoms (EN/DE) and WHO/CDC/PAHO/OWID sources.

| Outbreak | Route of spread | Waterborne? |
|---|---|---|
| SARS 2002–03 | respiratory droplets | no |
| H1N1 2009–10 | respiratory | no |
| MERS 2012– | respiratory, camels | no |
| Ebola West Africa 2013–16 | body fluids | no |
| Zika 2015–16 | mosquitoes | no |
| Ebola Kivu 2018–20 | body fluids | no |
| COVID-19 2019–23 | respiratory | no (only detectable in wastewater) |
| Mpox 2022– | close contact | no |
| Hantavirus, cruise ship Hondius 2026 | rodents / person-to-person (Andes virus) | no |
| Ebola Bundibugyo, DR Congo 2026 | body fluids | no |

**Verdict:** none of the 10 is waterborne, so the **records** can't validate river spread or supply
simulation parameters. Three parts are reusable:
1. **The schema and builder pattern.** Copy it for a new hand-checked "Waterborne outbreaks since 2000" layer
   (candidates: Haiti cholera 2010–19, Zimbabwe cholera 2008–09, Yemen cholera 2016–, Malawi cholera 2022–23,
   plus hepatitis E and typhoid outbreaks), with the same fields, sources and roles.
2. **The live WHO Disease Outbreak News reader** from the WEL page, filtered to cholera, typhoid, hepatitis A/E,
   shigellosis and leptospirosis.
3. **Country points** from WEL's `world.json` (centre of each country's largest polygon).

Optional: one "contrast" sentence on the page — most famous recent outbreaks spread through the air or by
contact, which is why this map focuses on cholera-type pathogens.

The WEL repo is private forever: copy data and code patterns, never link the repo.
