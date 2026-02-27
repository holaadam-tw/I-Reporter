-- 自動登打同步記錄表
-- 請在 Supabase SQL Editor 手動執行此 migration

CREATE TABLE IF NOT EXISTS sync_log (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  table_name TEXT NOT NULL,
  record_id UUID NOT NULL,
  target_system TEXT NOT NULL DEFAULT 'ERP',
  status TEXT NOT NULL CHECK (status IN ('success','failed')),
  error_message TEXT,
  synced_by TEXT DEFAULT 'auto-typer',
  synced_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sync_log_lookup
  ON sync_log(table_name, record_id, target_system);

COMMENT ON TABLE sync_log IS '自動登打同步記錄';
