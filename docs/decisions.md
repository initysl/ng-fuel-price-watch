# Decisions log

Each decision records *Decision / Alternatives / Why*, and points back to the evidence in the
findings section that comes first. The exploration code is in
[`notebooks/01_explore_source.ipynb`](../notebooks/01_explore_source.ipynb).

---

## Step 1: Source exploration (Nov 2026)

### Scope
- **All 19 releases** in the NBS catalogue (`catalog/157`, *Related materials*):
  Nov 2024 – May 2026, one xlsx and one PDF each, stored as `landing/raw/pms/<YYYY-MM>/`.
- The catalogue has nothing before Nov 2024. Each file's year-ago column extends the series
  back to **Nov 2023**: **31 consecutive months** and 2,109 state-price observations across vintages.

### Release packaging

| Releases | Packaging on the catalogue |
|---|---|
| Nov 2024 – Jun 2025 | Separate `.pdf` and `.xlsx` downloads |
| Jul 2025 – May 2026 | One `.zip` per release (xlsx + pdf inside) |
| Aug + Sep 2025 | **One combined zip** containing both months' files |

File names follow no single convention (`PMS_`, `Fuel_`, `PMS Report`, upper/title case,
stray spaces). The Jan 2026 xlsx is named **`PMS_JANUARY_2025.xlsx`**, with the wrong year.

### Release timing (PDF creation date, a proxy for publication)

| Report | PDF created | Report | PDF created |
|---|---|---|---|
| Nov 2024 | 2025-01-16 | Aug 2025 | **2026-02-25** |
| Dec 2024 | 2025-01-16 | Sep 2025 | **2026-02-25** |
| Jan 2025 | 2025-03-25 | Oct 2025 | 2025-11-27 |
| Feb 2025 | 2025-03-25 | Nov 2025 | 2025-12-22 |
| Mar 2025 | 2025-04-23 | Dec 2025 | 2026-02-01 |
| Apr 2025 | 2025-05-21 | Jan 2026 | 2026-02-25 |
| May 2025 | 2025-06-30 | Feb 2026 | 2026-03-25 |
| Jun 2025 | 2025-07-31 | Mar 2026 | 2026-04-27 |
| Jul 2025 | 2025-08-20 | Apr 2026 | 2026-05-26 |
|  |  | May 2026 | 2026-06-24 |

- The usual lag is about 3–5 weeks. Releases sometimes come **in pairs** (Nov+Dec 2024, Jan+Feb 2025).
- **Aug and Sep 2025 were released about 6 months late and out of order**, after Oct 2025 – Jan 2026.
- The cover page always says "Report Date: <following month>".

### xlsx layout: same blocks, moving positions

Every file has one visible sheet with these blocks:
**[title] → [narrative] → header (`State`, three month columns) → 37 states (alphabetical)
→ `AVERAGE` → `Year on Year` → `Month on Month`**, plus a **zone block** (6 zones, current
month only) and a **top/bottom-3 block**.

| Feature | Variation observed |
|---|---|
| Header row | row **1** (Dec 24 – Jul 25), **2** (Nov 24, Aug–Sep 25, Jan–Feb 26, Apr 26), **3** (May 26), **15** (Oct–Dec 25, Mar 26) |
| Month headers (B:D) | Always real Excel dates (`mmm-yy`), always `(M-12, M-1, M)` |
| Title cell (A1) | **Missing** in Nov 24 – Jul 25. **Wrong month** in Oct 25 ("AUGUST 2025") and Jan 26 ("JANUARY 2025") |
| Narrative (A2:H14) | Only in Oct–Dec 25 and Mar 26 |
| Sheet name | `November 2024`, `Fuel March 2025`, `PMS AUGUST 2025`, `PMS_OCT_2025`, **`Sheet1`** (Jan 26), … |
| Zone block | Columns F:G next to the table, except **Jan 26: below the table in column A** (rows 44–50) |
| Formulas | Dec 24, Jul 25, Nov 25, Mar 26 and Apr 26 link to an external workbook (`=[1]Calculations!B2`, linking to `/Users/…/PMS_Fuel WATCH SERIES.xlsx`). Cached values are present. Oct 25 YoY/MoM are live formulas |
| Helper cells | Dec 24 and Jul 25 have `MAX`/`MIN` formulas in I:J |
| Prices | Full float precision (`1653.9100201599535`), displayed with format `0.00` |

#### Incident: a raw file was modified locally after download
During exploration the local Nov 2024 xlsx turned out to differ from what was downloaded
(9,608 bytes / `d0983d86` instead of 15,219 bytes / `c6ac797a`; edited at 12:37 on 2026-11-21).
In the edited copy, **column A had shifted up one row**, so every state label sat next to the
previous state's numbers. A second `AVERAGE` row appeared and the national figure was stored as text.
The **NBS original is clean**, and it was restored from a fresh download (hash re-verified).

Lessons that feed the design:
- **The national-mean check cannot catch label misalignment**, because a mean ignores labels.
  The edited file passed it.
- The **cross-report check** caught it: Nov-24 values against the Nov-24 column of the Dec 2024
  report matched **0/36** as labelled. The zone check also catches it.
- Raw files must be verified against the hash recorded at download before every (re)processing (D3).

### State names

| Raw label | Files | Maps to |
|---|---|---|
| `Abuja` | all 19 | FCT (`NG-FC`) |
| `Nassarawa` | 9 xlsx (Nov 24 – Jul 25) | `NG-NA` |
| `Nasarawa` | 10 xlsx (Aug 25 onwards) **and every PDF**, including the PDFs of the Nassarawa xlsx releases | `NG-NA` |

All other 35 labels match the canonical names exactly. No stray whitespace, no `State` suffix.

### Cross-checks across all 19 files

| Check | Result |
|---|---|
| 37 states in every (vintage, month) | Yes |
| `AVERAGE` = unweighted mean of the 37 states | **57/57** vintage-months exact (difference ≤ 5e-12) |
| Published zone = mean of its states under `dim_state` zones | **113/114** exact. **Jan 2025 North Central** is published as 1,307.22 but the states average 1,287.90; 1,307.22 is the mean **without Kwara**, an NBS arithmetic error |
| Each report's M-1 column = the previous report's M column | **18/18** consecutive pairs, 37/37 states each |
| Revisions: same (state, month) in later reports | **0 changes in 962 overlaps** (666 previous-month, 296 year-ago) |
| National figure restated between reports | Never |
| Mean of **2-dp-rounded** states = published 2-dp national | **2/57 miss by ₦0.01** (Apr-24 in Apr-25 report, Aug-24 in Aug-25 report) |
| Blueprint headline figures (§21) | All match |

The methodology (PDF p.3) says *state* estimates are weighted by household fuel spending.
The *national* and *zone* averages, however, are plain unweighted means of states. README limitation.

### Rounding
- NBS's displayed 2-dp figures follow Excel: round to **15 significant digits**, then half-up.
  Example: Rivers Sep-25 is stored as `980.3549999999999`, Excel shows `980.36`, and naive
  Python gives `980.35`.
- Postgres converts `float8 → numeric` at 15 significant digits, so a `numeric` column followed by
  `round(x, 2)` reproduces NBS exactly.

### Data quality

| Period | Whole-naira prices (of 37) | Max / min state ratio |
|---|---|---|
| Nov 2023 – Oct 2024 (year-ago columns only) | 4–11 | 1.12–1.47 |
| **Jan – Apr 2025** | **5–17** | **1.64–1.81** (Jigawa ₦1,730 in Feb 25) |
| May 2025 onwards | 0–6, mostly 0–2 since Aug 25 | 1.11–1.25 |

- Early 2025 is unusually dispersed and coarse. It was **published that way and never revised**.
- Only one month-on-month move above 40%: **Kaduna, Jan 2025, +41.1%** (₦1,161 → ₦1,638).
- National series range: ₦648.93 (Nov 2023) to ₦1,596.25 (May 2026). The biggest national moves
  are **May 2025 −17.1%**, Mar 2026 +22.6% and Apr 2026 +19.0%.

### PDFs

- 9 pages, built in Microsoft Publisher. Pages 5–7 are image-only charts. The **appendix on p.8** is
  one 45-row table (header + 6 zone rows + 37 states + `Grand Total`). The word "APPENDIX" also
  appears on the contents page (p.2).
- The values agree with the xlsx (rounded the Excel way) **where the extraction works**, but:
  - **Nov 2024 PDF appendix is stale.** It shows Oct-23 / Sep-24 / Oct-24, the previous report's table.
  - **Aug 2025:** wrapped cells merge rows (`'8\n1007.01'`), giving 35 states and no Grand Total.
  - **Apr 2026:** an extra empty column shifts every value one column right.

---

## Decisions

### D1. Find the header by its three date cells, then require `State` in column A
- **Alternatives:** a fixed `header=` row; searching only for `State` in column A.
- **Why:** the header row has been 1, 2, 3 and 15. The constant is **B:D holding three Excel
  dates**. Column A of that row must then read `State` (stripped, case-insensitive), followed by
  exactly 37 labels and a single `AVERAGE` row. Anything else raises `LayoutChangedError`.

### D2. The report month (= `report_vintage`) is the latest month header, and nothing else
- **Alternatives:** file name, sheet name, title cell.
- **Why:** a file name had the wrong year (Jan 26), titles are missing in 9 files and wrong in 2,
  and sheet names vary freely. Additional ERROR: the headers must be exactly `(M-12, M-1, M)`.
  A title that disagrees with the header is a WARN.

### D3. Verify raw files against their download hash before every (re)processing
- **Alternatives:** trust whatever is in `landing/`; hash only at download time.
- **Why:** a raw file was modified locally during exploration (see *Incident*). The edited file
  still looked plausible and passed the national-mean check. The SHA-256 recorded in
  `raw.ingestion_log` at download is re-checked whenever a file is extracted or backfilled. A
  mismatch is an ERROR (`RawFileModifiedError`); the fix is to download again, never to edit.
  Make raw files read-only (`chmod 444`) once logged.

### D4. Store prices at full precision: `avg_price_ngn numeric(14,6)`
- **Alternatives:** `numeric(10,2)` (blueprint).
- **Why:** 2-dp storage misses 2 of 57 published national figures. Full precision plus
  Postgres `round(…, 2)` reproduces all 57, including Excel's 15-digit rounding (see *Rounding*).

### D5. xlsx only in v1; PDFs archived but not parsed
- **Alternatives:** a PDF extractor as a fallback (blueprint Step 4).
- **Why:** every release has an xlsx. The PDF appendix was stale in one release and broke table
  extraction in two more, so it is a worse source, not a fallback. Revisit only if a release is
  ever PDF-only.

### D6. National check is a strict ERROR; zones are computed, and published zones are a WARN
- **Alternatives:** the blueprint's 3% WARN on the national cross-check; loading NBS zone figures as truth.
- **Why:** the national figure matches the mean of states in 57/57 cases, so any gap means we
  parsed wrong: **ERROR at ₦0.01**. Zones match in 113/114, and the miss is an NBS error, so:
  - `mart.zone_monthly` **computes** zones from states for every month (the published ones exist
    for the current month only anyway);
  - the published zone figures are loaded into `fact_fuel_price_aggregate` and compared. One zone
    off is a **WARN**. **Two or more zones off is an ERROR**, because that pattern means state labels
    are misaligned (D3).

### D7. Keep vintages, and make the cross-vintage check strict
- **Alternatives:** overwrite on reload; drop vintages since nothing was ever revised.
- **Why:** NBS has restated **nothing** in 962 overlaps, which makes a change a strong signal.
  Any changed value is a **WARN** (blueprint rule 9, with the threshold lowered from 10% to ₦0.01).
  **More than 3 states changed in one month is an ERROR**, because that pattern means misalignment:
  the edited Nov 2024 copy changed 36/36. Vintages still cost nothing and keep the audit trail if
  NBS ever does revise.

### D8. Require cached values for formula cells
- **Why:** 5 of 19 files are formula-driven, linking to a workbook on an NBS laptop. If a state or
  price cell reads as `None`, or as a string starting with `=`, raise `LayoutChangedError`.

### D9. Expect numeric cells, but parse defensively
- **Why:** every price cell in all 19 original files is a real number. Transform still runs
  `pd.to_numeric` and reports anything that fails, as the blueprint requires, because a re-saved or
  hand-edited file can turn numbers into text (the edited Nov 2024 copy did).

### D10. Aliases: `abuja → NG-FC`, `nassarawa → NG-NA` (both observed)
- **Why:** both appear in real files. Keep the blueprint's other starter aliases. Add new ones only
  when a file shows them.

### D11. Ignore derived and decorative blocks
- **Why:** title, narrative, YoY/MoM rows, top/bottom-3, `MAX`/`MIN` helpers are all
  derivable or noise. The top/bottom-3 block becomes a WARN-level cross-check
  of our ranking. The zone block must be found **anywhere on the sheet** by zone name (it moved
  to column A in Jan 2026).

### D12. Load the year-ago columns too: history starts Nov 2023
- **Why:** Nov 2023 – Oct 2024 exist only as year-ago columns (one vintage each). They are
  genuine NBS figures, giving 31 continuous months, so YoY works from Nov 2024.

### D13. Acquisition: hash the files inside zips; never assume months arrive in order
- **Why:** since Jul 2025 releases come as zips, one zip can contain two months (Aug+Sep 2025),
  and releases come out of order. Acquire unzips each release (safely, rejecting unsafe paths) and
  hashes each **inner** file. `report_vintage` comes from content (D2). The freshness rule
  (blueprint rule 10, 45 days) stays a WARN; it would have fired for Aug/Sep 2025.

### D14. Thresholds confirmed
- Price band ₦300 – ₦5,000: observed ₦602.55 (Apr 2024) – ₦1,730 (Feb 2025). OK.
- MoM > 40% WARN: fires once in 31 months (Kaduna Jan 2025). OK.

---

## Step 2: Database schema and seeds

`sql/001_schemas.sql` → `002_raw_tables.sql` → `003_core_tables.sql`, seeds in `seeds/`, run with
`python -m pipeline.setup`.

### D15. `core` is a star schema with two fact tables (a fact constellation)
- **Facts:** `fact_fuel_price_state` (grain: product × state × month × vintage) and
  `fact_fuel_price_aggregate` (product × national/zone area × month × vintage).
  **Dimensions:** `dim_state`, `dim_product`.
- **Alternatives:** one fact table with a level column; a snowflaked `dim_zone`; a `dim_date`.
- **Why:** separate grains can never be summed together by accident. Zone is a plain attribute of
  `dim_state` (6 values, no attributes of its own), so a `dim_zone` would add a join and nothing
  else. With monthly grain, a first-of-month `date` column is enough; add `dim_month` only if
  fiscal periods are ever needed. `state_alias` is a transform-time lookup, not a dimension, and
  `raw.ingestion_log` is lineage.

### D16. Migration order is raw before core
- **Why:** both fact tables reference `raw.ingestion_log (file_id)`. The blueprint's order
  (core before raw) fails on the foreign key. `raw.ingestion_log` deliberately has **no** foreign
  key into `core`, so the raw layer never depends on the conformed layer.

### D17. `ingestion_log.sha256` is not unique; a partial unique index enforces one success
- **Alternatives:** `sha256 UNIQUE` (blueprint).
- **Why:** with a plain unique constraint, logging a `skipped_duplicate` row violates it, and a
  `failed` file could never be retried. `UNIQUE (sha256) WHERE status = 'success'` allows
  retries and duplicate logging, and still prevents loading the same content twice. `status` also
  includes `running` (Step 7 inserts it first), and a `failed` row must carry an `error_message`.

### D18. Business rules live in constraints, not only in Python
- Prices are `numeric(14,6)` and `> 0` (D4). Both date columns must be first-of-month, and
  `price_month <= report_vintage`. Aggregate rows must be `national/Nigeria` or `zone/<one of 6>`.
  Codes are checked against their patterns (`NG-XX`, `XXX`). Validation in Python (Step 6) gives
  clear messages; the constraints are the last line of defence.

### D19. Seeds are upserted (`ON CONFLICT … DO UPDATE`); removals only warn
- **Alternatives:** `DO NOTHING` (blueprint); truncate and reload.
- **Why:** `DO NOTHING` silently ignores a corrected CSV row, and truncating breaks foreign keys
  from the fact tables. Rows deleted from a CSV are reported as a warning, never deleted, because
  facts may still reference them.

### D20. `CREATE … IF NOT EXISTS` makes setup re-runnable, but it is not a migration tool
- **Why:** an existing table is never altered by re-running `003`. Any change after first deploy
  goes into a **new numbered file** (`004_…`). Alembic is not worth it for 6 tables. Revisit if
  the schema starts changing often.

### D21. DB tests run on a throwaway `<db>_test` database
- **Why:** each test session drops and recreates it. The fixture refuses any database name not
  ending in `_test`. Locally the DB tests skip if Postgres is down; CI sets `REQUIRE_DB=1` so they
  fail instead, and uses a Postgres 16 service container.

Seed notes: `state_alias.csv` = 37 canonical names (normalised) + observed `abuja`, `nassarawa`
+ starter variants (`fct`, `fct abuja`, `akwaibom`, `crossriver`), 43 rows. It is generated
with `pipeline.transform.normalise_state_name`, so seeds and lookups use identical rules. The
LPG unit (`NGN/kg`) is provisional until the Phase 2 reports are inspected.

---

## Open questions
1. Is the Jan 2025 North Central error (Kwara omitted) corrected anywhere by NBS? Not in later reports.
2. Why were Jan–Apr 2025 so dispersed? It's a candidate "finding" for the README. Hypotheses only.
3. Does a stable listing or API exist for the catalogue (for Step 3), or do we scrape
   *Related materials* (resource ids increase with publication order)?
