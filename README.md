# Infected Waterways

**Status:** Milestones 1–3 done (river graph + trace, live data layer with KPIs, spread simulator), 2026-11-16. Private repo.

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
| 2 | Real-data layer | ✅ Daily collector on the Pi: WHO weekly cholera by country (2023–now), WHO Disease Outbreak News (3,205 reports since 1996, 347 waterborne), GDACS floods, GloFAS river flow at 150 virtual gauges vs. the same season of the previous 5 years; GHS-POP 2025 population (people within 5 km of each trace); KPI panel with comparison periods |
| 3 | Spread simulator | ✅ Release anywhere: relative concentration = dilution (Q₀/Q) × die-off 10^(−t/T90), per pathogen with fast/typical/slow T90 from the literature; lakes add their residence time; optional today's flow from GloFAS; KPIs: km and days until 99.9 % gone, people and cities on that stretch |
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

5. **The world now (Milestone 2).** `pi/collect/collect_live.py` runs daily at 07:20 (`waterways-collect.timer`):

   | Source | What | Access |
   |---|---|---|
   | [WHO Global Cholera and AWD dashboard](https://who-global-cholera-and-awd-dashboard-1-who.hub.arcgis.com/) | weekly cholera cases and deaths per country since 2023 (public CSV item `cholera_adm0_week`) | open, no key |
   | [WHO Disease Outbreak News API](https://www.who.int/api/news/diseaseoutbreaknews) | every outbreak report since 1996, classified waterborne / other, matched to a country | open, no key, 100 per page |
   | [GDACS](https://www.gdacs.org/) | flood events of the last 120 days, all alert levels | open, no key, 100 per page |
   | [Open-Meteo Flood API](https://open-meteo.com/en/docs/flood-api) (GloFAS v4) | daily discharge at 150 virtual gauges near the mouths of the largest systems: last 30 days + 7-day forecast, and the same ±15 days in each of the previous 5 years | open, CC BY 4.0, non-commercial, ~1,000 weighted calls/day |
   | [GHS-POP R2023A](https://human-settlement.emergency.copernicus.eu/ghs_pop2023.php), epoch 2025 | population grid (30″, aggregated to 0.025°) for "people within 5 km of the river" | open, CC BY 4.0, one-time |

   KPIs (`GET /api/live`), each with a comparison: cholera cases in the last 4 weeks vs. the 4 weeks before; countries reporting;
   cases this year vs. the same weeks last year; current river floods; big rivers above / below normal for the season;
   people living within 5 km of a river ≥ 1 m³/s; countries with cholera **and** a river flood right now.
   The cholera window ends one week before the newest reported week because reports arrive late.

6. **Spread simulator (Milestone 3).** In the trace panel: relative concentration after full mixing at the release point =
   dilution by tributaries (Q₀/Q) × die-off 10^(−t/T90). Every pathogen has three T90 values (fast / typical / slow), because
   published river-water decay rates vary by orders of magnitude with sunlight, temperature and sediment:

   | Pathogen | T90 fast / typical / slow (days) | Basis |
   |---|---|---|
   | Vibrio cholerae | 1 / 3 / 32 | no reference value for river water (data gap in the Global Water Pathogen Project); 32 d = survival in riverbed sediment (PubMed 27193001) |
   | Salmonella Typhi | 0.5 / 4 / 48 | GWPP: < 1 h in sunlit water, 48–96 d in the dark at 15 °C |
   | Hepatitis A virus | 2.6 / 10 / 33 | Boehm et al. 2019 meta-analysis: mammalian viruses k = 0.07–0.9 / day in surface water |
   | E. coli (indicator) | 0.5 / 2 / 7 | GWPP: T90 2.2 d sunlit at 15 °C, < 7 d at 20–30 °C |
   | Cryptosporidium | 5 / 40 / 86 | GWPP: T90 38–86 d dark at 20–25 °C |
   | Chemical (no decay) | – | dilution only, as in the spills used for calibration |

   The "typical" value is our central assumption between the published extremes. Lakes on the path add their residence time
   to the die-off clock. "Today's flow" scales every reach by the river's current GloFAS anomaly (travel time ∝ r^−b).
   Output: km and days until 99.9 % is gone, people within 5 km of that stretch, cities on it, concentration curve with the
   fast–slow band. Ignores sediment storage, regrowth in estuaries and water treatment. Labelled **HYPOTHETICAL**.

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
.venv/Scripts/python build/build_pop.py         # GHS-POP 2025 -> pop.csv.gz; on the Pi: pi/load_pop.sh
.venv/Scripts/python scripts/push_to_pi.py [--server]   # web/ (+ .gz twins) -> /mnt/ssd/waterways/web/site
# on the Pi: sql/03_live.sql, then python3 pi/collect/collect_live.py --setup-gauges (once, ~20 min),
#            pi/systemd/waterways-collect.{service,timer} (daily 07:20)
```
Map: MapLibre GL 5.24.0 on a custom OpenFreeMap (OpenMapTiles) style. It offers Esri World Imagery, Sentinel-2 cloudless 2025 (EOX),
AWS Terrain Tiles hillshade/3D, maplibre-contour contour lines, and a globe view.
Deep links: `?trace=lon,lat`, `?event=<id>`, `?river=<name>`, `?base=esri|s2`, `?3d=1`, `?panel=cholera|floods|flow|people`, `?pathogen=cholera|typhoid|hepa|ecoli|crypto|tracer`.

Zoom: HydroRIVERS (a ~500 m model network that carries the flow data) fades out from zoom 7.5 to 10 and OpenStreetMap water areas and river lines take over, so the zoomed-in map shows the real banks.

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
