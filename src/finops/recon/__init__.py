"""Engine two: reconciliation and exception management (two sources, e.g. bank vs general ledger).

    normalize   CSV/Excel rows -> Txn (one sign convention, dates, references), bad rows -> exceptions
    matcher     candidate generation -> scoring -> assignment, layer by layer, strongest evidence first
    classify    what is left over becomes a named exception (fee, timing, duplicate, reversal, ...)
    engine      one deterministic run: prior human decisions applied, totals, completeness checks
    service     persistence: idempotent reruns, decisions, audit events
"""
