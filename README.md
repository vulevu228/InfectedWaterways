# Infected Waterways

**Status:** Milestone 1 (world waterways map) in progress, 2026-11-16. Private repo.

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
| 1 | World waterways map + river graph | Web map of rivers ≥ 10 m³/s, named main stems, lakes ✅ (map); next: HydroRIVERS in PostGIS, downstream routing (`NEXT_DOWN`), travel time from discharge |
| 2 | Real-data layer | WHO GHO + OWID cholera history, WHO DON outbreak feed (daily), GDACS floods, WorldPop exposure |
| 3 | Spread simulator | Plume = load ÷ discharge × e^(−k·t), with per-pathogen decay rates k; arrival times + people exposed per city |
| 4 | Validation | Replay the 2005 Songhua→Amur benzene spill and the 2010 Haiti Artibonite cholera outbreak, then compare with reported arrival times |
| 5 | Map + dashboard | Web map (Count Down style) + Power BI report (real cholera vs. floods vs. WASH coverage) |
| 6 | Showcase scenarios | e.g. Lancang→Mekong→Tonle Sap seasonal flow reversal, Ganges–Brahmaputra delta, Niger, Danube |

## Run the map
```
python -m venv .venv && .venv/Scripts/python -m pip install geopandas pyogrio pyarrow
# put HydroRIVERS_v10_<region>_shp.zip (8 regions), ne_10m_rivers_lake_centerlines.zip, ne_10m_lakes.zip
# (and optionally HydroLAKES_polys_v10_shp.zip) into data/raw/
.venv/Scripts/python build/build_rivers.py
.venv/Scripts/python build/build_mainstems.py
.venv/Scripts/python build/build_lakes.py
cd web && python -m http.server 8799   # open http://127.0.0.1:8799
```
Layers: main stems (from the mouth, always the branch with the largest upstream area; named from Natural Earth),
mainstreams ≥ 1,000 m³/s, major rivers ≥ 100 m³/s, rivers ≥ 10 m³/s (loaded per region on zoom), lakes.
Click a river to highlight its whole river system.

See `docs/SOURCES.md` (access test of every source) and `docs/DATA_ASSESSMENT.md` (login sources, WEL outbreak data).

## Planned stack
Python collectors → PostgreSQL + PostGIS (Pi 5 data server once it arrives) → web map + Power BI.

## Layout
- `build/` scripts that turn raw downloads into `web/data/`
- `web/` the map (MapLibre GL 5.24.0, OpenFreeMap dark basemap)
- `collectors/` API pulls (WHO DON, GHO, GDACS, Open-Meteo flood)
- `sql/` PostGIS schema + routing functions
- `data/raw`, `data/processed` (git-ignored once a repo exists)
- `notebooks/` exploration
- `docs/` source inventory, method notes
