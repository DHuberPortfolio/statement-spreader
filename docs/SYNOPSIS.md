# Finance Operations platform: synopsis

## What it is

A working prototype that takes on the keying and ticking in finance operations, checks its own work, and sends a person only
what it isn't sure of. It is built around one rule: nothing is approved, paid or released without a named person, and a wrong
number should never pass quietly.

## What it can do today

**Statement spreading (the core).** It reads a company's financial statements from an SEC filing, a PDF with a text layer or an
Excel workbook, and places each number on a standard template.
- Every number links back to the printed cell it came from.
- Accounting checks run on the result. A value goes through without review only if independent evidence agrees with it, such as
  a check that adds up, the same number repeated in the filing, last year's approved spread, or a label's track record.
- Blockers and warnings open to show what is wrong, why it matters, the printed statement with the row marked, suggested fixes,
  and a place to fix it with a recorded reason.
- Spreads export to Excel, CSV and JSON.
- Each company's approved spreads and each person's corrections feed later documents.

**Reconciliation.** Matches bank lines to the ledger. Only unambiguous matches settle alone; the rest are proposed to a person,
and exceptions are closed with a recorded decision.

**Invoices.** Reads invoices, checks the arithmetic, matches them to purchase orders and receipts, and screens for duplicates and
changed bank details. The best status it can give is "eligible for approval": approval and payment stay in the ERP.

**Data quality.** Checks vendor and purchase-order exports before another system loads them. Definite errors are rejected and
suspicious records are held for a person.

**Spreadsheets.** Scans workbooks for broken references, inconsistent formulas, typed-over numbers and risky changes between
versions. It only reads the workbook.

**Results for management.** Accuracy is reported in plain language. Time saved covers hours, cash, costs and what-if scenarios,
with every figure labelled as measured, estimated or an assumption. Review time is recorded in the background, and only managers
and admins see time and ROI figures.

**Controls.** Named sign-in with roles, optional two-person approval, and an audit log built to reveal later edits. An optional
AI second opinion runs in shadow during a learning period, with senior reviewers ruling on disagreements.

## How well it works

Measured on real SEC filings only, against each filing's own XBRL tags, a separate route to the numbers.

**Unseen test.** 101 filings from companies drawn at random by industry and size, kept out of tuning:

| Measure | Before this round | Now |
|---|---|---|
| Numbers right | 74.8% | 81.5% |
| Wrong with no flag | 6 of 1,574 | 6 of 1,762 |
| Blank with no flag | 707 of 10,037 | 502 of 10,019 |
| Right with no person involved | 15.6% | 17.5% |

The test set was opened more than once while fixing a bug, so it is close to unseen rather than perfectly unseen. In all, 327 real
filings have been used. The original 54 kept-back filings were used to find fixes, so they are now a regression check.

Most numbers still go to a person, and some come out blank, so it speeds up review rather than replacing it. Results come from public
filings, not private-company documents, and reconciliation and invoice rates come from generated test records.

## End goal

A platform a bank, lender or finance team can trust across thousands of companies: it does the repetitive reading, matching and
checking; it can prove every number; it lets through a steadily growing share of work on its own while keeping silent errors under
0.2%; and it leaves people the judgment calls. Next steps toward that are wider testing on real filings and a pilot on an
organisation's own documents, with timed work to measure the real return.
