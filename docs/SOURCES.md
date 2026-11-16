# Data sources — access check (tested live 2026-11-16)

Scope: whole world. "Tested" = an actual HTTP request was made from this PC on 2026-11-16.

## Open, no login, no API key

| Source | What it gives | Access | Licence | Test result 2026-11-16 |
|---|---|---|---|---|
| HydroRIVERS v1.0 (HydroSHEDS) | Global river network, ~8.5 M segments, each with `NEXT_DOWN` id + long-term avg discharge (m³/s) | Direct zip download per continent | CC BY 4.0 | HTTP 200, Asia shapefile zip = 12.9 MB |
| HydroLAKES / HydroBASINS (HydroSHEDS) | Global lakes (~1.4 M polygons) and nested catchments | Direct zip download | CC BY 4.0 | Same server as HydroRIVERS (not separately tested) |
| Open-Meteo Flood API | Daily river discharge (m³/s) from GloFAS, any lat/lon, past + forecast | REST, no key | CC BY 4.0, **non-commercial**, 10,000 calls/day | HTTP 200, Phnom Penh point returned 4 days |
| WHO GHO OData API | Cholera cases, deaths, CFR per country per year (`CHOLERA_0000000001/2/3`, `WHS3_40`) | REST, no key | WHO open terms | HTTP 200, 4 cholera indicators found |
| WHO Disease Outbreak News API | Every DON report (title, date, summary, text) | REST (OData), no key | WHO terms | HTTP 200, 49.5 KB for 2 latest reports |
| Our World in Data — cholera | Reported cholera cases per country, 1949+ | CSV download | CC BY 4.0 | HTTP 200, 76 KB CSV |
| WorldPop | Gridded population, ~100 m, per country per year | REST + GeoTIFF download | CC BY 4.0 | HTTP 200, Cambodia listing returned |
| HDX (Humanitarian Data Exchange) | Outbreak datasets (29 hits for "cholera") | CKAN API, no key | Per dataset (mostly CC BY / ODbL) | HTTP 200 |
| GDACS API | Current/past flood events worldwide (GeoJSON) | REST, no key | Open | HTTP 200, flood events Oct–Nov 2026 returned |
| GDELT DOC 2.0 | News articles mentioning outbreaks | REST, no key | Open | HTTP 429 = works, but **max 1 request per 5 s** |
| CDC NWSS (data.cdc.gov) | Wastewater SARS-CoV-2 etc. — **USA only** | Socrata API, no key | Public domain | HTTP 200 |
| Global Dam Watch database v1.0 (Figshare) | 41,145 barriers + 35,295 reservoirs | Download | CC BY 4.0 | Not tested (found via search) |
| OpenStreetMap Overpass | Waterways, water intakes, treatment plants | Query API, no key | ODbL | **Timed out in test**, known open; use Geofabrik extracts instead for bulk |

## Login / account / form required

| Source | What it gives | Hurdle | Test result 2026-11-16 |
|---|---|---|---|
| Copernicus GloFAS (EWDS) | Full gridded global discharge archive 1979+ | Free Copernicus/ECMWF account + API token | Metadata HTTP 200, data request **HTTP 401 "authentication required"** |
| GRDC (BfG Koblenz) | Measured discharge at ~10,000 real gauges | Web form + contact details + terms, **no API**, non-commercial only | Portal reachable; not automatable |
| GRanD v1.3 (via globaldamwatch.org) | 7,320 large dams | Unclear (one mirror says registration) — use the open GDW v1.0 above instead | Not confirmed |
| JMP WASH (washdata.org) | Drinking-water + sanitation coverage per country | No login, but files are behind a JS download page, no public API | Page HTTP 200, `api.washdata.org` = 404 |

## Paid / not usable

| Source | Why not |
|---|---|
| ProMED-mail | Subscription paywall since 2023 ("Subscribe now…" on homepage) |
| GIDEON | Commercial licence |

## Gaps to know about

- **Wastewater surveillance outside the USA** is fragmented (per-country portals). Phase 4 decides which ones are worth adding.
- **Pathogen concentrations in rivers** have no global open feed. The simulator models them (load ÷ discharge × decay) and labels every result as **simulated**.
- Open-Meteo is free only for **non-commercial** use, which fits a portfolio project.
