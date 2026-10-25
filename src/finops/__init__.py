"""Finance operations platform: a shared core and three engines.

    finops.core      what every engine needs: money, tables, configuration, fingerprints,
                     exceptions (the review queue), an append-only audit log, rates and reports
    spreader         engine one, financial statement spreading (its own package, kept as built)
    finops.recon     engine two, reconciliation and exception management
    finops.invoice   engine three, invoice intake and three-way matching

The rule every engine follows: arithmetic, matching constraints and policy are deterministic
code; anything uncertain becomes an exception a person resolves; nothing is approved or paid
by this software.
"""

__version__ = "0.1.0"
