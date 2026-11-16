#!/bin/sh
# load GHS-POP cells (build/build_pop.py) and compute the "people within 5 km of a river" KPI
set -e
psql -q -d waterways <<'SQL'
DROP TABLE IF EXISTS pop_raw; CREATE UNLOGGED TABLE pop_raw (lon real, lat real, pop real);
SQL
zcat /mnt/ssd/waterways/load/pop.csv.gz | psql -q -d waterways -c "\copy pop_raw FROM STDIN WITH (FORMAT csv)"
psql -q -d waterways <<'SQL'
DROP TABLE IF EXISTS pop;
CREATE TABLE pop AS SELECT row_number() OVER ()::int AS id, pop, ST_SetSRID(ST_Point(lon, lat), 4326) AS geom FROM pop_raw;
ALTER TABLE pop ADD PRIMARY KEY (id);
CREATE INDEX pop_geom_gix ON pop USING gist (geom);
DROP TABLE pop_raw; ANALYZE pop;
CREATE TABLE IF NOT EXISTS meta (key text PRIMARY KEY, value text);
INSERT INTO meta VALUES ('people_total', (SELECT round(sum(pop::float8))::text FROM pop)) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
SQL
echo "pop loaded $(date)"
# people_5km is computed on the PC (build/people_near_rivers.py): the PostGIS version of that join hung the 1 GB Pi 4
