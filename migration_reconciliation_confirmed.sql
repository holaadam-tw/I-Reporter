-- 核對確認記錄表
-- 請在 Supabase SQL Editor 手動執行此 migration

CREATE TABLE IF NOT EXISTS reconciliation_confirmed (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  product_id UUID NOT NULL REFERENCES products(id),
  date_from DATE NOT NULL,
  date_to DATE NOT NULL,
  assembly_qty INTEGER NOT NULL,
  packaging_qty INTEGER NOT NULL,
  confirmed_by TEXT NOT NULL,
  confirmed_at TIMESTAMPTZ DEFAULT now(),
  note TEXT,
  UNIQUE(product_id, date_from, date_to)
);

COMMENT ON TABLE reconciliation_confirmed IS '核對確認鎖定記錄';
