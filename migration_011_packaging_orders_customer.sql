-- ============================================================
-- migration_011: packaging_orders 加入 customer_id 欄位
-- 在 Supabase SQL Editor 執行
-- ============================================================

ALTER TABLE packaging_orders ADD COLUMN IF NOT EXISTS customer_id UUID REFERENCES customers(id);

COMMENT ON COLUMN packaging_orders.customer_id IS '包裝單關聯客戶（可為 NULL 表示庫存）';
