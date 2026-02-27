-- ============================================================
-- fn_reconcile_by_date_range: 區間累計核對函數
-- 在指定日期範圍內，按產品彙總組裝/包裝數量並比較
-- 扣除已確認鎖定的數量（reconciliation_confirmed）
-- ============================================================

DROP FUNCTION IF EXISTS fn_reconcile_by_date_range(DATE, DATE);

CREATE OR REPLACE FUNCTION fn_reconcile_by_date_range(
  p_date_from DATE,
  p_date_to DATE
)
RETURNS TABLE (
  product_code TEXT,
  product_name TEXT,
  product_id UUID,
  order_date DATE,
  first_asm_date DATE,
  first_pkg_date DATE,
  assembly_qty BIGINT,
  packaging_qty BIGINT,
  diff BIGINT,
  resolved_at TIMESTAMPTZ,
  resolved_by TEXT,
  resolved_note TEXT,
  hidden BOOLEAN,
  confirmed_at TIMESTAMPTZ,
  confirmed_by TEXT,
  confirmed_asm_qty BIGINT,
  confirmed_pkg_qty BIGINT,
  status TEXT,
  status_desc TEXT
) LANGUAGE plpgsql AS $$
BEGIN
  RETURN QUERY
  WITH asm AS (
    SELECT p.product_id AS p_code, p.product_name AS p_name, p.id AS pid,
      SUM(ai.qty) AS total_qty,
      MIN(ao.order_date) AS first_date
    FROM assembly_items ai
    JOIN assembly_orders ao ON ao.id = ai.order_id
    JOIN products p ON p.id = ai.product_id
    WHERE ao.order_date BETWEEN p_date_from AND p_date_to
    GROUP BY p.id, p.product_id, p.product_name
  ),
  pkg AS (
    SELECT p.product_id AS p_code, p.product_name AS p_name, p.id AS pid,
      SUM(pi2.qty) AS total_qty,
      MIN(po.order_date) AS first_date
    FROM packaging_items pi2
    JOIN packaging_orders po ON po.id = pi2.order_id
    JOIN products p ON p.id = pi2.product_id
    WHERE po.order_date BETWEEN p_date_from AND p_date_to
    GROUP BY p.id, p.product_id, p.product_name
  ),
  -- 已確認鎖定的數量（日期區間有重疊就算）
  conf AS (
    SELECT rc.product_id AS pid,
      SUM(rc.assembly_qty) AS conf_asm,
      SUM(rc.packaging_qty) AS conf_pkg,
      MAX(rc.confirmed_at) AS last_confirmed_at,
      MAX(rc.confirmed_by) AS last_confirmed_by
    FROM reconciliation_confirmed rc
    WHERE rc.date_from <= p_date_to AND rc.date_to >= p_date_from
    GROUP BY rc.product_id
  ),
  combined AS (
    SELECT
      COALESCE(a.p_code, k.p_code) AS product_code,
      COALESCE(a.p_name, k.p_name) AS product_name,
      COALESCE(a.pid, k.pid) AS product_id,
      COALESCE(a.first_date, k.first_date) AS order_date,
      a.first_date AS first_asm_date,
      k.first_date AS first_pkg_date,
      GREATEST(COALESCE(a.total_qty, 0) - COALESCE(cf.conf_asm, 0), 0) AS assembly_qty,
      GREATEST(COALESCE(k.total_qty, 0) - COALESCE(cf.conf_pkg, 0), 0) AS packaging_qty,
      GREATEST(COALESCE(a.total_qty, 0) - COALESCE(cf.conf_asm, 0), 0)
        - GREATEST(COALESCE(k.total_qty, 0) - COALESCE(cf.conf_pkg, 0), 0) AS diff,
      cf.last_confirmed_at,
      cf.last_confirmed_by,
      COALESCE(cf.conf_asm, 0) AS confirmed_asm_qty,
      COALESCE(cf.conf_pkg, 0) AS confirmed_pkg_qty
    FROM asm a
    FULL OUTER JOIN pkg k ON a.pid = k.pid
    LEFT JOIN conf cf ON cf.pid = COALESCE(a.pid, k.pid)
  ),
  resolved AS (
    SELECT DISTINCT ON (rr.product_id) rr.product_id, rr.resolved_at, rr.resolved_by,
      rr.note AS resolved_note, rr.hidden
    FROM reconciliation_resolved rr ORDER BY rr.product_id, rr.resolved_at DESC
  )
  SELECT
    c.product_code,
    c.product_name,
    c.product_id,
    c.order_date,
    c.first_asm_date,
    c.first_pkg_date,
    c.assembly_qty,
    c.packaging_qty,
    c.diff,
    r.resolved_at,
    r.resolved_by,
    r.resolved_note,
    COALESCE(r.hidden, false) AS hidden,
    c.last_confirmed_at AS confirmed_at,
    c.last_confirmed_by AS confirmed_by,
    c.confirmed_asm_qty,
    c.confirmed_pkg_qty,
    CASE
      WHEN c.assembly_qty = 0 AND c.packaging_qty = 0 THEN 'matched'
      WHEN c.assembly_qty = 0 THEN 'missing_asm'
      WHEN c.packaging_qty = 0 THEN 'missing_pkg'
      WHEN c.assembly_qty > c.packaging_qty AND c.packaging_qty > 0 THEN 'wip_normal'
      WHEN c.packaging_qty > c.assembly_qty THEN 'over_packaged'
      WHEN c.assembly_qty <> c.packaging_qty THEN 'qty_mismatch'
      ELSE 'matched'
    END AS status,
    CASE
      WHEN c.assembly_qty = 0 AND c.packaging_qty = 0 THEN '核對一致'
      WHEN c.assembly_qty = 0 THEN '有包裝無組裝'
      WHEN c.packaging_qty = 0 THEN '有組裝無包裝'
      WHEN c.assembly_qty > c.packaging_qty AND c.packaging_qty > 0 THEN '在製品(正常)'
      WHEN c.packaging_qty > c.assembly_qty THEN '包裝超出組裝'
      WHEN c.assembly_qty <> c.packaging_qty THEN '數量差異'
      ELSE '核對一致'
    END AS status_desc
  FROM combined c
  LEFT JOIN resolved r ON r.product_id = c.product_id
  WHERE NOT (c.assembly_qty = 0 AND c.packaging_qty = 0)
  ORDER BY
    CASE
      WHEN c.assembly_qty = 0 THEN 0
      WHEN c.packaging_qty = 0 THEN 0
      WHEN c.packaging_qty > c.assembly_qty THEN 1
      WHEN c.assembly_qty <> c.packaging_qty THEN 2
      WHEN c.assembly_qty > c.packaging_qty AND c.packaging_qty > 0 THEN 3
      ELSE 4
    END,
    c.order_date DESC;
END;
$$;
