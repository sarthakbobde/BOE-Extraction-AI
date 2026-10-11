-- =====================================================================
-- INDIAN CUSTOMS BILL OF ENTRY (BOE) — DATA MODEL
-- =====================================================================
-- Mirrors the printed document's Part I-VI / Section A-Z / Field N
-- structure so the app can drill down to any single field.
--
-- Hierarchy:  boe (1) -> boe_invoice (N) -> boe_invoice_item (N) -> boe_item_duty (N)
-- Everything else hangs off boe_id, invoice_id, or item_id.
--
-- Dialect: PostgreSQL (NUMERIC/BIGSERIAL). Swap BIGSERIAL for
-- BIGINT AUTO_INCREMENT / IDENTITY for MySQL / SQL Server.
-- =====================================================================


-- =====================================================================
-- ROOT: ONE ROW PER BILL OF ENTRY
-- =====================================================================

CREATE TABLE boe (
    boe_id              BIGSERIAL PRIMARY KEY,
    port_code           VARCHAR(10)  NOT NULL,   -- INDEL4
    port_name           VARCHAR(100),            -- text printed after "PORT :" in the page header
    be_no               VARCHAR(20)  NOT NULL,   -- 7526371
    be_date             DATE         NOT NULL,
    be_type             VARCHAR(5),              -- H
    iec_br              VARCHAR(30),             -- 0588000591/9
    copy_type           VARCHAR(30),             -- FIRST COPY / OOC COPY
    copy_label          VARCHAR(30),             -- second banner label: ASSESSED COPY / OUT OF CHARGE COPY
    gstin               VARCHAR(20),
    gst_type            VARCHAR(10),
    cb_code             VARCHAR(20),              -- customs broker code
    doc_type            VARCHAR(80),              -- BILL OF ENTRY FOR HOME CONSUMPTION
    total_invoices      SMALLINT,
    total_items         SMALLINT,
    total_containers    SMALLINT,
    total_packages      SMALLINT,
    gross_weight_kg     NUMERIC(12,3),
    barcode_ref         VARCHAR(50),              -- BE0140220261441
    -- Digital-signature block printed at the foot of Part I (page 1)
    digital_signer        VARCHAR(200),           -- "Digitally signed by DS CENTRAL BOARD OF INDIRECT TAXES AND CUSTOMS 10"
    digitally_signed_at   TIMESTAMPTZ,            -- "Date: 2026.09.08 11:08:58 IST"
    signature_reason      VARCHAR(60),            -- "Reason: CUSTOMS"
    signature_location    VARCHAR(60),            -- "Location: INDIA"
    signature_status      VARCHAR(40),            -- e.g. "Signature Not Verified"
    source_file         VARCHAR(255),             -- original PDF filename, for traceability
    extracted_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (port_code, be_no, be_date)
);

-- PART I - A. STATUS
CREATE TABLE boe_status (
    boe_id                  BIGINT PRIMARY KEY REFERENCES boe(boe_id) ON DELETE CASCADE,
    be_status               VARCHAR(20),   -- FIRST COPY / ...
    mode                    VARCHAR(10),   -- Air / Sea
    def_be                  VARCHAR(5),
    kaccha                  VARCHAR(5),
    sec_48                  VARCHAR(5),
    reimp                   VARCHAR(5),
    adv_be                  VARCHAR(5),
    assess                  VARCHAR(5),
    exam                    VARCHAR(5),
    hss                     VARCHAR(5),
    first_check             VARCHAR(5),
    prov_final              VARCHAR(5),
    country_of_origin       VARCHAR(60),
    country_of_consignment  VARCHAR(60),
    port_of_loading         VARCHAR(60),
    port_of_shipment        VARCHAR(60)
);

-- PART I - B. DECLARANT
CREATE TABLE boe_declarant (
    boe_id           BIGINT PRIMARY KEY REFERENCES boe(boe_id) ON DELETE CASCADE,
    importer_name    VARCHAR(200),
    importer_address TEXT,
    cb_name          VARCHAR(200),
    aeo              VARCHAR(50),
    ucr              VARCHAR(50),
    ad_code          VARCHAR(20)
);

-- PART I - C. DUTY SUMMARY (BOE-level totals, rolled up from item-level duty)
CREATE TABLE boe_duty_summary (
    boe_id                  BIGINT PRIMARY KEY REFERENCES boe(boe_id) ON DELETE CASCADE,
    bcd                     NUMERIC(14,2),
    acd                     NUMERIC(14,2),
    sws                     NUMERIC(14,2),
    nccd                    NUMERIC(14,2),
    add_duty                NUMERIC(14,2),
    cvd                     NUMERIC(14,2),
    igst                    NUMERIC(14,2),
    g_cess                  NUMERIC(14,2),
    total_assessable_value  NUMERIC(16,2),
    sg                      NUMERIC(14,2),
    saed                    NUMERIC(14,2),
    gsia                    NUMERIC(14,2),
    tta                     NUMERIC(14,2),
    health                  NUMERIC(14,2),
    total_duty              NUMERIC(14,2),
    interest                NUMERIC(14,2),
    penalty                 NUMERIC(14,2),
    fine                    NUMERIC(14,2),
    total_amount            NUMERIC(16,2)
);

-- PART I - D. MANIFEST
CREATE TABLE boe_manifest (
    boe_id           BIGINT PRIMARY KEY REFERENCES boe(boe_id) ON DELETE CASCADE,
    igm_no           VARCHAR(30),
    igm_date         DATE,
    inw_date         DATE,
    gigm_no          VARCHAR(30),
    gigm_date        DATE,
    mawb_no          VARCHAR(30),
    mawb_date        DATE,
    hawb_no          VARCHAR(30),
    hawb_date        DATE,
    packages         INT,
    gross_weight_kg  NUMERIC(12,3)
);

-- PART I - E. BOND DETAILS (repeatable)
CREATE TABLE boe_bond (
    bond_id      BIGSERIAL PRIMARY KEY,
    boe_id       BIGINT NOT NULL REFERENCES boe(boe_id) ON DELETE CASCADE,
    bond_no      VARCHAR(30),
    port         VARCHAR(30),
    bond_cd      VARCHAR(10),
    debt_amount  NUMERIC(14,2),
    bg_amount    NUMERIC(14,2)
);

-- PART I - F. PAYMENT DETAILS (repeats by Sr No)
CREATE TABLE boe_payment (
    payment_id   BIGSERIAL PRIMARY KEY,
    boe_id       BIGINT NOT NULL REFERENCES boe(boe_id) ON DELETE CASCADE,
    sr_no        INT,
    challan_no   VARCHAR(30),
    paid_on      DATE,
    amount       NUMERIC(14,2)
);

-- PART I - G. WAREHOUSE
CREATE TABLE boe_warehouse (
    boe_id     BIGINT PRIMARY KEY REFERENCES boe(boe_id) ON DELETE CASCADE,
    wbe_no     VARCHAR(30),
    wbe_date   DATE,
    wbe_site   VARCHAR(60),
    wh_code    VARCHAR(20)
);

-- PART I - H. PROCESSING DETAILS (Submission / Assessment / Examination / OOC / Finalisation)
CREATE TABLE boe_processing_event (
    event_id             BIGSERIAL PRIMARY KEY,
    boe_id               BIGINT NOT NULL REFERENCES boe(boe_id) ON DELETE CASCADE,
    event_name           VARCHAR(20) NOT NULL
                          CHECK (event_name IN ('SUBMISSION','ASSESSMENT','EXAMINATION','OOC','FINALISATION')),
    event_date           DATE,
    event_time           TIME,
    exchange_rate_text   VARCHAR(50)   -- e.g. '100 JPY=58.65INR'
);

-- PART I - J  and  PART IV - N. CONTAINER DETAILS
CREATE TABLE boe_container (
    container_id      BIGSERIAL PRIMARY KEY,
    boe_id            BIGINT NOT NULL REFERENCES boe(boe_id) ON DELETE CASCADE,
    sno               INT,
    lcl_fcl           VARCHAR(5),
    truck_number      VARCHAR(30),
    seal_number       VARCHAR(30),
    container_number  VARCHAR(30)
);


-- =====================================================================
-- PART II: INVOICE & VALUATION (one block per invoice on the BOE)
-- =====================================================================

-- PART II - A. INVOICE
CREATE TABLE boe_invoice (
    invoice_id            BIGSERIAL PRIMARY KEY,
    boe_id                BIGINT NOT NULL REFERENCES boe(boe_id) ON DELETE CASCADE,
    invoice_sno           INT NOT NULL,           -- 1.S.NO on Part II / Part IV-O
    invoice_no            VARCHAR(30) NOT NULL,   -- BYA48607
    invoice_date          DATE,
    purchase_order_no     VARCHAR(50),
    purchase_order_date   DATE,
    lc_no                 VARCHAR(50),
    lc_date               DATE,
    contract_no           VARCHAR(50),
    contract_date         DATE,
    ad_code               VARCHAR(20),            -- Part II "6. AD CODE" (invoice-level; Part I-B has the importer's)
    invoice_amount        NUMERIC(16,2),          -- matches Part I-I / Part IV-O summary
    currency_code         VARCHAR(5),
    UNIQUE (boe_id, invoice_sno)
);

-- PART II - B. TRANSACTING PARTIES (Buyer / Seller / Supplier / Third Party as rows)
CREATE TABLE boe_invoice_party (
    party_id     BIGSERIAL PRIMARY KEY,
    invoice_id   BIGINT NOT NULL REFERENCES boe_invoice(invoice_id) ON DELETE CASCADE,
    party_role   VARCHAR(15) NOT NULL
                 CHECK (party_role IN ('BUYER','SELLER','SUPPLIER','THIRD_PARTY')),
    name         VARCHAR(200),
    address      TEXT,
    country      VARCHAR(60),
    aeo          VARCHAR(50),               -- Part II-B "5. AEO" (Authorized Economic Operator)
    UNIQUE (invoice_id, party_role)
);

-- PART II - C. VALUATION   <-- "3. Insurance" lives here
CREATE TABLE boe_invoice_valuation (
    invoice_id          BIGINT PRIMARY KEY REFERENCES boe_invoice(invoice_id) ON DELETE CASCADE,
    invoice_value        NUMERIC(16,2),   -- 1. INV VALUE
    freight               NUMERIC(16,2),   -- 2. FREIGHT
    insurance             NUMERIC(16,4),   -- 3. INSURANCE   (e.g. 0.046 = .046%)
    insurance_unit        VARCHAR(10)      -- 'PERCENT' when printed with a % sign, 'AMOUNT' when a flat value
                          CHECK (insurance_unit IN ('PERCENT','AMOUNT')),
    hss_flag              VARCHAR(5),      -- 4. HSS
    loading                NUMERIC(16,2),   -- 5. LOADING
    commission             NUMERIC(16,2),   -- 6. COMMN
    pay_terms              VARCHAR(20),     -- 7. PAY TERMS   (e.g. FC)
    valuation_method       VARCHAR(80),     -- 8. VALUATION METHOD
    currency_code           VARCHAR(5),      -- 14. Cur (first value = invoice currency)
    freight_currency_code   VARCHAR(5),      -- 14. Cur (second value, when printed = freight currency)
    related_party_flag      VARCHAR(5),      -- 9. RELTD
    svb_ch                   VARCHAR(20),     -- 10. SVB CH
    svb_no                    VARCHAR(30),     -- 11. SVB NO
    svb_date                   DATE,            -- 12. DATE
    loa                          VARCHAR(20),     -- 13. LOA
    incoterm                       VARCHAR(10)      -- 15. Term (FOB, CIF, ...)
);

-- PART II - D. COST & SERVICES
CREATE TABLE boe_invoice_cost_services (
    invoice_id               BIGINT PRIMARY KEY REFERENCES boe_invoice(invoice_id) ON DELETE CASCADE,
    commission_brokerage     NUMERIC(14,2),  -- 1. C&B
    cost_of_container        NUMERIC(14,2),  -- 2. CoC
    cost_of_packing          NUMERIC(14,2),  -- 3. CoP
    handling_charges         NUMERIC(14,2),  -- 4. HND CHG
    goods_and_services_cost  NUMERIC(14,2),  -- 5. G&S
    document_charges         NUMERIC(14,2),  -- 6. DOC CH
    country_of_origin_cert   NUMERIC(14,2),  -- 7. COO
    royalty_licence_fee      NUMERIC(14,2),  -- 8. R&LF
    other_cost               NUMERIC(14,2),  -- 9. OTH COST
    loading_unloading        NUMERIC(14,2),  -- 10. LD/ULD
    warranty_services        NUMERIC(14,2),  -- 11. WS
    other_costs               NUMERIC(14,2),  -- 12. OTC
    misc_charge                NUMERIC(14,2),  -- 13. MISC CHARGE
    assessable_value            NUMERIC(16,2)   -- 14. ASS. VALUE
);

-- PART II - E  +  PART III - A. ITEM  (commercial line + assessment detail, same item)
CREATE TABLE boe_invoice_item (
    item_id              BIGSERIAL PRIMARY KEY,
    invoice_id           BIGINT NOT NULL REFERENCES boe_invoice(invoice_id) ON DELETE CASCADE,
    item_sno             INT NOT NULL,          -- Part II 1.S NO  /  Part III 2.ITEMSN
    cth                  VARCHAR(15),           -- customs tariff head
    ceth                 VARCHAR(15),
    description          VARCHAR(300),
    unit_price           NUMERIC(16,6),
    quantity             NUMERIC(16,6),
    uqc                  VARCHAR(10),           -- unit quantity code, e.g. NOS
    amount               NUMERIC(16,2),
    -- Part III-A assessment detail for the same item:
    upi                  NUMERIC(16,6),         -- 11. UPI (Unit Price Invoiced)
    country_of_origin    VARCHAR(5),            -- 12. COO
    commercial_qty       NUMERIC(16,6),
    commercial_uqc       VARCHAR(10),
    standard_qty         NUMERIC(16,6),
    standard_uqc         VARCHAR(10),
    scheme_code          VARCHAR(10),           -- 17. SCH
    stnd_pr_flag         VARCHAR(10),
    rsp_flag             VARCHAR(10),
    reimp_flag           VARCHAR(5),
    prov_flag            VARCHAR(5),
    end_use              VARCHAR(30),
    prodn_flag           VARCHAR(5),
    cntrl_flag           VARCHAR(5),
    qualfr_flag          VARCHAR(5),
    contnt_flag          VARCHAR(5),
    stmnt_flag           VARCHAR(5),
    sup_docs_flag        VARCHAR(5),
    fs_flag              VARCHAR(3),            -- Food Safety and Standards Authority
    pq_flag              VARCHAR(3),            -- Plant Quarantine
    dc_flag              VARCHAR(3),            -- Central Drugs Standard Control
    wc_flag              VARCHAR(3),            -- WildLife Crime Control Bureau
    aq_flag              VARCHAR(3),            -- Animal Quarantine
    assess_value         NUMERIC(16,2),         -- 29. ASSESS VALUE
    total_duty           NUMERIC(16,2),         -- 30. TOTAL DUTY
    UNIQUE (invoice_id, item_sno)
);


-- =====================================================================
-- PART III: DUTIES — normalized duty-component fact table
-- =====================================================================

-- Lookup of the ~20 duty types printed across Part III sections B / C / C-A
-- (the viewer / extractor writes the code without punctuation: CVD05 here is 'CVD_05'; GCESS = 'G.CESS'; SPEXD = 'SP EXD' ...)
CREATE TABLE ref_duty_type (
    duty_type_code   VARCHAR(15) PRIMARY KEY,
    duty_group       VARCHAR(20) NOT NULL
                      CHECK (duty_group IN ('ITEM_DUTY','OTHER_DUTIES','OTHER_DUTIES_A')),
    display_label    VARCHAR(60) NOT NULL,
    display_order    SMALLINT
);

INSERT INTO ref_duty_type (duty_type_code, duty_group, display_label, display_order) VALUES
    ('BCD',      'ITEM_DUTY',      'Basic Customs Duty',              1),
    ('CVD_05',   'ITEM_DUTY',      'CVD (Sec 05)',                    2),
    ('SWS',      'ITEM_DUTY',      'Social Welfare Surcharge',        3),
    ('SAD',      'ITEM_DUTY',      'Special Additional Duty',         4),
    ('IGST',     'ITEM_DUTY',      'Integrated GST',                  5),
    ('GCESS',    'ITEM_DUTY',      'GST Cess',                        6),
    ('ADD',      'ITEM_DUTY',      'Anti-Dumping Duty',               7),
    ('CVD',      'ITEM_DUTY',      'Countervailing Duty',             8),
    ('SG',       'ITEM_DUTY',      'Safeguard Duty',                  9),
    ('SPEXD',    'OTHER_DUTIES',   'Special Excise Duty',             10),
    ('CHCESS',   'OTHER_DUTIES',   'Cess (Chapter-specific)',         11),
    ('TTA',      'OTHER_DUTIES',   'TTA',                             12),
    ('CESS',     'OTHER_DUTIES',   'Cess',                            13),
    ('CAIDC',    'OTHER_DUTIES',   'Agriculture Infra & Dev Cess',    14),
    ('EAIDC',    'OTHER_DUTIES',   'Extra AIDC',                      15),
    ('CUSEDC',   'OTHER_DUTIES',   'Customs Education Cess',          16),
    ('CUSHEC',   'OTHER_DUTIES',   'Customs Higher Education Cess',   17),
    ('NCD',      'OTHER_DUTIES',   'National Calamity Duty',          18),
    ('OTHCUS',   'OTHER_DUTIES_A', 'Other Customs Duty',              19),
    ('OTHCVD',   'OTHER_DUTIES_A', 'Other CVD',                       20),
    ('PETRCUS',  'OTHER_DUTIES_A', 'Petroleum Customs Duty',          21),
    ('INFRACES', 'OTHER_DUTIES_A', 'Infrastructure Cess',             22),
    ('CUSCVD',   'OTHER_DUTIES_A', 'Customs CVD',                     23);

-- PART III - B / C / C-A. ITEM DUTY COMPONENTS (one row per item per duty type)
CREATE TABLE boe_item_duty (
    item_duty_id         BIGSERIAL PRIMARY KEY,
    item_id              BIGINT NOT NULL REFERENCES boe_invoice_item(item_id) ON DELETE CASCADE,
    duty_type_code       VARCHAR(15) NOT NULL REFERENCES ref_duty_type(duty_type_code),
    notification_no      VARCHAR(30),   -- Notn No.
    notification_sno     VARCHAR(15),   -- Notn SNo.
    rate                 NUMERIC(8,3),
    amount               NUMERIC(16,2),
    duty_foregone         NUMERIC(16,2), -- 'Duty Fg' row: an AMOUNT (e.g. 84501.79), not a flag
    UNIQUE (item_id, duty_type_code)
);

-- Section-level rollups printed alongside the B / C tables (10.T.VALUE, 10.AGGR)
CREATE TABLE boe_item_duty_section_total (
    item_id           BIGINT NOT NULL REFERENCES boe_invoice_item(item_id) ON DELETE CASCADE,
    duty_group        VARCHAR(20) NOT NULL CHECK (duty_group IN ('ITEM_DUTY','OTHER_DUTIES')),
    total_value        NUMERIC(16,2),   -- 10.T.VALUE (ITEM_DUTY) or 10.AGGR (OTHER_DUTIES)
    PRIMARY KEY (item_id, duty_group)
);


-- =====================================================================
-- PART IV: ADDITIONAL DETAILS (mostly item-scoped, boe_id/item_id FK)
-- =====================================================================

CREATE TABLE boe_item_svb (                       -- A. SVB DETAILS
    svb_id       BIGSERIAL PRIMARY KEY,
    item_id      BIGINT NOT NULL REFERENCES boe_invoice_item(item_id) ON DELETE CASCADE,
    ref_no       VARCHAR(30),
    ref_date     DATE,
    prt_cd       VARCHAR(10),
    lab          VARCHAR(30),
    p_f_1        VARCHAR(5),
    load_date    DATE,
    p_f_2        VARCHAR(5)
);

CREATE TABLE boe_previous_be (                    -- B. PREVIOUS BEs
    prev_be_id     BIGSERIAL PRIMARY KEY,
    item_id        BIGINT NOT NULL REFERENCES boe_invoice_item(item_id) ON DELETE CASCADE,
    prev_be_no     VARCHAR(20),
    prev_be_date   DATE,
    prt_cd         VARCHAR(10),
    unit_price     NUMERIC(16,6),
    currency_code  VARCHAR(5)
);

CREATE TABLE boe_reimport_after_export (          -- C. RE-IMPORT AFTER EXPORT
    reimport_id   BIGSERIAL PRIMARY KEY,
    item_id       BIGINT NOT NULL REFERENCES boe_invoice_item(item_id) ON DELETE CASCADE,
    notn_no       VARCHAR(30),
    sl_no         VARCHAR(10),
    frt           NUMERIC(14,2),
    ins           NUMERIC(14,2),
    duty          NUMERIC(14,2),
    sb_no         VARCHAR(30),
    sb_date       DATE,
    port_cd       VARCHAR(10),
    sinv          VARCHAR(30),
    sitemn        VARCHAR(10)
);

CREATE TABLE boe_item_manufacturer (              -- D. MANUFACTURER/PRODUCER/GROWER
    manufacturer_id  BIGSERIAL PRIMARY KEY,
    item_id          BIGINT NOT NULL REFERENCES boe_invoice_item(item_id) ON DELETE CASCADE,
    manufacturer_type VARCHAR(30),
    manufact_cd      VARCHAR(20),
    source_country    VARCHAR(60),
    trans_country     VARCHAR(60),
    address           TEXT
);

CREATE TABLE boe_item_accessory (                 -- E. ACCESSORY STATUS
    accessory_id  BIGSERIAL PRIMARY KEY,
    item_id       BIGINT NOT NULL REFERENCES boe_invoice_item(item_id) ON DELETE CASCADE,
    item_details  VARCHAR(300)
);

CREATE TABLE boe_item_licence (                   -- F. LICENCE DETAILS
    licence_id    BIGSERIAL PRIMARY KEY,
    item_id       BIGINT NOT NULL REFERENCES boe_invoice_item(item_id) ON DELETE CASCADE,
    lic_sl_no     VARCHAR(10),
    lic_no        VARCHAR(30),
    lic_date      DATE,
    scheme_code   VARCHAR(10),
    port          VARCHAR(30),
    debit_value   NUMERIC(14,2),
    qty           NUMERIC(16,6),
    uqc           VARCHAR(10),
    debit_duty    NUMERIC(14,2)
);

CREATE TABLE boe_item_scheme_notification (       -- G. SCHEME NOTIFICATION / DUTY FOREGONE
    scheme_id       BIGSERIAL PRIMARY KEY,
    item_id         BIGINT NOT NULL REFERENCES boe_invoice_item(item_id) ON DELETE CASCADE,
    exemption_ref   VARCHAR(30),
    scheme_notn     VARCHAR(30),
    scheme_sno      VARCHAR(10),
    bcd_rate        NUMERIC(8,3),
    cvd_rate        NUMERIC(8,3),
    bcd_amt_fg      NUMERIC(14,2),
    oth_amt_fg      NUMERIC(14,2)
);

CREATE TABLE boe_certificate (                    -- H. CERTIFICATE DETAILS
    certificate_id       BIGSERIAL PRIMARY KEY,
    boe_id               BIGINT NOT NULL REFERENCES boe(boe_id) ON DELETE CASCADE,
    item_id               BIGINT REFERENCES boe_invoice_item(item_id) ON DELETE CASCADE,
    certificate_number    VARCHAR(30),
    certificate_date      DATE,
    certificate_type      VARCHAR(30)
);

CREATE TABLE boe_hss_detail (                     -- I. HSS DETAILS
    boe_id        BIGINT PRIMARY KEY REFERENCES boe(boe_id) ON DELETE CASCADE,
    prc_level     VARCHAR(20),
    iec           VARCHAR(30),
    branch_sl_no  VARCHAR(10)
);

CREATE TABLE boe_item_sw_declaration (            -- J. SINGLE WINDOW DECLARATION
    sw_declaration_id  BIGSERIAL PRIMARY KEY,
    item_id            BIGINT NOT NULL REFERENCES boe_invoice_item(item_id) ON DELETE CASCADE,
    info_type          VARCHAR(10),    -- e.g. CHR
    qualifier          VARCHAR(100),
    info_code          VARCHAR(20),    -- e.g. SQC
    info_text          VARCHAR(200),
    info_measure       NUMERIC(12,4),
    uqc                VARCHAR(10)
);

CREATE TABLE boe_item_sw_constituent (            -- K. SW DECLARATION - CONSTITUENTS
    constituent_id  BIGSERIAL PRIMARY KEY,
    item_id         BIGINT NOT NULL REFERENCES boe_invoice_item(item_id) ON DELETE CASCADE,
    c_sno           INT,
    name            VARCHAR(150),
    code            VARCHAR(20),
    percentage      NUMERIC(6,3),
    yield_pct       NUMERIC(6,3),
    ingredient      VARCHAR(150)
);

CREATE TABLE boe_item_sw_control (                -- L. SW DECLARATION - CONTROL
    control_id     BIGSERIAL PRIMARY KEY,
    item_id        BIGINT NOT NULL REFERENCES boe_invoice_item(item_id) ON DELETE CASCADE,
    control_type   VARCHAR(60),
    location       VARCHAR(100),
    start_date     DATE,
    end_date       DATE,
    result_code    VARCHAR(20),
    result_text    VARCHAR(200)
);

CREATE TABLE boe_supporting_document (            -- M. SUPPORTING DOCUMENTS
    doc_id         BIGSERIAL PRIMARY KEY,
    boe_id         BIGINT NOT NULL REFERENCES boe(boe_id) ON DELETE CASCADE,
    invoice_id     BIGINT REFERENCES boe_invoice(invoice_id) ON DELETE CASCADE,    -- set when source invsno > 0
    item_id        BIGINT REFERENCES boe_invoice_item(item_id) ON DELETE CASCADE,  -- set when source itmsno > 0
    doc_type_code  VARCHAR(10),     -- 3. TYP, e.g. PNM, CHR, SIU, SQC
    icegate_id     VARCHAR(30),     -- 4. ICEGATE ID, e.g. NEINDELD, MARUTISUZUKI
    irn            VARCHAR(30),     -- 5. IRN
    doc_code       VARCHAR(10),     -- 6. DOC CODE, e.g. 70300, 33100, 78000, 71000, 10100
    issue_place    VARCHAR(60),
    issue_date     DATE,
    expiry_date    DATE
);
-- Level is derived from which FKs are populated:
--   invoice_id NULL, item_id NULL  -> BOE-level      (source invsno=0, itmsno=0)
--   invoice_id set,  item_id NULL  -> invoice-level  (source invsno=N, itmsno=0)  -- e.g. per-invoice packing list
--   invoice_id set,  item_id set   -> item-level      (source invsno=N, itmsno=M)


-- =====================================================================
-- PART V: OTHER COMPLIANCES
-- =====================================================================

CREATE TABLE boe_compliance (
    boe_id                     BIGINT PRIMARY KEY REFERENCES boe(boe_id) ON DELETE CASCADE,
    examination_order_rms      TEXT,
    examination_order          TEXT,
    examination_instructions   TEXT,
    compulsory_compliance      TEXT,
    ac_remarks                 TEXT,
    examination_report         TEXT,
    superintendent_comments    TEXT,
    ooc_no                     VARCHAR(30),
    ooc_date                   DATE
);

CREATE TABLE boe_pga_examination (                -- B1. PGA EXAMINATION INSTRUCTIONS
    pga_id       BIGSERIAL PRIMARY KEY,
    boe_id       BIGINT NOT NULL REFERENCES boe(boe_id) ON DELETE CASCADE,
    invoice_sno  INT,
    item_sno     INT,
    agency       VARCHAR(60),
    status       VARCHAR(60)
);


-- =====================================================================
-- PART VI: DECLARATION
-- =====================================================================

CREATE TABLE boe_declaration_statement (
    declaration_id    BIGSERIAL PRIMARY KEY,
    boe_id            BIGINT NOT NULL REFERENCES boe(boe_id) ON DELETE CASCADE,
    declaration_for   VARCHAR(20),    -- e.g. '0/0', '1/0'
    declaration_text  TEXT
);

CREATE TABLE boe_signatory (
    boe_id                BIGINT PRIMARY KEY REFERENCES boe(boe_id) ON DELETE CASCADE,
    signed_date           DATE,
    signed_place          VARCHAR(60),
    authorised_signatory  VARCHAR(200),
    cha_name              VARCHAR(200)
);


-- =====================================================================
-- FIELD CATALOG — metadata-driven drill-down navigation
-- =====================================================================
-- Maps every printed Part/Section/Field label to the table+column that
-- actually stores it. The frontend reads this to build the navigation
-- tree (Part -> Section -> Field) instead of hardcoding it, and to
-- resolve a click ("Part II > C. Valuation > 3. Insurance") into the
-- table.column to query.

CREATE TABLE boe_field_catalog (
    catalog_id      SERIAL PRIMARY KEY,
    part_no         VARCHAR(10)  NOT NULL,   -- 'I','II','III','IV','V','VI'
    part_label      VARCHAR(150),
    section_code    VARCHAR(5),              -- 'A','B','C',...
    section_label   VARCHAR(150),
    field_no        VARCHAR(5),              -- '1','2','3',...
    field_label     VARCHAR(150),
    target_table    VARCHAR(100) NOT NULL,
    target_column   VARCHAR(100) NOT NULL,
    data_type       VARCHAR(30),
    sort_order      INT,
    UNIQUE (part_no, section_code, field_no)
);

-- Seed rows for a few fields, including the exact example from the doc:
INSERT INTO boe_field_catalog
    (part_no, part_label, section_code, section_label, field_no, field_label, target_table, target_column, data_type, sort_order)
VALUES
    ('II','INVOICE & VALUATION DETAILS','C','VALUATION','1','INV VALUE',        'boe_invoice_valuation','invoice_value',     'numeric', 1),
    ('II','INVOICE & VALUATION DETAILS','C','VALUATION','2','FREIGHT',          'boe_invoice_valuation','freight',           'numeric', 2),
    ('II','INVOICE & VALUATION DETAILS','C','VALUATION','3','INSURANCE',        'boe_invoice_valuation','insurance',         'numeric', 3),
    ('II','INVOICE & VALUATION DETAILS','C','VALUATION','8','VALUATION METHOD', 'boe_invoice_valuation','valuation_method',  'text',    8),
    ('I', 'BOE SUMMARY',                'C','DUTY SUMMARY','14','TOTAL DUTY',   'boe_duty_summary',      'total_duty',        'numeric', 14);


-- =====================================================================
-- INDEXES for drill-down / rollup performance
-- =====================================================================

CREATE INDEX idx_boe_invoice_boe_id            ON boe_invoice(boe_id);
CREATE INDEX idx_boe_invoice_item_invoice_id   ON boe_invoice_item(invoice_id);
CREATE INDEX idx_boe_item_duty_item_id         ON boe_item_duty(item_id);
CREATE INDEX idx_boe_item_duty_type            ON boe_item_duty(duty_type_code);
CREATE INDEX idx_boe_invoice_party_invoice_id  ON boe_invoice_party(invoice_id);
CREATE INDEX idx_boe_sw_declaration_item_id    ON boe_item_sw_declaration(item_id);
CREATE INDEX idx_boe_supporting_doc_boe_id     ON boe_supporting_document(boe_id);
CREATE INDEX idx_boe_supporting_doc_invoice_id ON boe_supporting_document(invoice_id);
CREATE INDEX idx_boe_field_catalog_lookup      ON boe_field_catalog(part_no, section_code, field_no);


-- =====================================================================
-- EXAMPLE DRILL-DOWN QUERIES
-- =====================================================================

-- 1) The exact example from the request: Part II > C.Valuation > 3.Insurance
--    for invoice BYA48607 on BE 7526371.
-- SELECT v.insurance
-- FROM boe b
-- JOIN boe_invoice i     ON i.boe_id = b.boe_id
-- JOIN boe_invoice_valuation v ON v.invoice_id = i.invoice_id
-- WHERE b.be_no = '7526371' AND i.invoice_no = 'BYA48607';

-- 2) Same thing, driven generically off the catalog (what the UI actually calls):
-- SELECT target_table, target_column FROM boe_field_catalog
-- WHERE part_no = 'II' AND section_code = 'C' AND field_no = '3';
-- -> then SELECT <target_column> FROM <target_table> WHERE invoice_id = :selected_invoice_id;

-- 3) Full duty breakdown for one item (all ~20 duty types as rows):
-- SELECT rdt.display_label, d.rate, d.amount, d.notification_no
-- FROM boe_item_duty d
-- JOIN ref_duty_type rdt ON rdt.duty_type_code = d.duty_type_code
-- WHERE d.item_id = :item_id
-- ORDER BY rdt.display_order;

-- 4) Roll every item's IGST back up to the BOE, cross-checked against Part I-C total:
-- SELECT b.be_no, SUM(d.amount) AS igst_from_items, ds.igst AS igst_declared
-- FROM boe b
-- JOIN boe_invoice i ON i.boe_id = b.boe_id
-- JOIN boe_invoice_item ii ON ii.invoice_id = i.invoice_id
-- JOIN boe_item_duty d ON d.item_id = ii.item_id AND d.duty_type_code = 'IGST'
-- JOIN boe_duty_summary ds ON ds.boe_id = b.boe_id
-- WHERE b.boe_id = :boe_id
-- GROUP BY b.be_no, ds.igst;
