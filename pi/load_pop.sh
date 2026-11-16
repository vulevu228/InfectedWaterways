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
INSERT INTO meta VALUES ('people_total', (SELECT round(sum(pop))::text FROM pop)) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
SQL
echo "pop loaded $(date)"
psql -q -d waterways <<'SQL'
SET max_parallel_workers_per_gather = 3;
INSERT INTO meta VALUES ('people_5km', (
  SELECT round(sum(p.pop))::text FROM pop p
  WHERE EXISTS (SELECT 1 FROM rivers r WHERE ST_DWithin(r.geom, p.geom, 0.09)
                  AND ST_DWithin(r.geom::geography, p.geom::geography, 5000))))
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
INSERT INTO meta VALUES ('pop_source', 'GHS-POP R2023A epoch 2025, 0.025 deg cells') ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
SQL
echo "people_5km done $(date)"
psql -d waterways -Atc "select * from meta"
