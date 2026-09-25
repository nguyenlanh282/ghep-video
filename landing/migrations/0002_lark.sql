-- Lark Base sync: the row's record id in Lark, or the last error when pushing failed.
ALTER TABLE leads ADD COLUMN lark_record TEXT;
ALTER TABLE leads ADD COLUMN lark_error TEXT;
