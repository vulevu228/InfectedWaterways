# Infected Waterways

**Status:** Milestone 1 done (world map, river graph in PostGIS, downstream trace, travel-time calibration, history layer), 2026-11-16. Private repo.

**Live (Tailscale only):** http://100.108.59.90:8796/ on the Pi (service `waterways-web`).

**Idea:** a global, open-data model of how waterborne pathogens travel along the world's river networks.
You pick a release point on any river. The model routes it downstream using real flow data and shows
dilution, die-off, arrival time at each city and the population living along the affected river stretch.
It is validated against documented real events.

**Ethics rule:** every simulated scenario is labelled **SIMULATED / HYPOTHETICAL** on every map, chart and
export. Real outbreak data (WHO and others) stays visually separate from the simulation.

## Pathogens (simulation parameters)
Cholera (*V. cholerae*), Typhoid, Hepatitis A/E, plus a generic chemical tracer for validation.
SARS-CoV-2 only shows up in the wastewater early-warning layer, because it doesn't spread through rivers.

## Milestones
| # | Milestone | Output |
|---|---|---|
| 0 | Planning + source check | `docs/SOURCES.md`, this README ✅ |
| 1 | World waterways map + river graph | ✅ Web map (rivers ≥ 10 m³/s, 1,131 named main stems, 1,708 HydroLAKES ≥ 100 km², OSM waterways at zoom ≥ 7, satellite/Sentinel-2/3D terrain); 2,369,127 HydroRIVERS reaches (≥ 1 m³/s) in PostGIS; downstream trace API (path, travel time, countries incl. border rivers, cities, lakes); 11 historic outbreaks + spills with sources; velocity calibrated on 6 reported arrival times (`docs/CALIBRATION.md`) |
| 2 | Real-data layer | WHO GHO + OWID cholera history, WHO DON outbreak feed (daily), GDACS floods, WorldPop exposure |
| 3 | Spread simulator | Plume = load ÷ discharge × e^(−k·t), with per-pathogen decay rates k; arrival times + people exposed per city |
| 4 | Validation | (Travel time already checked in M1.) Replay the 2005 Songhua→Amur benzene spill and the 2010 Haiti Artibonite cholera outbreak, then compare with reported arrival times |
| 5 | Map + dashboard | Web map (Count Down style) + Power BI report (real cholera vs. floods vs. WASH coverage) |
| 6 | Showcase scenarios | e.g. Lancang→Mekong→Tonle Sap seasonal flow reversal, Ganges–Brahmaputra delta, Niger, Danube |

## How it works
1. **River graph.** HydroRIVERS v1.0: every reach has `NEXT_DOWN`, the reach it flows into. The 2,369,127 reaches with
   mean flow ≥ 1 m³/s (`ORD_FLOW ≤ 6`) are loaded into PostGIS (table `rivers`). Flow order only grows downstream, so
   this subset is closed under `NEXT_DOWN`: every trace reaches the sea or an inland sink.
2. **Trace.** `GET /api/trace?lon&lat` snaps the click to the nearest reach (≤ 25 km), follows `NEXT_DOWN` with a recursive
   CTE, and adds per reach: distance, mean discharge, speed and arrival time. Along the path it also lists the countries
   (2 countries within 2.5 km of a reach = border river; runs < 12 km are dropped as noise), Natural Earth cities
   within 8 km, and HydroLAKES ≥ 5 km² with their residence time. Typical response 0.3–3 s on the Pi 4.
3. **Travel time.** Reach speed v = a · Q^b m/s (Leopold & Maddock 1953). Fitted on 6 reported arrival times
   (Baia Mare cyanide 2000: 3 checkpoints; Songhua benzene 2005; Rio Doce tailings 2015; Rhine water Rheinfelden→Lobith).
   Leave-one-out cross-validation chose **a = 0.10, b = 0.30**. Typical out-of-sample error is a factor of ×1.17. See `docs/CALIBRATION.md`.
4. **History.** `build/events.json`: 7 waterborne outbreaks + 4 river contamination events, each hand-checked with
   WHO / PAHO / UNEP / CDC / peer-reviewed sources. `build/build_events.py` traces each one and writes the map layers.

Every trace on the map is labelled **SIMULATED · MEAN FLOW**. It uses long-term mean flow, so it is not a forecast.

## Run / deploy
```
python -m venv .venv && .venv/Scripts/python -m pip install geopandas pyogrio pyarrow
# data/raw/: HydroRIVERS_v10_<region>_shp.zip (8 regions), HydroLAKES_polys_v10_shp.zip,
#            ne_10m_rivers_lake_centerlines.zip, ne_10m_lakes.zip, ne_10m_populated_places.zip, ne_10m_admin_0_countries.zip
.venv/Scripts/python build/build_rivers.py      # web/data/rivers_t1/t2/t3_<region>.geojson
.venv/Scripts/python build/build_mainstems.py   # main stems + names
.venv/Scripts/python build/build_lakes.py       # HydroLAKES >= 100 km2
.venv/Scripts/python build/export_pg.py         # rivers -> csv.gz for PostGIS
.venv/Scripts/python build/export_layers.py     # places, countries, lakes, main stems -> csv.gz
# on the Pi: sql/01_schema.sql, pi/load.sh, sql/02_indexes.sql; service: pi/systemd/waterways-web.service
.venv/Scripts/python build/build_events.py      # traces + calibration (needs the API)
.venv/Scripts/python scripts/push_to_pi.py [--server]   # web/ (+ .gz twins) -> /mnt/ssd/waterways/web/site
```
Map: MapLibre GL 5.24.0 on a custom OpenFreeMap (OpenMapTiles) style. It offers Esri World Imagery, Sentinel-2 cloudless 2025 (EOX),
AWS Terrain Tiles hillshade/3D, maplibre-contour contour lines, and a globe view.
Deep links: `?trace=lon,lat`, `?event=<id>`, `?river=<name>`, `?base=esri|s2`, `?3d=1`.

See `docs/SOURCES.md` (access test of every source) and `docs/DATA_ASSESSMENT.md` (login sources, WEL outbreak data).

## Planned stack
PostGIS 3.5 on Postgres 17, database `waterways`, data on the Pi SSD `/mnt/ssd`. The SSD moves to the Pi 5 when it arrives. Stdlib Python + psycopg 3 API → web map; Power BI later.

## Layout
- `build/` scripts that turn raw downloads into `web/data/`
- `web/` the map (MapLibre GL 5.24.0, OpenFreeMap dark basemap)
- `collectors/` API pulls (WHO DON, GHO, GDACS, Open-Meteo flood)
- `sql/` PostGIS schema + indexes
- `pi/` loader, systemd unit, trace API server (`pi/web/waterways_web.py`)
- `scripts/` deploy (`push_to_pi.py`)
- `data/raw`, `data/processed` (git-ignored once a repo exists)
- `notebooks/` exploration
- `docs/` source inventory, method notes
