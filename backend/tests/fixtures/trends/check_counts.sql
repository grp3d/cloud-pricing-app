-- Expected Trends counts for tests/fixtures/trends (019, T007). Run from backend/:
--   uv run python -c "import duckdb; print(duckdb.sql(open('tests/fixtures/trends/check_counts.sql').read()))"
-- To check revision 1 of 2026-09-21 instead, change the filter to NOT LIKE '%20260921T000002Z%'.
-- Comparable price per (date, location, sku): on-demand, first tier with a non-zero price
-- (ordered by numeric begin_range); 0 when every tier is 0; NULL when the price is NULL.
WITH od AS (
  SELECT snapshot_date AS d, region AS location, sku, price, try_cast(begin_range AS DOUBLE) AS b
  FROM read_parquet('tests/fixtures/trends/aws/parquet/price_fact/*/*/part-*.parquet', filename = true)
  WHERE term = 'OnDemand' AND filename NOT LIKE '%20260921T000001Z%'   -- current revision of 2026-09-21 only
),
cp AS (
  SELECT d, location, sku,
         CASE WHEN bool_or(price IS NULL) THEN NULL
              ELSE coalesce(arg_min(price, b) FILTER (WHERE price <> 0), 0) END AS price
  FROM od GROUP BY d, location, sku
),
svc AS (SELECT DISTINCT region AS location, sku, service_code FROM read_parquet('tests/fixtures/trends/aws/parquet/product_dim/*/*/*.parquet')),
weeks AS (SELECT DISTINCT d, lead(d) OVER (ORDER BY d) AS nd FROM (SELECT DISTINCT d FROM cp)),
pairs AS (SELECT d AS from_d, nd AS to_d FROM weeks WHERE nd IS NOT NULL),
pa AS (SELECT p.from_d, p.to_d, c.location, c.sku, c.price FROM pairs p JOIN cp c ON c.d = p.from_d),
pb AS (SELECT p.from_d, p.to_d, c.location, c.sku, c.price FROM pairs p JOIN cp c ON c.d = p.to_d),
j AS (
  SELECT from_d, to_d, location, sku, a.price AS old_price, b.price AS new_price,
         a.sku IS NOT NULL AS in_old, b.sku IS NOT NULL AS in_new,
         coalesce(a.price > 0 AND b.price > 0, false) AS ok
  FROM pa a FULL JOIN pb b USING (from_d, to_d, location, sku)
)
SELECT from_d, to_d, location, s.service_code,
  count(*) FILTER (WHERE ok)                              AS compared,
  count(*) FILTER (WHERE ok AND new_price = old_price)    AS unchanged,
  count(*) FILTER (WHERE ok AND new_price > old_price)    AS increased,
  count(*) FILTER (WHERE ok AND new_price < old_price)    AS decreased,
  count(*) FILTER (WHERE NOT in_old)                      AS added,
  count(*) FILTER (WHERE NOT in_new)                      AS removed,
  count(*) FILTER (WHERE in_old AND in_new AND NOT ok)    AS excluded
FROM j JOIN svc s USING (location, sku)
GROUP BY ALL ORDER BY 1, 3, 4;
