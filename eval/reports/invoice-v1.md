# Invoice evaluation: invoice-v1

Policy default-ap 4a1df7e3bcf5208b. Synthetic invoices (PDF printed by headless Edge in three layouts, plus structured JSON), vendor master, POs and receipts from the generator; the answer key is written by the generator. $0: no model or API calls.

## dev (81 invoices, 0.042 s each on average)

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

## holdout (81 invoices, 0.027 s each on average)

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

