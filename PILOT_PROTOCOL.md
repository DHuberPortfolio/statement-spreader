# Analyst pilot protocol

How to measure whether the tool saves an analyst time without costing accuracy (DECISIONS D49). A first feasibility
study: at least three documents spread by hand and three reviewed with the tool. Not a benchmark: with six sessions
the result shows whether a larger study is worth running and roughly what it would find, not a number to put in a
business case.

**Status: no analyst session has been run.** Everything below is the procedure and the tooling; the results are
pending.

## Before starting

1. **Authorisation.** Written permission to use the documents (public 10-Ks need none; borrower statements need the
   data owner's approval and must be anonymised or kept inside the organisation's environment). Confidential documents
   go only into a deployment with sign-in, encryption and retention set (D43, D45, D46).
2. **Documents.** Six statement packages of similar size and difficulty (same industry template, similar number of
   line items, all with income statement, balance sheet and cash flow). Rate each before the study:
   - *low*: clean layout, one unit, two periods, no restatement;
   - *medium*: three periods or a unit change between statements or more than 60 line items;
   - *high*: restated columns, unusual labels, or a scanned page.
   Public SEC filings from the evaluation's holdout half are a good default: their answer keys allow an independent
   quality check (step 6).
3. **Analysts.** At least two, so nobody spreads a document they have already seen. Each records their
   experience (under 1 year, 1-3, 3-5, over 5 years) when starting a session.
4. **Assignment.** Split documents into two comparable sets A and B (same mix of difficulty). Analyst 1 spreads A by
   hand and reviews B with the tool; analyst 2 the reverse. Alternate which arm each analyst does first. The app
   refuses a second timing of one document by the same person.

## Each session

5. **Timing.** In the app, signed in as the analyst: *Time saved* page, timing tool: choose the document, the mode
   (*Baseline* = by hand, *Assisted*), its difficulty and your experience, then *Start timing*. Only active time counts (the timer pauses after a minute without input or when the tab is hidden).
   - *By hand*: start when the empty template opens, stop when every value is keyed and checked by the analyst as
     they normally would. Enter the values in the app's baseline form.
   - *Assisted*: start when the tool's spread opens, stop when the analyst would sign it off (every blocker resolved,
     approval ready). Corrections and resolutions are counted automatically.
   - Processing time of the tool is measured separately (it is in each run's timings) and not added to the analyst's.
   - Breaks, interruptions and questions to the study lead are noted in the session note.

## After the sessions

6. **Independent quality check.** For each document, compare the final values (the hand-keyed values; the approved
   assisted spread) with the answer key (SEC filings) or a second analyst's reconciliation. Record silent errors
   (a wrong value that went out unflagged) and omissions per session. The app compares hand-keyed values with the
   document's approved spread automatically; the approved spread itself must be checked against the key.
7. **Report.** `.venv/Scripts/python scripts/pilot_report.py --out pilot-report.md` writes the observed times,
   corrections and checks, and says PENDING until both arms have three finished sessions. The ROI page applies the
   organisation's own cost assumptions; time saved is released capacity, not cash, unless a finance owner enters a
   cash-realisation share.

## Scoring rubric (per session)

| Measure | Definition | Source |
|---|---|---|
| Active minutes | Timer, inputs and visible tab only | App |
| Elapsed minutes | Start to end, including pauses | App |
| Corrections | Values the analyst changed (assisted) | App |
| Exceptions handled | Review items resolved | App (audit log) |
| Rework | Values changed after the analyst said they were done | Study lead's note |
| Silent errors | Final values that are wrong and were not flagged | Step 6 |
| Omissions | Template values left empty that the document prints | Step 6 |
| Completed without intervention | Share of values accepted by the tool and right | Step 6 |

## Limits to state with any result

Six sessions; two or three analysts; documents chosen, not sampled; by-hand sessions are known to be timed, review time is recorded in the background (D65); the tool's
accuracy on these documents may differ from the evaluation sets. Report the medians with their ranges and the
quality figures side by side; never a time saving without the error rates of both arms.
