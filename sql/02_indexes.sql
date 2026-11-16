-- run after COPY
ALTER TABLE rivers ALTER COLUMN geom TYPE geometry(Geometry, 4326) USING ST_SetSRID(geom, 4326);
CREATE INDEX IF NOT EXISTS rivers_geom_gix ON rivers USING gist (geom);
CREATE INDEX IF NOT EXISTS rivers_next_down_ix ON rivers (next_down);
CREATE INDEX IF NOT EXISTS rivers_main_riv_ix ON rivers (main_riv);
CREATE INDEX IF NOT EXISTS places_geom_gix ON places USING gist (geom);
CREATE INDEX IF NOT EXISTS countries_geom_gix ON countries USING gist (geom);
CREATE INDEX IF NOT EXISTS lakes_geom_gix ON lakes USING gist (geom);
ANALYZE;

-- small pieces make point-in-polygon tests fast (China, Russia, the Caspian are huge polygons)
DROP TABLE IF EXISTS countries_sub;
CREATE TABLE countries_sub AS SELECT iso3, name, ST_Subdivide(geom, 128) AS geom FROM countries;
CREATE INDEX ON countries_sub USING gist (geom);
DROP TABLE IF EXISTS lakes_sub;
CREATE TABLE lakes_sub AS SELECT hylak_id, ST_Subdivide(geom, 128) AS geom FROM lakes WHERE area_km2 >= 5;
CREATE INDEX lakes_sub_gix ON lakes_sub USING gist (geom);
ANALYZE countries_sub; ANALYZE lakes_sub;
