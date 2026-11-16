-- Infected Waterways: PostGIS schema (database "waterways" on the Pi, PostGIS 3.5)
-- Loaded by pi/load.sh from the gzip CSVs that build/export_pg.py and build/export_layers.py write.

CREATE EXTENSION IF NOT EXISTS postgis;

-- HydroRIVERS v1.0 segments with mean discharge >= 1 m3/s (ORD_FLOW <= 6). One row = one river reach (~2-10 km).
-- next_down = the reach this one flows into (0 = mouth / inland sink). Closed under next_down.
DROP TABLE IF EXISTS rivers CASCADE;
CREATE TABLE rivers (
  hyriv_id    bigint PRIMARY KEY,
  next_down   bigint NOT NULL,
  main_riv    bigint NOT NULL,     -- id of the system's outlet reach
  length_km   real,
  dist_dn_km  real,                -- distance from this reach to the outlet along the river
  dist_up_km  real,                -- distance to the farthest source upstream
  upland_skm  real,                -- upstream catchment area, km2
  dis_av_cms  real,                -- long-term mean discharge, m3/s (HydroSHEDS / WaterGAP)
  ord_stra    smallint,            -- Strahler order
  ord_clas    smallint,            -- classical order (1 = main stem)
  ord_flow    smallint,            -- log10 discharge class (1 = >= 100,000 m3/s ... 6 = >= 1 m3/s)
  endorheic   smallint,            -- 1 = drains to an inland sink
  hybas_l12   bigint,              -- HydroBASINS level-12 sub-basin id
  region      text,
  geom        geometry             -- set to LineString/MultiLineString 4326 after load
);

-- Natural Earth 10m populated places (public domain): cities passed by a trace
DROP TABLE IF EXISTS places;
CREATE TABLE places (id serial PRIMARY KEY, name text, country text, iso3 text, pop_max bigint, rank smallint,
                     capital text, geom geometry(Point, 4326));

-- Natural Earth 10m admin-0 countries (public domain): countries a trace passes through
DROP TABLE IF EXISTS countries;
CREATE TABLE countries (iso3 text, name text, geom geometry(MultiPolygon, 4326));

-- HydroLAKES v1.0 (CC BY 4.0), lakes >= 1 km2: lakes a trace passes through, with residence time
DROP TABLE IF EXISTS lakes;
CREATE TABLE lakes (hylak_id bigint PRIMARY KEY, name text, country text, type text, area_km2 real,
                    vol_mcm real, depth_m real, dis_cms real, res_days real, geom geometry(MultiPolygon, 4326));

-- named main stems (build/build_mainstems.py)
DROP TABLE IF EXISTS mainstems;
CREATE TABLE mainstems (main_riv bigint PRIMARY KEY, name text, len_km real, dis_cms real, area_km2 real, sink text);
