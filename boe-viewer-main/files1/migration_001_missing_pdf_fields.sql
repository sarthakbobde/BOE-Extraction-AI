-- =====================================================================
-- MIGRATION 001: add Bill of Entry fields that were printed on the PDF
-- but missing from the first version of boe_schema.sql.
--
-- Run this ONLY on a database created from the OLD boe_schema.sql.
-- A database created from the current boe_schema.sql already has these columns.
-- Safe to run twice (IF NOT EXISTS). Dialect: PostgreSQL.
-- =====================================================================

BEGIN;

-- Page header / Part I footer
ALTER TABLE boe ADD COLUMN IF NOT EXISTS port_name           VARCHAR(100);   -- text after "PORT :"
ALTER TABLE boe ADD COLUMN IF NOT EXISTS copy_label          VARCHAR(30);    -- ASSESSED COPY / OUT OF CHARGE COPY
ALTER TABLE boe ADD COLUMN IF NOT EXISTS digital_signer      VARCHAR(200);
ALTER TABLE boe ADD COLUMN IF NOT EXISTS digitally_signed_at TIMESTAMPTZ;
ALTER TABLE boe ADD COLUMN IF NOT EXISTS signature_reason    VARCHAR(60);
ALTER TABLE boe ADD COLUMN IF NOT EXISTS signature_location  VARCHAR(60);
ALTER TABLE boe ADD COLUMN IF NOT EXISTS signature_status    VARCHAR(40);

-- Part II
ALTER TABLE boe_invoice           ADD COLUMN IF NOT EXISTS ad_code               VARCHAR(20);  -- 6. AD CODE
ALTER TABLE boe_invoice_party     ADD COLUMN IF NOT EXISTS aeo                   VARCHAR(50);  -- 5. AEO
ALTER TABLE boe_invoice_valuation ADD COLUMN IF NOT EXISTS freight_currency_code VARCHAR(5);   -- 14. Cur (2nd value)
ALTER TABLE boe_invoice_valuation ADD COLUMN IF NOT EXISTS insurance_unit        VARCHAR(10);  -- PERCENT / AMOUNT

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'boe_invoice_valuation_insurance_unit_check') THEN
        ALTER TABLE boe_invoice_valuation
            ADD CONSTRAINT boe_invoice_valuation_insurance_unit_check
            CHECK (insurance_unit IN ('PERCENT','AMOUNT'));
    END IF;
END $$;

-- Part III
ALTER TABLE boe_invoice_item ADD COLUMN IF NOT EXISTS upi NUMERIC(16,6);   -- 11. UPI (Unit Price Invoiced)

-- Optional back-fill: existing insurance values were all printed as percentages in the sample bills.
-- UPDATE boe_invoice_valuation SET insurance_unit = 'PERCENT' WHERE insurance IS NOT NULL AND insurance_unit IS NULL;

COMMIT;
