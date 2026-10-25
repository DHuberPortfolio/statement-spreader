# Independent DQ test set 1

A hand-labelled test set for the data-quality gate, written without reading the gate's code, its tests or its
reports. The only inputs were `config/finops/dq/vendors.yaml`, `config/finops/dq/purchase_orders.yaml`, the
downstream examples in `eval/invoice/dev/master/`, and the written policy in the request.

Every name, tax id, bank account and routing number is invented. Routing numbers were generated to pass (or, where
a row tests it, to fail) the ABA checksum. Tax ids and bank accounts are unique across all three vendor files except
where a row deliberately shares one.

## Files

| File | Rows | What it is |
|---|---|---|
| `portal.csv` | 59 | Procurement-portal vendor export (portal column names, UTF-8, no BOM, CRLF) |
| `erp.xlsx` | 46 | Legacy-ERP vendor export, sheet `VENDOR_EXPORT`. Text is stored as text cells; number and date cells appear only where a row tests Excel damage |
| `previous.csv` | 50 | Last accepted vendor snapshot, canonical columns in `fields` order, canonical values (EIN as NN-NNNNNNN, tax rate as a fraction, ISO dates, routing numbers with their leading zeros) |
| `po.csv` | 85 | ERP purchase-order lines (ERP PO column names) |
| `truth.json` | 190 | One label per data row of the three input files (`row` is the Excel row, header = 1) |
| `build_set.py` | | The generator that wrote all of the above, with each row's label next to the row |

### Expected decisions

| File | accepted | review | rejected | duplicate |
|---|---|---|---|---|
| portal.csv | 25 | 15 | 18 | 1 |
| erp.xlsx | 22 | 10 | 13 | 1 |
| po.csv | 51 | 10 | 23 | 1 |

## How it was built

1. Each vendor was first written as a canonical record. The script then renders it into the source's raw form
   (portal: status codes A/I/B, country names such as "USA" or "United Kingdom", tax as a percent, dates
   `%m/%d/%Y`; ERP: ACTIVE/INACTIVE/HOLD, NETnn terms, `|` between aliases, ISO dates) and applies the row's
   deliberate mess on top.
2. The snapshot `previous.csv` is built from the same canonical records, with a deliberate difference only where a
   row tests change control (bank account, routing, tax id changed or removed) or tests that a non-controlled
   change is ignored (rename, status change). New vendors and most rows built to fail are left out of it.
3. `po.csv` references vendors by their expected outcome. **The vendor reference is the union of the vendor_ids
   labelled `accepted` in `portal.csv` and `erp.xlsx`** (the first row of each exact-duplicate pair counts; held
   `review` vendors and rejected vendors are absent). Inactive and blocked vendors are in it on purpose.
4. Sanity checks in the script: every routing number in the snapshot passes the checksum, every "bad checksum" row
   fails it, PO lines labelled for an existing vendor point at an accepted vendor (and the reverse), no item code
   other than HYD-220 has 4+ lines with a price spread over 8x, and same-country name pairs above 0.8 similarity
   (difflib) are only the designed ones.
5. Portal and ERP vendor ids do not overlap (V1xxx and V2xxx), so the set works whether the gate runs the two
   files separately or together.

## Rows where I was unsure how the policy applies

These are the judgment calls. Each one is labelled the way I read the policy, with the alternative noted.

**portal.csv**
- Row 21 (`tax_rate_fraction_in_percent_column`, V1020): "0.0825" in the percent column becomes 0.000825, which is
  inside 0..0.25. Labelled **accepted** because nothing in the config can tell; a human would call it an error.
- Row 31 (`bank_scientific_notation`, V1030): "4.52382E+11". Labelled **rejected** (not a readable account).
  A literal reading of the config would let it through: `digits_only` turns it into 45238211, which matches
  `\d{6,17}`. Even then, change control should hold it for **review** because the snapshot has the real account.
- Row 33 (`date_excel_serial_text`): "45124" as text in a CSV. Labelled **rejected**; I did not expect the gate to
  convert serials in a CSV.
- Row 41 (`iban_in_account`, DE): an IBAN in the account column leaves 20 digits after `digits_only`, so the
  pattern fails and it is **rejected**. A German vendor quoting an IBAN is normal, but the config has nowhere
  to put one.
- Rows 47/48 and 49/50 (same tax id, shared bank): I labelled **both** rows of each pair review. A gate that flags
  only the second one would miss half.
- Rows 51/52 (Thistledown Textiles Ltd vs Thistledown Textile Ltd, GB, one tax id empty): both **review**. The
  difflib ratio is 0.979. I don't know which fuzzy scorer the gate uses, but any common one should be above 92.
- Rows 19/20 (Meridian Valve Co vs Meridian Valve Corp): **accepted** whatever the score, because both EINs are
  filled and different.
- Rows 57/58 (exact duplicate): row 57 is **accepted**. A gate that runs same_tax_id/shared_bank before removing the
  duplicate would wrongly hold row 57 against its own copy.
- Row 59 (`bank_removed_vs_snapshot`): the snapshot has an account and routing, the export has neither. Labelled
  **review** (a removal is a change). One could argue that only a new value counts as a change.
- Rows 6 and 7 / ERP rows 3 and 4: UK VAT and German ids have 9 digits, so a too-eager `ein` normaliser could
  turn "GB 274 5519 08" into 27-4551908. That does not change their labels (no rule checks non-US tax ids), but
  for that reason I left those vendors **out of previous.csv**: their canonical tax id is not well defined.
- Row 5 (`ca_no_tax_no_bank`): a Canadian vendor in the portal takes the source default currency USD. Labelled
  accepted; I assumed the default is not checked against the country.

**erp.xlsx**
- Row 5 (`bank_number_cell_intact`): a 12-digit account as a number cell, exactly stored. Labelled **accepted**. A
  gate that reads it as "738190245561.0" and then applies `digits_only` gets 7381902455610, a different account.
- Row 6 (`routing_number_cell_no_leading_zero`): a routing number as a number cell that never had a leading zero.
  Labelled **accepted**.
- Row 7 (`created_true_date_cell`): CREATED is a real date cell, not text in a listed format. Labelled
  **accepted** (the value is a date). A gate that only parses strings would reject it.
- Row 23 (`routing_lost_leading_zero`): number cell 67994900, from 067994900. Labelled **rejected** (8 digits, not
  an ABA). A gate could reasonably left-pad to 9 digits for xlsx number cells, which would then pass the checksum
  and match the snapshot. If it did that, the right answer would be **accepted**.
- Row 25 (`date_serial_number_cell`): CREATED is a plain number 45123 with no date format. Labelled **rejected**.
  A gate that treats numbers in a date column as Excel serials would accept it (2023-07-16).
- Row 15 (`ccy_blank`): ERP vendor with no CCY. The ERP source has no default, and currency is optional. Labelled
  **accepted**.
- Row 34 (`bank_scientific_text`): like portal row 31, but the vendor is not in the snapshot, so nothing but a
  scientific-notation check can catch it. Labelled **rejected**.
- Row 44 (`erp_exact_dup_second`): STAT "active" (lowercase, not a value_maps key) and "NET 30". I assumed the
  value_maps lookup is case-insensitive and that an already-canonical status passes, which makes the row identical.
  If "active" is not accepted, this row becomes rejected instead of duplicate.
- Ambiguous dates: the ERP formats (`%Y-%m-%d`, `%d.%m.%Y`) can never both match one string, and the portal has one
  format. So **no row can be "review: ambiguous date"** with this config. Row 19 ("05.04.2023") is the closest:
  it only fits `%d.%m.%Y`, so it is accepted as 5 April.

**po.csv**
- Row 29 (PO_STATUS "open") and row 28 ("o"): labelled **accepted**, assuming the canonical value passes and the
  O/C/X map is case-insensitive.
- Rows 5/6: CCY "usd" vs "USD" on the same PO. **Accepted**: group consistency should compare normalised values.
- Row 35 (`price_extra_zero`, HYD-220 at 4125.00 vs about 410 on 5 other lines): **review**. A gate that compares
  against a mean that includes the outlier sees only about 4x (below factor 8) and would miss it. The median and the
  others-only mean both give about 10x.
- Rows 41-43 (VLV-3: 35, 36, 350): only 3 lines in total, below `min_group` 4, so row 43 is **accepted** although it
  is 10x. Whether `min_group` counts the line itself or only the others, it is short either way.
- Row 44 (QTY "1,000"): labelled **rejected** (a thousands separator is not a plain decimal; "1,5" would be
  ambiguous). A US-locale gate might read it as 1000; then it would be accepted.
- Rows 54/55 (GR_REQUIRED "N", "TRUE") and row 5/6 ("Y"): labelled **accepted** as standard boolean spellings. The
  config doesn't list bool spellings; the downstream file uses yes/no.
- Row 13: unit price 0.00, allowed (min 0). Row 51: PO number " po-6037 " trims and upper-cases, so **accepted**.
- Rows 17, 72 and 73: vendors that were held or rejected are **rejected** here, as instructed ("not in the accepted
  vendor file"). In practice the PO would just wait for the vendor to be fixed.
- Rows 14-16, 70, 71: inactive or blocked vendors that are in the reference → **review** on every line.
- Rows 20-26: group-consistency failures reject every line of the PO, including lines that are fine on their own.
  The mixed-status PO (rows 25/26) uses O vs C. The mixed-currency PO (rows 23/24) uses USD vs CAD for a Canadian
  vendor.

## Not covered (deliberately)

- Lowercase `net 45` in ERP terms (the `^NET\s*` pattern's case-sensitivity is not specified).
- "8.25%" with a percent sign in the portal tax column, and "Active" (title case) in the portal status column: I
  could not decide these from the policy.
- Cross-file duplicates between portal and ERP: avoided so that the labels do not depend on whether the files are
  gated together.
