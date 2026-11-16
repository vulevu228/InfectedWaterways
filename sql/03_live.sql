-- Milestone 2: live / real-data layer, filled daily by pi/collect/collect_live.py

-- WHO Global Cholera and AWD dashboard, weekly cases by country since 2023 (public CSV "cholera_adm0_week")
CREATE TABLE IF NOT EXISTS cholera_week (
  iso3 text, country text, week date, cases integer, deaths integer, who_region text,
  lon real, lat real, PRIMARY KEY (iso3, week));

-- WHO Disease Outbreak News, every report since 1996; kind = waterborne | other
CREATE TABLE IF NOT EXISTS don_reports (
  url_name text PRIMARY KEY, published timestamptz, title text, disease text, country text, iso3 text,
  kind text, summary text);
CREATE INDEX IF NOT EXISTS don_reports_pub_ix ON don_reports (published);

-- GDACS flood events (source GLOFAS / others), one row per event, last episode wins
CREATE TABLE IF NOT EXISTS floods (
  eventid bigint PRIMARY KEY, episodeid integer, name text, country text, iso3 text, alert text, alertscore real,
  from_date timestamptz, to_date timestamptz, is_current boolean, source text, report_url text,
  geom geometry(Point, 4326), props jsonb, updated timestamptz DEFAULT now());

-- River gauges: one virtual gauge (GloFAS cell via Open-Meteo) near the mouth of each big river system
CREATE TABLE IF NOT EXISTS gauges (
  main_riv bigint PRIMARY KEY, name text, hyriv_id bigint, dis_av real, dist_dn_km real,
  lon real, lat real,           -- point on the HydroRIVERS main stem
  glon real, glat real,         -- snapped GloFAS cell (largest discharge in a 5 x 5 window, 0.05 deg)
  snap_q real);
CREATE TABLE IF NOT EXISTS gauge_flow (main_riv bigint, day date, q real, PRIMARY KEY (main_riv, day));

-- population (GHS-POP R2023A, epoch 2025, 30 arcsec aggregated to 0.025 deg cells): people living along a trace
CREATE TABLE IF NOT EXISTS pop (id serial PRIMARY KEY, pop real, geom geometry(Point, 4326));
