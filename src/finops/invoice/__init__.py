"""Engine three: invoice intake and three-way matching (invoice, purchase order, goods receipt).

    extract     PDF (text layer) or structured JSON -> Invoice, every field with its origin and
                where on the page it came from; bank details are masked at the door
    validate    deterministic arithmetic: line extensions, subtotal, tax (only under a known rule), total
    matching    purchase-order and receipt matching, header and line level, under explicit tolerances
    duplicates  exact and possible duplicates, beyond the invoice number alone
    controls    vendor bank-detail changes against a trusted baseline; eligibility, never approval
    engine      one invoice in, one outcome out, with exceptions and separate status dimensions
    service     persistence, corrections that keep the original, reviewer decisions, audit trail

This software never approves an invoice, never pays one, and never changes vendor master data.
"""
