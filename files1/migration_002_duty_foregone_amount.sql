-- =====================================================================
-- MIGRATION 002: "Duty Fg" is an amount, not a flag.
--
-- The Part III duty tables print a 'Duty Fg' row that holds the duty foregone as an AMOUNT
-- (e.g. 84501.79). The first schema stored it as VARCHAR(5) "duty_foregone_flag", which cannot hold it.
-- Run on a database created from boe_schema.sql before this change. Numeric-looking old values are kept.
-- Dialect: PostgreSQL. Safe to run twice.
-- =====================================================================

BEGIN;

ALTER TABLE boe_item_duty ADD COLUMN IF NOT EXISTS duty_foregone NUMERIC(16,2);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'boe_item_duty' AND column_name = 'duty_foregone_flag') THEN
        UPDATE boe_item_duty
           SET duty_foregone = duty_foregone_flag::numeric
         WHERE duty_foregone IS NULL AND duty_foregone_flag ~ '^-?[0-9]+(\.[0-9]+)?$';
        ALTER TABLE boe_item_duty DROP COLUMN duty_foregone_flag;
    END IF;
END $$;

COMMIT;
