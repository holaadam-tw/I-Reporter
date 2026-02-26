-- ============================================================
-- Migration 010: Fix order_no conflicts + date-based reconciliation
-- Execute this in Supabase SQL Editor
-- ============================================================

-- ===================
-- Fix 1: order_no duplicate conflict (409 error)
-- ===================

DROP TRIGGER IF EXISTS set_assembly_order_no ON assembly_orders;
DROP TRIGGER IF EXISTS set_packaging_order_no ON packaging_orders;
DROP TRIGGER IF EXISTS set_testing_order_no ON testing_orders;
DROP FUNCTION IF EXISTS generate_order_no();

CREATE OR REPLACE FUNCTION generate_order_no()
RETURNS TRIGGER AS $$
DECLARE
  prefix TEXT;
  date_str TEXT;
  seq INT;
BEGIN
  IF TG_TABLE_NAME = 'assembly_orders' THEN prefix := 'ASM';
  ELSIF TG_TABLE_NAME = 'packaging_orders' THEN prefix := 'PKG';
  ELSIF TG_TABLE_NAME = 'testing_orders' THEN prefix := 'TST';
  END IF;

  date_str := TO_CHAR(NEW.order_date, 'YYYYMMDD');

  EXECUTE format(
    'SELECT COUNT(*) + 1 FROM %I WHERE order_date = $1',
    TG_TABLE_NAME
  ) INTO seq USING NEW.order_date;

  NEW.order_no := prefix || '-' || date_str || '-' || LPAD(seq::TEXT, 3, '0');

  LOOP
    BEGIN
      RETURN NEW;
    EXCEPTION WHEN unique_violation THEN
      seq := seq + 1;
      NEW.order_no := prefix || '-' || date_str || '-' || LPAD(seq::TEXT, 3, '0');
    END;
  END LOOP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_assembly_order_no
  BEFORE INSERT ON assembly_orders FOR EACH ROW
  WHEN (NEW.order_no IS NULL) EXECUTE FUNCTION generate_order_no();

CREATE TRIGGER set_packaging_order_no
  BEFORE INSERT ON packaging_orders FOR EACH ROW
  WHEN (NEW.order_no IS NULL) EXECUTE FUNCTION generate_order_no();

CREATE TRIGGER set_testing_order_no
  BEFORE INSERT ON testing_orders FOR EACH ROW
  WHEN (NEW.order_no IS NULL) EXECUTE FUNCTION generate_order_no();


-- ===================
-- Fix 2: v_reconciliation view - date-based comparison
-- ===================

DROP VIEW IF EXISTS v_reconciliation;

CREATE OR REPLACE VIEW v_reconciliation AS
WITH asm AS (
  SELECT p.product_id AS product_code, p.product_name, p.id AS pid, ao.order_date,
    SUM(ai.qty) AS day_qty
  FROM assembly_items ai
  JOIN assembly_orders ao ON ao.id = ai.order_id
  JOIN products p ON p.id = ai.product_id
  GROUP BY p.id, p.product_id, p.product_name, ao.order_date
),
pkg AS (
  SELECT p.product_id AS product_code, p.product_name, p.id AS pid, po.order_date,
    SUM(pi2.qty) AS day_qty
  FROM packaging_items pi2
  JOIN packaging_orders po ON po.id = pi2.order_id
  JOIN products p ON p.id = pi2.product_id
  GROUP BY p.id, p.product_id, p.product_name, po.order_date
),
combined AS (
  SELECT
    COALESCE(a.product_code, k.product_code) AS product_code,
    COALESCE(a.product_name, k.product_name) AS product_name,
    COALESCE(a.pid, k.pid) AS product_id,
    COALESCE(a.order_date, k.order_date) AS order_date,
    COALESCE(a.day_qty, 0) AS assembly_qty,
    COALESCE(k.day_qty, 0) AS packaging_qty,
    COALESCE(a.day_qty, 0) - COALESCE(k.day_qty, 0) AS diff
  FROM asm a
  FULL OUTER JOIN pkg k ON a.product_code = k.product_code AND a.order_date = k.order_date
),
resolved AS (
  SELECT DISTINCT ON (product_id) product_id, resolved_at, resolved_by,
    note AS resolved_note, hidden
  FROM reconciliation_resolved ORDER BY product_id, resolved_at DESC
)
SELECT c.*, c.order_date AS first_asm_date, c.order_date AS first_pkg_date,
  r.resolved_at, r.resolved_by, r.resolved_note, COALESCE(r.hidden, false) AS hidden,
  CASE
    WHEN c.assembly_qty = 0 THEN 'missing_asm'
    WHEN c.packaging_qty = 0 THEN 'missing_pkg'
    WHEN c.assembly_qty <> c.packaging_qty THEN 'qty_mismatch'
    ELSE 'matched'
  END AS status,
  CASE
    WHEN c.assembly_qty = 0 THEN '有包裝無組裝'
    WHEN c.packaging_qty = 0 THEN '有組裝無包裝'
    WHEN c.assembly_qty <> c.packaging_qty THEN '數量差異'
    ELSE '核對一致'
  END AS status_desc
FROM combined c
LEFT JOIN resolved r ON r.product_id = c.product_id
ORDER BY
  CASE WHEN c.assembly_qty = 0 THEN 0 WHEN c.packaging_qty = 0 THEN 0
    WHEN c.assembly_qty <> c.packaging_qty THEN 1 ELSE 2 END,
  c.order_date DESC;

GRANT SELECT ON v_reconciliation TO anon, authenticated;
