#!/bin/bash
# Load the gzip CSVs in /mnt/ssd/waterways/load into the "waterways" PostGIS database. Run as emir on the Pi.
set -euo pipefail
L=/mnt/ssd/waterways/load
cd /home/emir/waterways
psql -q -v ON_ERROR_STOP=1 -d waterways -f sql/01_schema.sql
for f in $L/rivers_*.csv.gz; do
  zcat "$f" | psql -q -v ON_ERROR_STOP=1 -d waterways -c "\copy rivers (hyriv_id,next_down,main_riv,length_km,dist_dn_km,dist_up_km,upland_skm,dis_av_cms,ord_stra,ord_clas,ord_flow,endorheic,hybas_l12,region,geom) FROM STDIN WITH (FORMAT csv)"
  echo "$(date +%T) loaded $(basename $f)"
done
zcat $L/places.csv.gz    | psql -q -d waterways -c "\copy places (name,country,iso3,pop_max,rank,capital,geom) FROM STDIN WITH (FORMAT csv)"
zcat $L/countries.csv.gz | psql -q -d waterways -c "\copy countries (iso3,name,geom) FROM STDIN WITH (FORMAT csv)"
zcat $L/lakes.csv.gz     | psql -q -d waterways -c "\copy lakes (hylak_id,name,country,type,area_km2,vol_mcm,depth_m,dis_cms,res_days,geom) FROM STDIN WITH (FORMAT csv)"
zcat $L/mainstems.csv.gz | psql -q -d waterways -c "\copy mainstems (main_riv,name,len_km,dis_cms,area_km2,sink) FROM STDIN WITH (FORMAT csv)"
echo "$(date +%T) side tables loaded, indexing"
psql -q -v ON_ERROR_STOP=1 -d waterways -f sql/02_indexes.sql
psql -d waterways -Atc "select 'rivers', count(*) from rivers union all select 'places', count(*) from places union all select 'countries', count(*) from countries union all select 'lakes', count(*) from lakes union all select 'mainstems', count(*) from mainstems; select pg_size_pretty(pg_database_size('waterways'))"
