# Statement Spreader

Financial statements in (an SEC 10-K, a PDF, an Excel workbook); a standard **spread** out: every
income-statement, balance-sheet and cash-flow line mapped to one template, per period, with each
number traced to the exact printed cell it came from, checked by accounting identities, and either
auto-accepted or sent to a reviewer with a reason. Built as a reusable foundation for an internal AI
pilot in credit, FP&A or audit: a new organisation adapts it with a configuration overlay, not code.

It measures itself. Every rate below comes from a command in [TESTING.md](TESTING.md), against
answer keys the pipeline never sees, and carries a 95% range.

## What it does

1. **Reads** HTML (including inline-XBRL filings, ignoring the tags and anything hidden), PDFs with
   a text layer (words rebuilt into rows, with page and box for every number) and Excel (cell
   references, hidden rows and sheets skipped, formulas without saved values refused).
2. **Finds the statements**, their periods (from headers, titles, other statements or the cover
   page) and their unit ("in millions, except per share").
3. **Finds totals by footing**: a row is a total when it equals the rows above it in every period.
4. **Maps each row** to the template with a confidence and a reason: reviewer memory, aliases,
   section rules, spelling, structure, and optionally a local language model that only ever picks
   a line id from a closed list and never sees a number.
5. **Assembles** one value per line and period with its provenance trail (read, scale, sum, sign,
   map, calculate, correct), and a status: extracted, normalized, calculated, AI-mapped, human,
   assumed or missing.
6. **Checks**: balance sheet balances, subtotals, cash-flow roll-forward, cross-statement and
   cross-period ties, EPS x shares vs net income, with rounding tolerance from the printed scale.
7. **Sends to review** whatever it doubts: failed checks, assumed units or periods, low-confidence
   mappings, unplaced rows, unreadable or ambiguous numbers, suspicious jumps, covenant breaches.
8. **Lets a reviewer** inspect any value back to its source, correct it with a reason, remap rows
   (remembered for next time), resolve items with notes, and approve: approval is refused while a
   blocking item is open. Everything is an audit event.
9. **Exports** Excel (spread, sources, checks, review, ratios; never live formulas), CSV and JSON.
10. **Measures ROI** from timed work sessions (by hand vs assisted, active time only), labelling
    every number observed, estimated, hypothetical or assumption, and keeping released capacity
    apart from cash saved.

## Measured results (2026-10-24)

SEC set: 63 recent 10-K filings of non-financial companies, split by ticker hash into a **dev** half
(tuned on) and a **holdout** half (measured, never tuned on). Answer keys come from each filing's
inline XBRL tags through an independent crosswalk. Synthetic set: 40 generated private-company
statement packages (30 clean, 10 adversarial) in HTML, Excel and PDF, with exact keys.

| Set | Documents | Values right | Silent error rate | Silent omissions | Wrong values caught | Review items per document (median) |
|---|---|---|---|---|---|---|
| SEC dev, HTML (tuned on) | 33 | 80.0% (3,542 of 4,425; 78.8-81.2%) | 2.8% (70 of 2,542; 2.2-3.5%) | 3.9% (171 of 4,425; 3.3-4.5%) | 68.2% (150 of 220; 61.8-74.0%) | 21 |
| SEC dev, HTML, + local model | 33 | 83.3% (3,608 of 4,333; 82.1-84.3%) | 2.1% (53 of 2,485; 1.6-2.8%) | 3.0% (128 of 4,333; 2.5-3.5%) | 79.5% (205 of 258; 74.1-83.9%) | 25 |
| **SEC holdout, HTML (never tuned on)** | 30 | 73.5% (2,858 of 3,890; 72.1-74.8%) | 3.2% (68 of 2,100; 2.6-4.1%) | 5.3% (208 of 3,890; 4.7-6.1%) | 81.7% (304 of 372; 77.5-85.3%) | 20 |
| SEC holdout, HTML, + local model | 30 | 75.0% (2,870 of 3,827; 73.6-76.3%) | 2.8% (59 of 2,086; 2.2-3.6%) | 3.8% (144 of 3,827; 3.2-4.4%) | 86.9% (392 of 451; 83.5-89.7%) | 24 |
| Synthetic, 40 cases x HTML/Excel/PDF | 120 | 97.0% (14,085 of 14,517; 96.7-97.3%) | 0.0% (6 of 13,452; 0.0-0.1%) | 1.7% (252 of 14,517; 1.5-2.0%) | 0.0% (0 of 6; 0.0-39.0%) | 1 |
| SEC dev printed to PDF | 33 | 77.5% (3,572 of 4,612; 76.2-78.6%) | 7.0% (193 of 2,756; 6.1-8.0%) | 2.5% (115 of 4,612; 2.1-3.0%) | - | - |

Sources: `eval/reports/{dev,holdout}-final[-model].json`, `eval/reports/syn-final.json`, `eval/sec/pdf/eval-sec-pdf-final.json`; regenerate with `scripts/run_eval.py`, `scripts/print_sec_pdfs.py --eval` and `scripts/results_table.py`. The PDF row's silent error rate is not comparable with the HTML rows: the scorer's "unjudged" correction (values the answer key cannot judge) matches HTML cell paths, so it never applies to PDFs. "Review items per document" is the reviewer's workload: one failed check flags several values but is resolved once.

The **silent error rate** is the share of auto-accepted values that are wrong: of what would go out
without a person looking, how much is wrong. Every improvement and every reverted idea is in
[IMPROVEMENT_LOG.md](IMPROVEMENT_LOG.md).

What these numbers do **not** show:
- SEC filings are cleaner than a borrower's scanned PDF; scanned PDFs (no text layer) are refused.
- The synthetic corpus was written by the same team that wrote the pipeline.
- ROI: no time savings have been measured yet. The ROI page reports "not measured" until at least
  three documents are spread by hand and three reviewed in assisted mode by a real analyst.

## Run it

```bash
py -3.11 -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
cd web && npm install && npm run build && cd ..
.venv/Scripts/python scripts/load_demo.py var/demo          # optional: a few documents to look at
SPREADER_DATA=var/demo .venv/Scripts/python -m uvicorn spreader.api:app --host 127.0.0.1 --port 8765
```

Open http://127.0.0.1:8765. To use an organisation's overlay:
`SPREADER_PROFILE=config/profiles/example-lender-overlay.yaml`. To turn on the local model tier, run
llama.cpp's `llama-server` on 127.0.0.1 and set `SPREADER_MODEL_URL=http://127.0.0.1:8088`.

Needs nothing paid: Python 3.11, Node 18+, and optionally an NVIDIA GPU for the model tier
(measured on an RTX 3060 Ti: about 0.35 s per row, 4.8 GB of GPU memory).

## Adapting it to an organisation

- **Template, aliases, checks, ratios, covenants**: `config/profiles/*.yaml`; an overlay
  (`extends:`) adds an organisation's labels, detection patterns, checks and covenant limits
  without copying the base ([example](config/profiles/example-lender-overlay.yaml)).
- **Sources**: a reader returns the same `DocumentIR` (tables of positioned tokens with source
  references); a new connector (SharePoint folder, email, a loan system's document API) only has to
  deliver bytes to `service.upload`.
- **Outputs**: `export.py` (Excel, CSV, JSON); a push to a downstream system belongs behind the
  approval gate.
- **Model provider**: `llm/` is optional and isolated; replacing the local server with an
  organisation's approved model endpoint changes one class.

## Limits and what production would need

Sign-in and roles (the reviewer name is an unverified header), a retention and deletion policy,
encryption at rest, OCR for scanned statements, multi-user concurrency on a server database, and,
in banking, model-risk-management review. See [THREAT_MODEL.md](THREAT_MODEL.md) and
[DECISIONS.md](DECISIONS.md).
