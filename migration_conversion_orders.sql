-- ============================================================
-- Migration: conversion_orders — 成品轉換單
-- Execute this in Supabase SQL Editor
-- ============================================================

-- 1. 建表
CREATE TABLE IF NOT EXISTS conversion_orders (
  id               UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  order_no         TEXT UNIQUE,
  conversion_date  DATE NOT NULL DEFAULT CURRENT_DATE,
  from_product_id  UUID NOT NULL REFERENCES products(id),
  to_product_id    UUID NOT NULL REFERENCES products(id),
  qty              INTEGER NOT NULL DEFAULT 0,
  reason           TEXT,
  note             TEXT,
  status           TEXT NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending','completed','cancelled')),
  created_by       TEXT,
  completed_at     TIMESTAMPTZ,
  created_at       TIMESTAMPTZ DEFAULT now()
);

-- 2. 索引
CREATE INDEX IF NOT EXISTS idx_conversion_orders_date
  ON conversion_orders (conversion_date DESC);
CREATE INDEX IF NOT EXISTS idx_conversion_orders_from
  ON conversion_orders (from_product_id);
CREATE INDEX IF NOT EXISTS idx_conversion_orders_to
  ON conversion_orders (to_product_id);

-- 3. RLS（匹配現有 anon_all 權限模式）
ALTER TABLE conversion_orders ENABLE ROW LEVEL SECURITY;

CREATE POLICY anon_all ON conversion_orders
  FOR ALL TO anon
  USING (true) WITH CHECK (true);

-- 4. Trigger: 自動產生 order_no (CNV-YYYYMMDD-XXX)
CREATE OR REPLACE FUNCTION generate_conversion_order_no()
RETURNS TRIGGER AS $$
DECLARE
  date_str TEXT;
  seq INT;
BEGIN
  date_str := TO_CHAR(NEW.conversion_date, 'YYYYMMDD');

  SELECT COUNT(*) + 1
    INTO seq
    FROM conversion_orders
   WHERE conversion_date = NEW.conversion_date;

  NEW.order_no := 'CNV-' || date_str || '-' || LPAD(seq::TEXT, 3, '0');

  LOOP
    BEGIN
      RETURN NEW;
    EXCEPTION WHEN unique_violation THEN
      seq := seq + 1;
      NEW.order_no := 'CNV-' || date_str || '-' || LPAD(seq::TEXT, 3, '0');
    END;
  END LOOP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_conversion_order_no
  BEFORE INSERT ON conversion_orders FOR EACH ROW
  WHEN (NEW.order_no IS NULL)
  EXECUTE FUNCTION generate_conversion_order_no();
