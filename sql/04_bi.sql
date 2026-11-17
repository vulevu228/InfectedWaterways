-- Milestone 6: read-only views for the Power BI report (exported to CSV by build/export_bi.py).
-- Small tables only: everything here runs in well under a second on the Pi 4.
CREATE SCHEMA IF NOT EXISTS bi;

-- WHO weekly cholera, every row moved to the Monday of its ISO week. 122 of 5,339 rows carry another weekday
-- (Sunday epi-week starts, report dates); Fri-Sun go to the NEXT Monday, Tue-Thu to the previous one.
-- A missing week means "no report", not zero cases, so nothing is filled in.
CREATE OR REPLACE FUNCTION bi.region_short(r text) RETURNS text LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE r WHEN 'African Region' THEN 'Africa' WHEN 'Eastern Mediterranean Region' THEN 'E. Mediterranean'
    WHEN 'European Region' THEN 'Europe' WHEN 'Region of the Americas' THEN 'Americas'
    WHEN 'South-East Asia Region' THEN 'SE Asia' WHEN 'Western Pacific Region' THEN 'W. Pacific' ELSE r END $$;

CREATE OR REPLACE VIEW bi.cholera_week AS
SELECT iso3, wk AS week, max(region) AS region, sum(cases)::int AS cases, sum(deaths)::int AS deaths
FROM (SELECT iso3, cases, deaths, bi.region_short(who_region) AS region,
             CASE WHEN extract(isodow FROM week) >= 5 THEN week + (8 - extract(isodow FROM week))::int
                  ELSE week - (extract(isodow FROM week) - 1)::int END AS wk
      FROM cholera_week) t
GROUP BY iso3, wk;

CREATE OR REPLACE VIEW bi.dim_week AS
SELECT d::date AS week, to_char(d, 'YYYYMMDD')::int AS week_key, extract(isoyear FROM d)::int AS iso_year,
       extract(week FROM d)::int AS iso_week, to_char(d, '"W"IW IYYY') AS week_label
FROM generate_series((SELECT min(week) FROM bi.cholera_week), (SELECT max(week) FROM bi.cholera_week), interval '7 days') d;

-- One row per country that has cholera data or WASH data. unsafe_pct = 100 - "at least basic" drinking water
-- (WHO/UNICEF JMP): people on unimproved sources or untreated surface water.
CREATE OR REPLACE VIEW bi.country AS
WITH c AS (SELECT DISTINCT ON (iso3) iso3, country, who_region FROM cholera_week ORDER BY iso3, week DESC),
     ids AS (SELECT iso3 FROM wash UNION SELECT iso3 FROM c)
SELECT i.iso3, CASE i.iso3 WHEN 'COD' THEN 'DR Congo' WHEN 'COG' THEN 'Congo' WHEN 'TZA' THEN 'Tanzania' WHEN 'SYR' THEN 'Syria'
         WHEN 'IRN' THEN 'Iran' WHEN 'VEN' THEN 'Venezuela' WHEN 'BOL' THEN 'Bolivia' WHEN 'LAO' THEN 'Laos' WHEN 'PRK' THEN 'North Korea'
         WHEN 'KOR' THEN 'South Korea' WHEN 'RUS' THEN 'Russia' WHEN 'VNM' THEN 'Viet Nam' WHEN 'FSM' THEN 'Micronesia'
         WHEN 'MDA' THEN 'Moldova' WHEN 'CAF' THEN 'Central African Rep.' WHEN 'GBR' THEN 'United Kingdom' WHEN 'USA' THEN 'United States'
         WHEN 'PSE' THEN 'Palestine' ELSE coalesce(c.country, p.name, i.iso3) END AS country, coalesce(bi.region_short(c.who_region), 'No WHO cholera data') AS who_region,
       p.pop, p.year AS pop_year, w.basic_pct, w.safe_pct, w.year AS wash_year,
       round((100 - w.basic_pct)::numeric, 1)::float8 AS unsafe_pct,
       CASE WHEN w.basic_pct IS NULL THEN 'No WASH data' WHEN 100 - w.basic_pct < 5 THEN 'Under 5 %'
            WHEN 100 - w.basic_pct < 15 THEN '5–15 %' WHEN 100 - w.basic_pct < 30 THEN '15–30 %' ELSE '30 % +' END AS unsafe_band,
       CASE WHEN w.basic_pct IS NULL THEN 4 WHEN 100 - w.basic_pct < 5 THEN 0 WHEN 100 - w.basic_pct < 15 THEN 1
            WHEN 100 - w.basic_pct < 30 THEN 2 ELSE 3 END AS band_order,
       c.iso3 IS NOT NULL AS has_cholera
FROM ids i LEFT JOIN c USING (iso3) LEFT JOIN country_pop p USING (iso3) LEFT JOIN wash w USING (iso3);

-- GDACS floods per country and start week (multi-country events have no iso3 and are left out)
CREATE OR REPLACE VIEW bi.flood AS
SELECT eventid, iso3, initcap(alert) AS alert, CASE lower(alert) WHEN 'red' THEN 2 WHEN 'orange' THEN 1 ELSE 0 END AS alert_order,
       from_date::date AS from_date, (date_trunc('week', from_date))::date AS week,
       greatest(1, (to_date::date - from_date::date) + 1) AS days, name
FROM floods WHERE iso3 IS NOT NULL AND length(iso3) = 3;

-- Event study: every flood in a country with WHO cholera data, cholera cases 4 weeks before to 8 weeks after the
-- flood's start week, against that country's own baseline (mean reported weekly cases in weeks -12..-5).
-- Kept only when the baseline has >= 4 reported weeks and > 0 cases, and the whole -4..+8 window lies inside the data.
CREATE OR REPLACE VIEW bi.flood_lag AS
WITH lim AS (SELECT min(week) AS w0, max(week) AS w1 FROM bi.cholera_week),
     ev AS (SELECT f.eventid, f.iso3, f.alert, f.alert_order, f.week FROM bi.flood f, lim
            WHERE f.iso3 IN (SELECT iso3 FROM bi.cholera_week) AND f.week - 84 >= lim.w0 AND f.week + 56 <= lim.w1),
     base AS (SELECT e.eventid, avg(c.cases)::float8 AS baseline, count(*) AS base_weeks
              FROM ev e JOIN bi.cholera_week c ON c.iso3 = e.iso3 AND c.week BETWEEN e.week - 84 AND e.week - 35
              GROUP BY e.eventid)
SELECT e.eventid, e.iso3, e.alert, e.alert_order, e.week AS flood_week, k AS lag_week, c.cases, b.baseline,
       (c.cases / b.baseline)::float8 AS ratio
FROM ev e JOIN base b USING (eventid) CROSS JOIN generate_series(-4, 8) k
LEFT JOIN bi.cholera_week c ON c.iso3 = e.iso3 AND c.week = e.week + 7 * k
WHERE b.base_weeks >= 4 AND b.baseline > 0;

-- WHO Disease Outbreak News, all reports; waterborne ones grouped by disease
CREATE OR REPLACE VIEW bi.don AS
SELECT url_name, published::date AS published, extract(year FROM published)::int AS year, title,
       replace(replace(country, 'Democratic Republic of the Congo', 'DR Congo'), 'United Republic of Tanzania', 'Tanzania') AS country, iso3, kind,
       CASE WHEN kind <> 'waterborne' THEN 'Not waterborne'
            WHEN disease ~* 'cholera|watery' THEN 'Cholera / AWD'
            WHEN disease ~* 'hepatitis' THEN 'Hepatitis A / E'
            WHEN disease ~* 'typhoid|enteric' THEN 'Typhoid'
            ELSE 'Other waterborne' END AS disease_group
FROM don_reports;
