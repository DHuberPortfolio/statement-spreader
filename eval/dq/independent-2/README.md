# Independent DQ test set 2

A hand-labelled test set for the data-quality gate, written without reading the gate's code, its tests, the other
test set in `eval/dq/` or any `eval/reports/dq-*` report. The only inputs were `config/finops/dq/vendors.yaml`,
`config/finops/dq/purchase_orders.yaml`, the example files in `eval/invoice/dev/master/` and the written gate policy.
Every name, tax id, bank account and routing number is invented. Routing numbers that are meant to be valid pass the
ABA checksum. Those meant to be invalid fail it on purpose.

## Files

| File | Rows | What it is |
|---|---|---|
| `portal.csv` | 60 | Procurement-portal vendor export (portal column names, UTF-8) |
| `erp.xlsx` | 47 | Legacy ERP vendor export (ERP column names, sheet `VENDORS`) |
| `previous.csv` | 50 | Last accepted vendor snapshot, canonical columns in `fields` order |
| `vendors_reference.csv` | 58 | Vendor file the PO check should use: accepted vendors plus held vendors carried forward |
| `po.csv` | 77 | ERP purchase-order lines (ERP PO column names) |
| `truth.json` | 184 | One label per data row of portal.csv, erp.xlsx and po.csv (`row` = Excel row, header = 1) |

Expected decisions:

| File | accepted | review | rejected | duplicate |
|---|---|---|---|---|
| portal.csv | 26 | 15 | 18 | 1 |
| erp.xlsx | 18 | 11 | 17 | 1 |
| po.csv | 42 | 8 | 27 | 0 |

## How it was built

A Python script (kept outside the repo) defines each vendor as a canonical record, which is the value an accepted
row should normalise to. It then renders that record in the source's raw form: portal percent tax, A/I/B status codes,
country names and `%m/%d/%Y` dates; ERP `NETnn` terms, `ACTIVE/INACTIVE/HOLD`, `|` alias separators, and dates as ISO
text, `dd.mm.yyyy` text or real Excel date cells in rotation. One deliberate change per row is applied on top. The
label, the case name and the reason are written next to each row in the script.

- `previous.csv` holds each vendor's earlier version. For change-control cases it holds the old bank, routing or tax id.
- `vendors_reference.csv` is derived from the labels. It holds every accepted row's canonical record, with blocked and
  inactive vendors keeping their status. For a vendor whose rows are all held (review or rejected), it holds the
  `previous.csv` version, but only when the vendor is in the snapshot and no held row of it is blocked or inactive.
- The script also checks itself. Every valid routing number passes the checksum. The only tax-id or bank collisions
  between different vendor ids are the intended ones. The rapidfuzz scores `ratio`, `token_set_ratio`,
  `partial_ratio` and `WRatio` stay below 92 for every unintended same-country name pair (the highest is 86). Every PO
  vendor's expected outcome agrees with the reference file.
- `erp.xlsx` was written with openpyxl. The ROUTING text cells are quote-prefixed, as Excel does for text-forced numbers.

### What it tries that a typical test would not

The set includes the following cases:

- Vendors re-numbered between systems: V1057 in the portal is V2040 in the ERP, with the same EIN and bank.
- A Cyrillic `а` in a Latin name (V1061 copies V1060).
- Zero-width spaces, one in a name and one in an id.
- A tab inside a name.
- Legal suffixes in several languages: S.A. de C.V., GmbH, SARL, Ltd., Inc.
- Two ids with the same bank and different names (V1055/V1056 and V2039/V2041).
- Near-identical names that must NOT be flagged:
  - V1015 and V1016 have different EINs.
  - V1064 is in another country.
- Country and status values that are mapped in one source but not the other: `Germany` and `A` in the ERP.
- An Excel boolean in STAT and a formula cell in TAX_ID.
- Numeric cells for a bank account, an EIN and a routing number. The routing number lost its leading zero.
- A leading apostrophe left in a CSV bank account.
- `6.70913E+11` in a bank account, and `1.23E+05` in an item code.
- An IBAN in the bank account field.
- Tax percentages `7,5` and `30`, and a VAT of `19` in the ERP, where the rate is a fraction.
- Payment terms `NET30` in the portal, plus `NET 45`, `NET 60`, `NET0`, `NET 45 EOM`, `Net 30` and `NET150`.
- Full-width digits.
- Dates: a non-padded `3/7/2024`, ISO in the portal, US in the ERP, `31.04.2024`, and a 2024 leap day.
- Format-only differences against the snapshot that are NOT changes:
  - an EIN written without its hyphen;
  - a bank account written with hyphens.
- Change-control cases:
  - an e-mail change (not controlled);
  - two transposed EIN digits;
  - a removed tax id and a removed bank account;
  - a bank change on a vendor that is now blocked, so it is not carried forward.
- PO lines:
  - lines that are consistent only after normalisation (PO-5016);
  - decimal quantities;
  - `1,200` and `1,234.50`;
  - a negative credit line;
  - a `$` price and the currency `US$`;
  - quantities at, and just below, the minimum;
  - line numbers 0, 999 and 1000;
  - outliers in both directions (decimal slips of 100x);
  - a 5.8x price that stays under the factor of 8;
  - an item with only 3 lines, so it is never checked;
  - vendors that are held but carried forward, held and not in force, blocked, or inactive.

## Assumptions the labels rest on

1. The duplicate, shared-bank, same-tax-id and similar-name checks compare the rows of the current batch (portal and
   ERP together). They do not compare a row against `previous.csv`. No current row collides with a snapshot value of a
   *different* vendor except in the intended pairs (V1055/V1056 and V1057/V2040), and those are already labelled review.
2. Two rows with the same vendor_id are not "another record" for the same-tax-id or shared-bank checks. In particular,
   the first row of an exact-duplicate pair stays **accepted** even though its duplicate has the same EIN and bank.
3. The outlier check compares a line with the other lines of the same item code: a typical value such as the median,
   by a ratio of 8 in either direction. All 4 outlier groups contain only lines that are otherwise clean, active and
   consistent.
4. A held vendor with an unreadable status (V2024, ERP row 23, `STAT 'A'`) is not "blocked or inactive". It is therefore
   carried forward.
5. Rows from the vendor files are processed portal first, then ERP. No label depends on this order: the only cross-file
   same-id pair (V1063) differs in content, so both rows are review whatever the order.
6. The ERP date formats `%Y-%m-%d` and `%d.%m.%Y` can never give one string two readings, and the portal has only one
   format. So **no row tests the "ambiguous date" review**: it cannot happen with this config.

## Rows I was unsure about

| File / row | Label | Doubt |
|---|---|---|
| portal 19 `routing_number_with_spaces` | accepted | ABA printed as `NNNN NNNN N`. `routing_number` has no `digits_only` normalisation. I read the spaces as formatting around a valid ABA number. A strict gate would reject the row. |
| portal 23 `fullwidth_digits_in_terms` | accepted | Terms `３０`. Python's `int()` reads full-width digits as 30, and NFKC also gives 30. A gate that accepts ASCII digits only would reject the row. |
| portal 30 `ein_with_space` | rejected | EIN `NN NNNNNNN`. The policy says `ein` turns *9 digits* into NN-NNNNNNN, and contrasts this with `digits_only`, which removes "spaces and hyphens (only)". I took it that `ein` does not remove an inner space, so the pattern fails. If `ein` strips non-digits, the row is accepted. |
| portal 40 `zero_width_space_in_vendor_id` | rejected | U+200B is not whitespace for `trim`, so `V1043`+ZWSP fails the id pattern. A gate that removes zero-width characters first would accept the row. |
| portal 24 `zero_width_space_in_name` | accepted | No rule covers invisible characters in a name. |
| portal 7 `tab_and_double_space_in_name` | accepted | Accepted whether or not a tab counts as a space when collapsing, because names are not change-controlled. |
| portal 22 `date_without_zero_padding_terms_zero` | accepted | `3/7/2024` parses with `strptime('%m/%d/%Y')`. A regex-based date reader that wants two digits would reject the row. |
| portal 14 / 17 | accepted | The 120-character name (row 14) scores 100 on the fuzzy check against the 121-character one (row 42, rejected), and Alder Creek `Inc`/`Inc.` (rows 16 and 17) score 100. In both pairs the EINs are filled and different, so `unless_different` suppresses the similar-name check. Rejected rows should not take part in the check anyway. |
| portal 56 `lookalike_name_cyrillic_a` | review | The two names differ by one code point (rapidfuzz ratio 97, at or above 92). A gate that folds confusable characters first scores 100. Either way the row is review. |
| portal 26 + 61, erp 16 + 48 | accepted + duplicate | Assumes the duplicate is dropped before the same-tax-id and shared-bank checks (assumption 2). |
| erp 9 `bank_account_numeric_cell` | accepted | The account is a number cell, `482019375512`. It is accepted if read as an integer. A gate that turns the cell into a float string (`...512.0`) would reject the row. |
| erp 14 `ein_numeric_cell` | accepted | TAX_ID is the number `451234567`, which has 9 digits, so `ein` gives `45-1234567`. Same doubt about number cells as above. |
| erp 21 `tax_id_formula_cell` | rejected | The formula has no cached value. The gate may read the cell as empty (a US vendor without an EIN) or as the text `=TEXT(...)`, which fails the pattern and starts with `=`. Both readings give rejected. |
| erp 20 `status_is_excel_boolean` | rejected | TRUE is not ACTIVE, INACTIVE or HOLD. |
| erp 25 `terms_mixed_case_net` | rejected | The strip pattern `^NET\s*` is upper-case, and the policy only says *value_maps* are case-insensitive. If the gate strips case-insensitively, the row is accepted. |
| erp 29 `routing_numeric_cell_lost_leading_zero` | rejected | Rejected because the 8-digit number cannot be read as an ABA number. A gate that zero-pads to 9 digits would accept the row. |
| po 37 `price_with_currency_symbol` | rejected | The policy only allows US thousands separators, so `$1,250.00` is not a number. |
| po 43 `receipt_flag_x` | rejected | `X` is SAP's tick mark, but nothing says the bool type accepts it. The other lines use `yes`/`no`, the downstream format. |
| po 58 `price_outlier_low` | review | Assumes "far from" is checked below the typical price as well as above it (0.25 vs about 24.75). |
| po 60 `price_outlier_high` | review | 1045 vs about 10.4. A gate that compares with a mean *including* the line itself would see only about 5.7x. |
| po 62 `item_code_scientific_notation` | rejected | Assumes `item_code` counts as an identifier field for the scientific-notation check. If it does not, the row is accepted. |
| po 67 `vendor_inactive_closed_po` | review | The vendor is inactive and the PO is already closed. The rule makes no exception for closed POs. |
| po 77 `blocked_held_vendor_not_carried` | rejected | V1065 is held, and the held version is blocked, so its old version is not carried forward and the vendor is absent from the reference: rejected. If the gate kept the held version in the reference as blocked, the line would be review instead. |
