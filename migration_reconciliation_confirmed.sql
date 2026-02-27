-- 核對確認記錄表
-- 請在 Supabase SQL Editor 手動執行此 migration
-- 每次勾選確認產生一筆記錄，SQL 函數 SUM 所有重疊區間的已確認數量

CREATE TABLE IF NOT EXISTS reconciliation_confirmed (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  product_id UUID NOT NULL REFERENCES products(id),
  date_from DATE NOT NULL,
  date_to DATE NOT NULL,
  assembly_qty INTEGER NOT NULL DEFAULT 0,
  packaging_qty INTEGER NOT NULL DEFAULT 0,
  confirmed_item_ids JSONB DEFAULT '[]',
  confirmed_by TEXT NOT NULL,
  confirmed_at TIMESTAMPTZ DEFAULT now(),
  note TEXT
);

CREATE INDEX IF NOT EXISTS idx_reconciliation_confirmed_product
  ON reconciliation_confirmed(product_id);

COMMENT ON TABLE reconciliation_confirmed IS '核對確認鎖定記錄（逐筆勾選）';

-- 如果已建過舊版（有 UNIQUE 限制），執行以下修改：
-- ALTER TABLE reconciliation_confirmed DROP CONSTRAINT IF EXISTS reconciliation_confirmed_product_id_date_from_date_to_key;
-- ALTER TABLE reconciliation_confirmed ADD COLUMN IF NOT EXISTS confirmed_item_ids JSONB DEFAULT '[]';
-- ALTER TABLE reconciliation_confirmed ALTER COLUMN assembly_qty SET DEFAULT 0;
-- ALTER TABLE reconciliation_confirmed ALTER COLUMN packaging_qty SET DEFAULT 0;
