# Invoice evaluation: invoice-v2

Policy default-ap 4a1df7e3bcf5208b. Synthetic invoices (PDF printed by headless Edge in three layouts, plus structured JSON), vendor master, POs and receipts from the generator; the answer key is written by the generator. $0: no model or API calls.

## dev (81 invoices, 0.025 s each on average)

three layouts the extractor was developed on.

| Measure | Result |
|---|---|
| **False touchless** (eligible without a person while a problem was planted) | 0.0% (0 of 37; likely 0.0-9.4%) |
| Touchless (eligible, no exception above info, no human touch) | 54.3% (44 of 81; likely 43.5-64.7%) |
| Clean invoices that went through untouched | 100.0% (44 of 44; likely 92.0-100.0%) |
| Clean invoices stopped by a false exception | 0.0% (0 of 44; likely 0.0-8.0%) |
| Header fields right | 100.0% (729 of 729; likely 99.5-100.0%) |
| Line items read exactly (description, qty, price, amount) | 100.0% (242 of 242; likely 98.4-100.0%) |
| PO matches that are the right PO | 100.0% (77 of 77; likely 95.2-100.0%) |
| Invoices with a true PO matched to it | 100.0% (77 of 77; likely 95.2-100.0%) |
| Invoice lines tied to the right PO line | 100.0% (234 of 234; likely 98.4-100.0%) |
| Planted problems raised with the right reason code | 100.0% (37 of 37; likely 90.6-100.0%) |
| Duplicate flags that are real duplicates | 100.0% (6 of 6; likely 61.0-100.0%) |
| Duplicates caught | 100.0% (6 of 6; likely 61.0-100.0%) |

Header fields:

| Field | Right |
|---|---|
| vendor_id | 100.0% (81 of 81; likely 95.5-100.0%) |
| invoice_number | 100.0% (81 of 81; likely 95.5-100.0%) |
| invoice_date | 100.0% (81 of 81; likely 95.5-100.0%) |
| due_date | 100.0% (81 of 81; likely 95.5-100.0%) |
| po_number | 100.0% (81 of 81; likely 95.5-100.0%) |
| currency | 100.0% (81 of 81; likely 95.5-100.0%) |
| subtotal | 100.0% (81 of 81; likely 95.5-100.0%) |
| tax | 100.0% (81 of 81; likely 95.5-100.0%) |
| total | 100.0% (81 of 81; likely 95.5-100.0%) |

Reason codes (planted problems):

| Code | Raised |
|---|---|
| BANK_DETAILS_CHANGED | 100.0% (3 of 3; likely 43.8-100.0%) |
| BANK_DETAILS_UNVERIFIED | 100.0% (2 of 2; likely 34.2-100.0%) |
| EXACT_DUPLICATE | 100.0% (4 of 4; likely 51.0-100.0%) |
| LINE_EXTENSION_MISMATCH | 100.0% (3 of 3; likely 43.8-100.0%) |
| MISSING_RECEIPT | 100.0% (3 of 3; likely 43.8-100.0%) |
| NO_PO_REFERENCE | 100.0% (2 of 2; likely 34.2-100.0%) |
| POSSIBLE_DUPLICATE | 100.0% (2 of 2; likely 34.2-100.0%) |
| PO_NOT_FOUND | 100.0% (2 of 2; likely 34.2-100.0%) |
| PO_NOT_OPEN | 100.0% (2 of 2; likely 34.2-100.0%) |
| PRICE_OVER_PO | 100.0% (3 of 3; likely 43.8-100.0%) |
| QTY_EXCEEDS_RECEIVED | 100.0% (3 of 3; likely 43.8-100.0%) |
| TAX_MISMATCH | 100.0% (2 of 2; likely 34.2-100.0%) |
| TAX_UNVERIFIED | 100.0% (2 of 2; likely 34.2-100.0%) |
| TOTAL_MISMATCH | 100.0% (2 of 2; likely 34.2-100.0%) |
| VENDOR_MISMATCH | 100.0% (2 of 2; likely 34.2-100.0%) |

| Scenario | Invoices | Touchless | Codes raised | False exceptions |
|---|---|---|---|---|
| bank_changed | 3 | 0 | 3 of 3 |  |
| bank_unverified | 2 | 0 | 2 of 2 |  |
| clean | 22 | 22 |  |  |
| closed_po | 2 | 0 | 2 of 2 |  |
| exact_dup | 3 | 0 | 3 of 3 |  |
| json_clean | 3 | 3 |  |  |
| line_math | 3 | 0 | 3 of 3 |  |
| missing_receipt | 3 | 0 | 3 of 3 |  |
| multipage | 2 | 2 |  |  |
| no_po_ref | 2 | 0 | 2 of 2 |  |
| over_receipt | 3 | 0 | 3 of 3 |  |
| po_not_found | 2 | 0 | 2 of 2 |  |
| possible_dup | 2 | 0 | 2 of 2 |  |
| price_over | 3 | 0 | 3 of 3 |  |
| price_within_tol | 3 | 3 |  |  |
| same_file_again | 1 | 0 | 1 of 1 |  |
| sequential | 6 | 6 |  |  |
| service_2way | 4 | 4 |  |  |
| similar_distinct | 2 | 2 |  |  |
| tax_unverified | 2 | 0 | 2 of 2 |  |
| tax_wrong | 2 | 0 | 2 of 2 |  |
| total_math | 2 | 0 | 2 of 2 |  |
| vendor_alias | 2 | 2 |  |  |
| vendor_mismatch | 2 | 0 | 2 of 2 |  |

## holdout (81 invoices, 0.025 s each on average)

same three layouts, new seed: never used for tuning.

| Measure | Result |
|---|---|
| **False touchless** (eligible without a person while a problem was planted) | 0.0% (0 of 37; likely 0.0-9.4%) |
| Touchless (eligible, no exception above info, no human touch) | 53.1% (43 of 81; likely 42.3-63.6%) |
| Clean invoices that went through untouched | 97.7% (43 of 44; likely 88.2-99.6%) |
| Clean invoices stopped by a false exception | 2.3% (1 of 44; likely 0.4-11.8%) |
| Header fields right | 100.0% (729 of 729; likely 99.5-100.0%) |
| Line items read exactly (description, qty, price, amount) | 100.0% (263 of 263; likely 98.6-100.0%) |
| PO matches that are the right PO | 100.0% (77 of 77; likely 95.2-100.0%) |
| Invoices with a true PO matched to it | 100.0% (77 of 77; likely 95.2-100.0%) |
| Invoice lines tied to the right PO line | 100.0% (253 of 253; likely 98.5-100.0%) |
| Planted problems raised with the right reason code | 100.0% (37 of 37; likely 90.6-100.0%) |
| Duplicate flags that are real duplicates | 85.7% (6 of 7; likely 48.7-97.4%) |
| Duplicates caught | 100.0% (6 of 6; likely 61.0-100.0%) |

Header fields:

| Field | Right |
|---|---|
| vendor_id | 100.0% (81 of 81; likely 95.5-100.0%) |
| invoice_number | 100.0% (81 of 81; likely 95.5-100.0%) |
| invoice_date | 100.0% (81 of 81; likely 95.5-100.0%) |
| due_date | 100.0% (81 of 81; likely 95.5-100.0%) |
| po_number | 100.0% (81 of 81; likely 95.5-100.0%) |
| currency | 100.0% (81 of 81; likely 95.5-100.0%) |
| subtotal | 100.0% (81 of 81; likely 95.5-100.0%) |
| tax | 100.0% (81 of 81; likely 95.5-100.0%) |
| total | 100.0% (81 of 81; likely 95.5-100.0%) |

Reason codes (planted problems):

| Code | Raised |
|---|---|
| BANK_DETAILS_CHANGED | 100.0% (3 of 3; likely 43.8-100.0%) |
| BANK_DETAILS_UNVERIFIED | 100.0% (2 of 2; likely 34.2-100.0%) |
| EXACT_DUPLICATE | 100.0% (4 of 4; likely 51.0-100.0%) |
| LINE_EXTENSION_MISMATCH | 100.0% (3 of 3; likely 43.8-100.0%) |
| MISSING_RECEIPT | 100.0% (3 of 3; likely 43.8-100.0%) |
| NO_PO_REFERENCE | 100.0% (2 of 2; likely 34.2-100.0%) |
| POSSIBLE_DUPLICATE | 100.0% (2 of 2; likely 34.2-100.0%) |
| PO_NOT_FOUND | 100.0% (2 of 2; likely 34.2-100.0%) |
| PO_NOT_OPEN | 100.0% (2 of 2; likely 34.2-100.0%) |
| PRICE_OVER_PO | 100.0% (3 of 3; likely 43.8-100.0%) |
| QTY_EXCEEDS_RECEIVED | 100.0% (3 of 3; likely 43.8-100.0%) |
| TAX_MISMATCH | 100.0% (2 of 2; likely 34.2-100.0%) |
| TAX_UNVERIFIED | 100.0% (2 of 2; likely 34.2-100.0%) |
| TOTAL_MISMATCH | 100.0% (2 of 2; likely 34.2-100.0%) |
| VENDOR_MISMATCH | 100.0% (2 of 2; likely 34.2-100.0%) |

| Scenario | Invoices | Touchless | Codes raised | False exceptions |
|---|---|---|---|---|
| bank_changed | 3 | 0 | 3 of 3 |  |
| bank_unverified | 2 | 0 | 2 of 2 |  |
| clean | 22 | 22 |  |  |
| closed_po | 2 | 0 | 2 of 2 |  |
| exact_dup | 3 | 0 | 3 of 3 |  |
| json_clean | 3 | 3 |  |  |
| line_math | 3 | 0 | 3 of 3 |  |
| missing_receipt | 3 | 0 | 3 of 3 |  |
| multipage | 2 | 2 |  |  |
| no_po_ref | 2 | 0 | 2 of 2 |  |
| over_receipt | 3 | 0 | 3 of 3 |  |
| po_not_found | 2 | 0 | 2 of 2 |  |
| possible_dup | 2 | 0 | 2 of 2 |  |
| price_over | 3 | 0 | 3 of 3 |  |
| price_within_tol | 3 | 3 |  |  |
| same_file_again | 1 | 0 | 1 of 1 |  |
| sequential | 6 | 5 |  | 1 |
| service_2way | 4 | 4 |  |  |
| similar_distinct | 2 | 2 |  |  |
| tax_unverified | 2 | 0 | 2 of 2 |  |
| tax_wrong | 2 | 0 | 2 of 2 |  |
| total_math | 2 | 0 | 2 of 2 |  |
| vendor_alias | 2 | 2 |  |  |
| vendor_mismatch | 2 | 0 | 2 of 2 |  |

## unseen (81 invoices, 0.024 s each on average)

a fourth layout with other wording, never seen in development, default policy.

| Measure | Result |
|---|---|
| **False touchless** (eligible without a person while a problem was planted) | 0.0% (0 of 37; likely 0.0-9.4%) |
| Touchless (eligible, no exception above info, no human touch) | 3.7% (3 of 81; likely 1.3-10.3%) |
| Clean invoices that went through untouched | 6.8% (3 of 44; likely 2.3-18.2%) |
| Clean invoices stopped by a false exception | 93.2% (41 of 44; likely 81.8-97.7%) |
| Header fields right | 36.1% (263 of 729; likely 32.7-39.6%) |
| Line items read exactly (description, qty, price, amount) | 1.6% (4 of 253; likely 0.6-4.0%) |
| PO matches that are the right PO | 100.0% (3 of 3; likely 43.8-100.0%) |
| Invoices with a true PO matched to it | 3.9% (3 of 77; likely 1.3-10.8%) |
| Invoice lines tied to the right PO line | 100.0% (4 of 4; likely 51.0-100.0%) |
| Planted problems raised with the right reason code | 27.0% (10 of 37; likely 15.4-43.0%) |
| Duplicate flags that are real duplicates | 100.0% (1 of 1; likely 20.7-100.0%) |
| Duplicates caught | 16.7% (1 of 6; likely 3.0-56.4%) |

Header fields:

| Field | Right |
|---|---|
| vendor_id | 100.0% (81 of 81; likely 95.5-100.0%) |
| invoice_number | 3.7% (3 of 81; likely 1.3-10.3%) |
| invoice_date | 3.7% (3 of 81; likely 1.3-10.3%) |
| due_date | 100.0% (81 of 81; likely 95.5-100.0%) |
| po_number | 6.2% (5 of 81; likely 2.7-13.6%) |
| currency | 3.7% (3 of 81; likely 1.3-10.3%) |
| subtotal | 3.7% (3 of 81; likely 1.3-10.3%) |
| tax | 100.0% (81 of 81; likely 95.5-100.0%) |
| total | 3.7% (3 of 81; likely 1.3-10.3%) |

Reason codes (planted problems):

| Code | Raised |
|---|---|
| BANK_DETAILS_CHANGED | 100.0% (3 of 3; likely 43.8-100.0%) |
| BANK_DETAILS_UNVERIFIED | 100.0% (2 of 2; likely 34.2-100.0%) |
| EXACT_DUPLICATE | 25.0% (1 of 4; likely 4.6-69.9%) |
| LINE_EXTENSION_MISMATCH | 0.0% (0 of 3; likely 0.0-56.2%) |
| MISSING_RECEIPT | 0.0% (0 of 3; likely 0.0-56.2%) |
| NO_PO_REFERENCE | 100.0% (2 of 2; likely 34.2-100.0%) |
| POSSIBLE_DUPLICATE | 0.0% (0 of 2; likely 0.0-65.8%) |
| PO_NOT_FOUND | 0.0% (0 of 2; likely 0.0-65.8%) |
| PO_NOT_OPEN | 0.0% (0 of 2; likely 0.0-65.8%) |
| PRICE_OVER_PO | 0.0% (0 of 3; likely 0.0-56.2%) |
| QTY_EXCEEDS_RECEIVED | 0.0% (0 of 3; likely 0.0-56.2%) |
| TAX_MISMATCH | 0.0% (0 of 2; likely 0.0-65.8%) |
| TAX_UNVERIFIED | 100.0% (2 of 2; likely 34.2-100.0%) |
| TOTAL_MISMATCH | 0.0% (0 of 2; likely 0.0-65.8%) |
| VENDOR_MISMATCH | 0.0% (0 of 2; likely 0.0-65.8%) |

| Scenario | Invoices | Touchless | Codes raised | False exceptions |
|---|---|---|---|---|
| bank_changed | 3 | 0 | 3 of 3 |  |
| bank_unverified | 2 | 0 | 2 of 2 |  |
| clean | 22 | 0 |  | 22 |
| closed_po | 2 | 0 | 0 of 2 |  |
| exact_dup | 3 | 0 | 0 of 3 |  |
| json_clean | 3 | 3 |  |  |
| line_math | 3 | 0 | 0 of 3 |  |
| missing_receipt | 3 | 0 | 0 of 3 |  |
| multipage | 2 | 0 |  | 2 |
| no_po_ref | 2 | 0 | 2 of 2 |  |
| over_receipt | 3 | 0 | 0 of 3 |  |
| po_not_found | 2 | 0 | 0 of 2 |  |
| possible_dup | 2 | 0 | 0 of 2 |  |
| price_over | 3 | 0 | 0 of 3 |  |
| price_within_tol | 3 | 0 |  | 3 |
| same_file_again | 1 | 0 | 1 of 1 |  |
| sequential | 6 | 0 |  | 6 |
| service_2way | 4 | 0 |  | 4 |
| similar_distinct | 2 | 0 |  | 2 |
| tax_unverified | 2 | 0 | 2 of 2 |  |
| tax_wrong | 2 | 0 | 0 of 2 |  |
| total_math | 2 | 0 | 0 of 2 |  |
| vendor_alias | 2 | 0 |  | 2 |
| vendor_mismatch | 2 | 0 | 0 of 2 |  |

Failures to investigate (first 15):

- inv-001-tax_wrong: invoice_number (got None, want INV-007001)
- inv-001-tax_wrong: invoice_date (got None, want 2026-03-22)
- inv-001-tax_wrong: po_number (got None, want PO-4501)
- inv-001-tax_wrong: currency (got None, want USD)
- inv-001-tax_wrong: subtotal (got None, want 5114.44)
- inv-001-tax_wrong: total (got None, want 5476.62)
- inv-001-tax_wrong: lines (got 0 of 2 right (0 read), want )
- inv-001-tax_wrong: missed TAX_MISMATCH (got ['CURRENCY_UNKNOWN', 'MISSING_FIELD', 'NO_LINE_ITEMS', 'NO_PO_REFERENCE', 'TAX_UNVERIFIED'], want )
- inv-002-clean: invoice_number (got None, want INV-007002)
- inv-002-clean: invoice_date (got None, want 2026-03-05)
- inv-002-clean: po_number (got None, want PO-4502)
- inv-002-clean: currency (got None, want USD)
- inv-002-clean: subtotal (got None, want 1635.00)
- inv-002-clean: total (got None, want 1749.45)
- inv-002-clean: lines (got 0 of 1 right (0 read), want )

## unseen+wording (81 invoices, 0.027 s each on average)

the same unseen set with the wording overlay example-supplier-layout-d 9442acbe2b103983.

| Measure | Result |
|---|---|
| **False touchless** (eligible without a person while a problem was planted) | 0.0% (0 of 37; likely 0.0-9.4%) |
| Touchless (eligible, no exception above info, no human touch) | 54.3% (44 of 81; likely 43.5-64.7%) |
| Clean invoices that went through untouched | 100.0% (44 of 44; likely 92.0-100.0%) |
| Clean invoices stopped by a false exception | 0.0% (0 of 44; likely 0.0-8.0%) |
| Header fields right | 100.0% (729 of 729; likely 99.5-100.0%) |
| Line items read exactly (description, qty, price, amount) | 100.0% (253 of 253; likely 98.5-100.0%) |
| PO matches that are the right PO | 100.0% (77 of 77; likely 95.2-100.0%) |
| Invoices with a true PO matched to it | 100.0% (77 of 77; likely 95.2-100.0%) |
| Invoice lines tied to the right PO line | 100.0% (246 of 246; likely 98.5-100.0%) |
| Planted problems raised with the right reason code | 100.0% (37 of 37; likely 90.6-100.0%) |
| Duplicate flags that are real duplicates | 100.0% (6 of 6; likely 61.0-100.0%) |
| Duplicates caught | 100.0% (6 of 6; likely 61.0-100.0%) |

Header fields:

| Field | Right |
|---|---|
| vendor_id | 100.0% (81 of 81; likely 95.5-100.0%) |
| invoice_number | 100.0% (81 of 81; likely 95.5-100.0%) |
| invoice_date | 100.0% (81 of 81; likely 95.5-100.0%) |
| due_date | 100.0% (81 of 81; likely 95.5-100.0%) |
| po_number | 100.0% (81 of 81; likely 95.5-100.0%) |
| currency | 100.0% (81 of 81; likely 95.5-100.0%) |
| subtotal | 100.0% (81 of 81; likely 95.5-100.0%) |
| tax | 100.0% (81 of 81; likely 95.5-100.0%) |
| total | 100.0% (81 of 81; likely 95.5-100.0%) |

Reason codes (planted problems):

| Code | Raised |
|---|---|
| BANK_DETAILS_CHANGED | 100.0% (3 of 3; likely 43.8-100.0%) |
| BANK_DETAILS_UNVERIFIED | 100.0% (2 of 2; likely 34.2-100.0%) |
| EXACT_DUPLICATE | 100.0% (4 of 4; likely 51.0-100.0%) |
| LINE_EXTENSION_MISMATCH | 100.0% (3 of 3; likely 43.8-100.0%) |
| MISSING_RECEIPT | 100.0% (3 of 3; likely 43.8-100.0%) |
| NO_PO_REFERENCE | 100.0% (2 of 2; likely 34.2-100.0%) |
| POSSIBLE_DUPLICATE | 100.0% (2 of 2; likely 34.2-100.0%) |
| PO_NOT_FOUND | 100.0% (2 of 2; likely 34.2-100.0%) |
| PO_NOT_OPEN | 100.0% (2 of 2; likely 34.2-100.0%) |
| PRICE_OVER_PO | 100.0% (3 of 3; likely 43.8-100.0%) |
| QTY_EXCEEDS_RECEIVED | 100.0% (3 of 3; likely 43.8-100.0%) |
| TAX_MISMATCH | 100.0% (2 of 2; likely 34.2-100.0%) |
| TAX_UNVERIFIED | 100.0% (2 of 2; likely 34.2-100.0%) |
| TOTAL_MISMATCH | 100.0% (2 of 2; likely 34.2-100.0%) |
| VENDOR_MISMATCH | 100.0% (2 of 2; likely 34.2-100.0%) |

| Scenario | Invoices | Touchless | Codes raised | False exceptions |
|---|---|---|---|---|
| bank_changed | 3 | 0 | 3 of 3 |  |
| bank_unverified | 2 | 0 | 2 of 2 |  |
| clean | 22 | 22 |  |  |
| closed_po | 2 | 0 | 2 of 2 |  |
| exact_dup | 3 | 0 | 3 of 3 |  |
| json_clean | 3 | 3 |  |  |
| line_math | 3 | 0 | 3 of 3 |  |
| missing_receipt | 3 | 0 | 3 of 3 |  |
| multipage | 2 | 2 |  |  |
| no_po_ref | 2 | 0 | 2 of 2 |  |
| over_receipt | 3 | 0 | 3 of 3 |  |
| po_not_found | 2 | 0 | 2 of 2 |  |
| possible_dup | 2 | 0 | 2 of 2 |  |
| price_over | 3 | 0 | 3 of 3 |  |
| price_within_tol | 3 | 3 |  |  |
| same_file_again | 1 | 0 | 1 of 1 |  |
| sequential | 6 | 6 |  |  |
| service_2way | 4 | 4 |  |  |
| similar_distinct | 2 | 2 |  |  |
| tax_unverified | 2 | 0 | 2 of 2 |  |
| tax_wrong | 2 | 0 | 2 of 2 |  |
| total_math | 2 | 0 | 2 of 2 |  |
| vendor_alias | 2 | 2 |  |  |
| vendor_mismatch | 2 | 0 | 2 of 2 |  |

