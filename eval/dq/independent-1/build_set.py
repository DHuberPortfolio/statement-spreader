"""Build the independent DQ test set (portal.csv, erp.xlsx, previous.csv, po.csv, truth.json).

All names, tax ids, bank accounts and routing numbers are invented. Labels are assigned by hand per row.
"""
import csv, json, os, random, difflib, datetime, re, sys
import openpyxl

OUT = os.path.dirname(os.path.abspath(__file__))  # this folder
os.makedirs(OUT, exist_ok=True)
rng = random.Random(20261024)
NBSP = "\u00a0"

used = set()

def uniq(fn):
    while True:
        v = fn()
        if v not in used:
            used.add(v)
            return v

def ein():
    return uniq(lambda: f"{rng.randint(10, 98)}-{rng.randint(0, 9999999):07d}")

def acct(n=None):
    n = n or rng.choice([10, 11, 12])
    return uniq(lambda: str(rng.randint(1, 9)) + "".join(str(rng.randint(0, 9)) for _ in range(n - 1)))

def aba_ok(s):
    if not re.fullmatch(r"\d{9}", s):
        return False
    d = [int(c) for c in s]
    return (3 * (d[0] + d[3] + d[6]) + 7 * (d[1] + d[4] + d[7]) + (d[2] + d[5] + d[8])) % 10 == 0

def aba(lead_zero=None):
    def make():
        first = "0" if lead_zero else str(rng.randint(1, 3)) if lead_zero is False else rng.choice("0123")
        body = first + "".join(str(rng.randint(0, 9)) for _ in range(7))
        d = [int(c) for c in body]
        s = 3 * (d[0] + d[3] + d[6]) + 7 * (d[1] + d[4] + d[7]) + (d[2] + d[5])
        return body + str((-s) % 10)
    v = uniq(make)
    assert aba_ok(v)
    return v

def bad_aba():
    v = aba(lead_zero=False)
    bad = v[:8] + str((int(v[8]) + 3) % 10)
    assert not aba_ok(bad)
    return bad

CANON = ["vendor_id", "name", "aliases", "tax_id", "tax_rate", "bank_account", "routing_number", "status",
         "country", "email", "currency", "payment_terms_days", "onboarded_date"]

PORTAL_COLS = ["Supplier ID", "Supplier Name", "Also Known As", "EIN", "Sales Tax %", "Bank Acct", "ABA", "Status",
               "Country", "Contact Email", "Terms (days)", "Onboarded"]
ERP_COLS = ["VENDOR_NO", "VENDOR_NAME", "ALT_NAMES", "TAX_ID", "VAT_RATE", "BANK_ACCOUNT", "ROUTING", "STAT", "CTRY",
            "EMAIL", "CCY", "PAY_TERMS", "CREATED"]
P_MAP = dict(zip(CANON[:10] + ["payment_terms_days", "onboarded_date"], PORTAL_COLS))
P_MAP = {"vendor_id": "Supplier ID", "name": "Supplier Name", "aliases": "Also Known As", "tax_id": "EIN",
         "tax_rate": "Sales Tax %", "bank_account": "Bank Acct", "routing_number": "ABA", "status": "Status",
         "country": "Country", "email": "Contact Email", "payment_terms_days": "Terms (days)",
         "onboarded_date": "Onboarded"}
E_MAP = dict(zip(CANON, ERP_COLS))
P_STATUS = {"active": "A", "inactive": "I", "blocked": "B"}
P_COUNTRY = {"US": "USA", "CA": "Canada", "GB": "United Kingdom", "DE": "Germany", "FR": "France", "MX": "Mexico"}
E_STATUS = {"active": "ACTIVE", "inactive": "INACTIVE", "blocked": "HOLD"}

def vendor(vid, name, country="US", status="active", tax=None, rate="", bank=None, routing=None, email=None,
           terms=30, date="2022-03-15", aliases="", currency="USD"):
    """Canonical record. tax/bank/routing: None = generate (US) / '' = empty."""
    if tax is None:
        tax = ein() if country == "US" else ""
    if bank is None:
        bank = acct() if country == "US" else ""
    if routing is None:
        routing = aba() if bank and country == "US" else ""
    if email is None:
        slug = re.sub(r"[^a-z]", "", name.lower())[:12] or "vendor"
        email = f"ap@{slug}.example.com"
    return {"vendor_id": vid, "name": name, "aliases": aliases, "tax_id": tax, "tax_rate": rate,
            "bank_account": bank, "routing_number": routing, "status": status, "country": country,
            "email": email, "currency": currency, "payment_terms_days": "" if terms is None else str(terms),
            "onboarded_date": date}

def portal_raw(c):
    r = {}
    for f, col in P_MAP.items():
        v = c[f]
        if f == "tax_rate" and v != "":
            v = f"{float(v) * 100:g}"
        elif f == "status":
            v = P_STATUS[v]
        elif f == "country":
            v = P_COUNTRY.get(v, v)
        elif f == "onboarded_date" and v:
            d = datetime.date.fromisoformat(v)
            v = d.strftime("%m/%d/%Y")
        r[col] = v
    return r

def erp_raw(c):
    r = {}
    for f, col in E_MAP.items():
        v = c[f]
        if f == "aliases":
            v = v.replace(";", "|")
        elif f == "status":
            v = E_STATUS[v]
        elif f == "payment_terms_days" and v != "":
            v = f"NET{v}"
        r[col] = v
    return r

truth = []
prev = []

def add_prev(c, **over):
    p = dict(c)
    p.update(over)
    prev.append(p)

# ------------------------------------------------------------------ portal.csv
portal_rows = []

def P(c, expect, case, hint, over=None, in_prev=True, prev_over=None):
    raw = portal_raw(c)
    if over:
        raw.update(over)
    portal_rows.append(raw)
    truth.append({"file": "portal.csv", "row": len(portal_rows) + 1, "expect": expect, "codes_hint": hint,
                  "case": case, "_vid": c["vendor_id"]})
    if in_prev:
        add_prev(c, **(prev_over or {}))
    return c

# --- valid rows
v = vendor("V1001", "Cardinal Bay Industrial Supply", rate="0.0825", date="2021-06-01",
           aliases="Cardinal Bay Supply;CBIS")
P(v, "accepted", "clean_us", "Clean US vendor, unchanged from snapshot")
v = vendor("V1002", "Hollins Creek Lumber", date="2020-11-09")
P(v, "accepted", "ein_without_hyphen", "EIN given as 9 digits; ein normalisation gives the snapshot's NN-NNNNNNN, so no change",
  over={"EIN": v["tax_id"].replace("-", "")})
v = vendor("V1003", "Tamsin Ridge Fabrication", routing=aba(lead_zero=True), date="2019-02-28", rate="0.06")
P(v, "accepted", "routing_leading_zero_kept", "Routing starts with 0 (kept as text in CSV and in previous.csv); unchanged")
v = vendor("V1004", "Prairie Lantern Outfitters", country="CA", date="2023-01-17")
P(v, "accepted", "ca_no_tax_no_bank", "Canadian vendor: no EIN and no bank details are both allowed outside the US")
v = vendor("V1005", "Thornbury Office Interiors Ltd", country="GB", tax="GB 274 5519 08", bank="40417726",
           date="2022-08-03")
P(v, "accepted", "gb_vat_bank_no_routing", "UK vendor: VAT number printed with spaces, 8-digit account, no ABA (rule only for US)", in_prev=False)
v = vendor("V1006", "Müller & Söhne Präzisionsteile GmbH", country="DE", tax="DE318840275", date="2021-10-12")
P(v, "accepted", "accented_name_de", "German umlauts and ampersand in name; non-US tax id as printed", in_prev=False)
v = vendor("V1007", "Atelier Côté Lumière SARL", country="FR", tax="FR40 512834901", date="2023-05-22")
P(v, "accepted", "accented_name_fr", "French vendor, accented name, FR VAT id, no bank")
v = vendor("V1008", "Grupo Herrera Peña S.A. de C.V.", country="MX", tax="HEPG850101AB1", date="2022-12-01",
           terms=45)
P(v, "accepted", "mx_rfc_punctuated_name", "Mexican vendor with RFC tax id and dotted legal suffix")
v = vendor("V1009", "Quillfeather Stationers", email="ACCOUNTS.PAYABLE@QUILLFEATHER.EXAMPLE.COM", date="2020-04-30")
P(v, "accepted", "email_capitals", "E-mail in capitals is still a valid address")
v = vendor("V1010", "Oxbow Courier Services", terms=0, date="2024-02-29")
P(v, "accepted", "zero_terms_leap_day", "Payment terms 0 (cash on delivery) is within min 0; onboarded on a leap day")
v = vendor("V1011", "Blue Heron Paper Co", date="2018-07-07")
P(v, "accepted", "odd_spacing", "Leading/trailing/double spaces in name collapse to the snapshot name",
  over={"Supplier Name": "  Blue  Heron   Paper Co "})
v = vendor("V1012", "Marlow Engineering Works", date="2022-01-10")
P(v, "accepted", "nbsp_in_id_and_name", "Non-breaking spaces: trailing one on the id, one inside the name; trimming/collapsing fixes both",
  over={"Supplier ID": "V1012" + NBSP, "Supplier Name": "Marlow" + NBSP + "Engineering Works"})
v = vendor("V1013", "Sagebrush Analytical Labs", date="2023-09-05")
P(v, "accepted", "lowercase_codes", "Status 'a' and country 'usa' map case-insensitively",
  over={"Status": "a", "Country": "usa"})
v = vendor("V1014", "Kittering Pump & Valve", date="2023-04-05")
P(v, "accepted", "date_no_leading_zeros", "Date 4/5/2023 is valid %m/%d/%Y without zero padding",
  over={"Onboarded": "4/5/2023"})
v = vendor("V1015", "Larkspur Catering Group", status="inactive", email="", date="2017-03-21")
P(v, "accepted", "inactive_no_email", "Contact rule applies to active vendors only; inactive with no e-mail is fine")
v = vendor("V1016", "Redfern Scaffold Hire", status="blocked", date="2019-12-12")
P(v, "accepted", "blocked_vendor", "Status B = blocked is an allowed value; a blocked vendor is still a valid master record")
v = vendor("V1017", "Juniper Hollow Software", bank="", routing="", date="2025-01-06")
P(v, "accepted", "no_bank_new_vendor", "No bank details at all (pays by card); new vendor, not in snapshot", in_prev=False)
v = vendor("V1018", "Meridian Valve Co", date="2020-02-02")
P(v, "accepted", "similar_name_different_ein_a", "Similar to 'Meridian Valve Corp' (same country) but both EINs filled and different")
v = vendor("V1019", "Meridian Valve Corp", date="2021-03-03")
P(v, "accepted", "similar_name_different_ein_b", "Similar to 'Meridian Valve Co' but both EINs filled and different")
v = vendor("V1020", "Copperline Electrical Contractors", rate="0.000825", date="2022-06-14")
P(v, "accepted", "tax_rate_fraction_in_percent_column", "Sales Tax % typed as 0.0825 -> 0.000825 after the 0.01 scale; within 0..0.25 so passes (real-world error the config cannot see)",
  over={"Sales Tax %": "0.0825"})
v = vendor("V1021", "Westbrook Janitorial Supply", date="2021-08-19")
P(v, "accepted", "lowercase_vendor_id", "Supplier ID 'v1021' upper-cases to V1021", over={"Supplier ID": "v1021"})
v = vendor("V1022", "Ironwood Pallet Recyclers", bank="441022873391", date="2020-10-01")
P(v, "accepted", "bank_with_dashes_unchanged", "Bank account written 4410-2287-3391; digits_only gives the snapshot's 441022873391, so no change",
  over={"Bank Acct": "4410-2287-3391"})
v = vendor("V1023", "Halcyon Print & Sign", date="2019-05-05")
P(v, "accepted", "rename_only", "Name changed since snapshot (rebrand); name is not change-controlled",
  prev_over={"name": "Halcyon Printing Services"})
v = vendor("V1024", "Ferncastle Plumbing Supply", status="inactive", date="2018-09-09")
P(v, "accepted", "status_change_only", "Status went active -> inactive since snapshot; status is not change-controlled",
  prev_over={"status": "active"})

# --- reject rows
v = vendor("V1025", "Stonegate Concrete Forms", tax="", date="2022-02-22")
P(v, "rejected", "us_missing_ein", "us_vendor_needs_ein: US vendor with empty EIN", in_prev=False)
v = vendor("V1026", "Pinebrook Signage", tax="61-834402", date="2023-03-30")
P(v, "rejected", "us_ein_8_digits", "us_vendor_needs_ein pattern: EIN has only 8 digits", in_prev=False)
v = vendor("V1027", "Garnet Hill Freightways", routing="", date="2021-11-11")
P(v, "rejected", "us_bank_without_routing", "us_bank_needs_routing: account present, ABA empty", in_prev=False)
v = vendor("V1028", "Ashcombe Tool & Die", routing=bad_aba(), date="2020-07-15")
P(v, "rejected", "aba_bad_checksum", "ABA has 9 digits but fails the checksum", in_prev=False)
v = vendor("V1029", "Maplecrest Seed Co", country="CA", bank="", routing=aba(), date="2022-04-04")
P(v, "rejected", "routing_without_account", "routing_needs_account: ABA present, account empty", in_prev=False)
v = vendor("V1030", "Calder Point Marine", bank="452381907716", date="2019-09-30")
P(v, "rejected", "bank_scientific_notation", "Bank Acct '4.52382E+11' is Excel scientific notation (digits lost); not a readable account. digits_only would give 45238211 which fits the pattern, and it also differs from the snapshot (change control) so at minimum review",
  over={"Bank Acct": "4.52382E+11"})
v = vendor("V1031", "Bellwether Data Cabling", date="2023-04-15")
P(v, "rejected", "date_iso_in_portal", "Onboarded '2023-04-15' is not %m/%d/%Y (portal's only format)",
  over={"Onboarded": "2023-04-15"}, in_prev=False)
v = vendor("V1032", "Cobblestone Event Rentals", date="2023-07-17")
P(v, "rejected", "date_excel_serial_text", "Onboarded '45124' is an Excel serial number written as text in a CSV",
  over={"Onboarded": "45124"}, in_prev=False)
v = vendor("V1033", "Driftwood Kitchen Equipment", date="2023-04-13")
P(v, "rejected", "date_day_month_swapped", "Onboarded '13/04/2023': month 13 under %m/%d/%Y",
  over={"Onboarded": "13/04/2023"}, in_prev=False)
v = vendor("V1034", "Everly Lane Florists", email="(555) 014-2290", date="2022-05-05")
P(v, "rejected", "phone_in_email", "Contact Email holds a phone number", in_prev=False)
v = vendor("V1035", "Foxglove Medical Disposables", rate="0.30", date="2021-01-25")
P(v, "rejected", "tax_rate_over_max", "Sales Tax % 30 -> 0.30 > max 0.25", in_prev=False)
v = vendor("V1036", "Granite Falls Asphalt", date="2020-08-08")
P(v, "rejected", "terms_text_in_portal", "Terms (days) 'Net 30': NET stripping is configured for the ERP only, so not an integer",
  over={"Terms (days)": "Net 30"}, in_prev=False)
v = vendor("V1037", "Hanamura Precision Optics", country="JP", tax="", bank="", date="2023-10-02")
P(v, "rejected", "country_not_allowed", "Country 'Japan' is not in value_maps and JP is not an allowed country",
  over={"Country": "Japan"}, in_prev=False)
v = vendor("", "Unnamed Import Row", date="2024-01-08")
P(v, "rejected", "missing_vendor_id", "Supplier ID empty (required)", in_prev=False)
v = vendor("V1040", "", date="2024-01-09", email="ap@v1040.example.com")
P(v, "rejected", "missing_name", "Supplier Name empty (required)", in_prev=False)
v = vendor("V1041", "Rheinfeld Verpackung AG", country="DE", tax="DE291104738", bank="DE12 3456 7890 1234 5678 90",
           date="2022-09-19")
P(v, "rejected", "iban_in_account", "Bank Acct holds a German IBAN; digits_only leaves 20 digits > 17 allowed by the pattern", in_prev=False)
v = vendor("V12", "Lowfield Garden Centre", date="2021-02-14")
P(v, "rejected", "vendor_id_pattern", "Supplier ID 'V12' has 2 digits; pattern needs V + 3-8 digits", in_prev=False)

# --- review rows
v = vendor("V1044", "Northcote Asset Recovery", email="", date="2022-11-30")
P(v, "review", "active_no_email", "active_vendor_needs_contact (severity review): active, no e-mail")
v = vendor("V1045", "Oakhurst Commercial Laundry", date="2020-03-03")
P(v, "review", "bank_account_changed", "change_control: bank_account differs from snapshot (routing same)",
  prev_over={"bank_account": acct()})
v = vendor("V1046", "Pellston Hydraulics", date="2019-04-18")
P(v, "review", "routing_changed", "change_control: routing_number differs from snapshot (account same)",
  prev_over={"routing_number": aba()})
v = vendor("V1047", "Quarry Lane Stoneworks", date="2018-12-03")
P(v, "review", "tax_id_changed", "change_control: tax_id differs from snapshot",
  prev_over={"tax_id": ein()})
shared_tax = ein()
v = vendor("V1048", "Rosemoor Facility Services", tax=shared_tax, date="2021-05-17")
P(v, "review", "same_tax_id_a", "same_tax_id with V1049 (V1049 writes it without the hyphen)", in_prev=False)
v = vendor("V1049", "RFS Building Maintenance", tax=shared_tax, date="2024-06-11")
P(v, "review", "same_tax_id_b", "same_tax_id with V1048 after ein normalisation of '%s'" % shared_tax.replace("-", ""),
  over={"EIN": shared_tax.replace("-", "")}, in_prev=False)
sh_acct, sh_rt = acct(11), aba()
v = vendor("V1050", "Sutter Valley Produce", bank=sh_acct, routing=sh_rt, date="2020-06-06")
P(v, "review", "shared_bank_a", "shared_bank_account with V1051 (same account+routing)", in_prev=False)
v = vendor("V1051", "Tidewater Fresh Foods", bank=sh_acct, routing=sh_rt, date="2024-08-21")
P(v, "review", "shared_bank_b", "shared_bank_account with V1050; account written with dashes, same digits",
  over={"Bank Acct": f"{sh_acct[:4]}-{sh_acct[4:8]}-{sh_acct[8:]}"}, in_prev=False)
v = vendor("V1052", "Thistledown Textiles Ltd", country="GB", tax="GB 391 2284 55", date="2019-08-08")
P(v, "review", "similar_name_one_tax_missing_a", "similar_name with V1053 (GB); V1053 has no tax id so the pair is not 'both filled and different'", in_prev=False)
v = vendor("V1053", "Thistledown Textile Ltd", country="GB", tax="", date="2024-09-02")
P(v, "review", "similar_name_one_tax_missing_b", "similar_name with V1052 (GB); no tax id here", in_prev=False)
v = vendor("V1054", "@Home Interiors Studio", date="2023-02-27")
P(v, "review", "formula_prefix_name", "Name starts with '@' (spreadsheet-formula risk), though it may be the real trading name", in_prev=False)
v = vendor("V1055", "Ulverston Cable & Wire", aliases='=HYPERLINK("http://ulverston.example.com/pay","Update bank")',
           date="2022-10-10")
P(v, "review", "formula_in_aliases", "Also Known As starts with '=' (formula injection)", prev_over={"aliases": ""})
v = vendor("V1056", "Vantage Hill Couriers", date="2021-07-07")
P(v, "review", "key_conflict_a", "V1056 appears twice with different e-mail and terms", in_prev=False)
P(dict(v, email="billing@vantagehillcouriers.example.com", payment_terms_days="45"), "review", "key_conflict_b",
  "Second V1056 row with different content", in_prev=False)
v = vendor("V1058", "Whitlock Brothers Hauling", date="2020-01-20")
P(v, "accepted", "exact_dup_first", "First of two V1058 rows with identical canonical content; loaded once (should NOT be flagged same_tax_id/shared_bank against its own copy)")
P(v, "duplicate", "exact_dup_second", "Same V1058 content; differs only in id case, status code case and spacing, which normalise away",
  over={"Supplier ID": " v1058", "Status": "a", "Supplier Name": "Whitlock Brothers  Hauling "}, in_prev=False)
v = vendor("V1060", "Yarrow Point Landscaping", bank="", routing="", date="2019-10-31")
P(v, "review", "bank_removed_vs_snapshot", "change_control: snapshot had account+routing, export has none (removal treated as a change)",
  prev_over={"bank_account": acct(), "routing_number": aba()})
v = vendor("V1061", "Zephyr Ridge Apparel", email="", routing=bad_aba(), date="2023-12-12")
P(v, "rejected", "review_and_reject", "Active without e-mail (review) AND ABA checksum fails (reject) -> rejected", in_prev=False)

# ------------------------------------------------------------------ erp.xlsx
erp_rows = []

def E(c, expect, case, hint, over=None, in_prev=True, prev_over=None):
    raw = erp_raw(c)
    if over:
        raw.update(over)
    erp_rows.append(raw)
    truth.append({"file": "erp.xlsx", "row": len(erp_rows) + 1, "expect": expect, "codes_hint": hint,
                  "case": case, "_vid": c["vendor_id"]})
    if in_prev:
        add_prev(c, **(prev_over or {}))
    return c

v = vendor("V2001", "Ambergate Fluid Power", rate="0.0725", date="2021-04-12", aliases="Ambergate FP")
E(v, "accepted", "clean_erp_us", "Clean ERP US vendor, NET30, unchanged")
v = vendor("V2002", "Kranich Antriebstechnik GmbH", country="DE", tax="DE811249307", rate="0.19", currency="EUR",
           date="2022-04-15", terms=60)
E(v, "accepted", "de_eur_dotted_date", "German vendor, EUR, VAT 0.19, date '15.04.2022' in the ERP's %d.%m.%Y format",
  over={"CREATED": "15.04.2022"}, in_prev=False)
v = vendor("V2003", "Pennywhistle Catering Ltd", country="GB", tax="GB 802 1187 30", rate="0.2", currency="GBP",
           bank="20714456", date="2020-09-01", terms=60)
E(v, "accepted", "gb_lowercase_ccy_net_space", "CCY 'gbp' upper-cases; PAY_TERMS 'NET 60' with a space strips to 60",
  over={"CCY": "gbp", "PAY_TERMS": "NET 60"}, in_prev=False)
v = vendor("V2004", "Larchmont Industrial Coatings", bank="738190245561", date="2019-03-14")
E(v, "accepted", "bank_number_cell_intact", "BANK_ACCOUNT stored as a NUMBER cell (12 digits, exact); must read as 738190245561 not 738190245561.0",
  over={"BANK_ACCOUNT": 738190245561})
rt5 = aba(lead_zero=False)
v = vendor("V2005", "Mossbank Electrical Wholesale", routing=rt5, date="2020-05-25")
E(v, "accepted", "routing_number_cell_no_leading_zero", "ROUTING stored as a NUMBER cell; it starts with 1-3 so nothing was lost",
  over={"ROUTING": int(rt5)})
v = vendor("V2006", "Nettlebed Office Furniture", date="2023-08-30")
E(v, "accepted", "created_true_date_cell", "CREATED is a real Excel date cell (datetime), not text",
  over={"CREATED": datetime.datetime(2023, 8, 30)})
v = vendor("V2007", "Orchard Gate Packaging", aliases="OGP;Orchard Gate Pkg Inc", date="2018-06-18")
E(v, "accepted", "alt_names_pipe", "ALT_NAMES 'OGP|Orchard Gate Pkg Inc' -> 'OGP;Orchard Gate Pkg Inc' via replace")
v = vendor("V2008", "Portage Bay Seafoods", country="CA", status="blocked", currency="CAD", date="2021-12-01",
           email="")
E(v, "accepted", "hold_maps_blocked", "STAT HOLD -> blocked; Canadian, CAD, no tax id/bank; no e-mail fine because not active")
v = vendor("V2009", "Distribuidora Núñez y Asociados", country="MX", tax="DNA990312QX4", currency="MXN",
           date="2022-02-16")
E(v, "accepted", "mx_accented_mxn", "Mexican vendor, accented name, MXN")
v = vendor("V2010", "L'Atelier d'Écriture Fournitures", country="FR", tax="FR83 404833048", currency="EUR",
           date="2023-03-01", rate="0.2")
E(v, "accepted", "fr_apostrophes", "French name with apostrophes and accents; EUR")
v = vendor("V2011", "Quenby Tooling Partners", terms=0, date="2022-07-07")
E(v, "accepted", "net0", "PAY_TERMS 'NET0' -> 0 days")
v = vendor("V2012", "Rushmere Abrasives", terms=45, date="2021-09-09")
E(v, "accepted", "terms_number_cell", "PAY_TERMS is a NUMBER cell 45 (no NET prefix)", over={"PAY_TERMS": 45})
v = vendor("V2013", "Saltmarsh Uniform Co", status="inactive", email="", date="2017-01-31")
E(v, "accepted", "inactive_no_email_erp", "INACTIVE with no e-mail: contact rule is for active only")
v = vendor("V2014", "Tanglewood Event Staffing", currency="", date="2024-03-18")
E(v, "accepted", "ccy_blank", "CCY blank: currency is optional and the ERP source has no default")
v = vendor("V2015", "Underhill Steel Stockholders", date="2019-11-11")
E(v, "accepted", "erp_ein_no_hyphen", "TAX_ID 9 digits; normalises to snapshot's NN-NNNNNNN",
  over={"TAX_ID": v["tax_id"].replace("-", "")})
v = vendor("V2016", "Verity Lab Instruments", date="2020-12-20", email="orders@veritylab.example.com")
E(v, "accepted", "trailing_spaces", "Trailing spaces on name and e-mail; trimmed",
  over={"VENDOR_NAME": "Verity Lab Instruments   ", "EMAIL": "orders@veritylab.example.com  "})
v = vendor("V2017", "Wexcombe Fasteners", date="2022-10-03")
E(v, "accepted", "erp_id_lower_padded", "VENDOR_NO ' v2017 ' trims and upper-cases", over={"VENDOR_NO": " v2017 "})
v = vendor("V2018", "Yelverton Safety Gear", date="2023-04-05")
E(v, "accepted", "dotted_date_low_day", "CREATED '05.04.2023' only fits %d.%m.%Y -> 5 April 2023 (not ambiguous under the ERP's formats)",
  over={"CREATED": "05.04.2023"})
v = vendor("V2019", "Northgate Fasteners", date="2024-04-22")
E(v, "accepted", "same_name_other_country_us", "Same name as V2020 but V2020 is in CA (block_on country)", in_prev=False)
v = vendor("V2020", "Northgate Fasteners", country="CA", currency="CAD", date="2024-05-06")
E(v, "accepted", "same_name_other_country_ca", "Same name as V2019 (US); different country, so no similar_name check", in_prev=False)
v = vendor("V2021", "Zennor Ceramics", rate="0", date="2021-02-02")
E(v, "accepted", "vat_zero_number", "VAT_RATE is a NUMBER cell 0", over={"VAT_RATE": 0})

# rejects
rt22 = aba(lead_zero=True)
v = vendor("V2022", "Abbotsford Rail Services", routing=rt22, date="2020-01-15")
E(v, "rejected", "routing_lost_leading_zero", f"ROUTING stored as NUMBER {int(rt22)} (8 digits); Excel dropped the leading 0 of {rt22}. Not a 9-digit ABA. Snapshot has the 9-digit value",
  over={"ROUTING": int(rt22)})
v = vendor("V2023", "Brackenfield Waste Solutions", date="2023-04-15")
E(v, "rejected", "date_us_format_in_erp", "CREATED '04/15/2023' is not %Y-%m-%d or %d.%m.%Y", over={"CREATED": "04/15/2023"},
  in_prev=False)
v = vendor("V2024", "Coldharbour Refrigeration", date="2023-07-16")
E(v, "rejected", "date_serial_number_cell", "CREATED is a plain NUMBER cell 45123 (date serial without date format)",
  over={"CREATED": 45123}, in_prev=False)
v = vendor("V2025", "Dunmore Glass & Glazing", country="GB", tax="GB 655 0193 27", currency="GBP", date="2022-03-03")
E(v, "rejected", "vat_percent_in_fraction_col", "VAT_RATE NUMBER 20 (percent typed into a fraction column) > max 0.25",
  over={"VAT_RATE": 20}, in_prev=False)
v = vendor("V2026", "Elmstead Security Patrols", date="2021-06-30")
E(v, "rejected", "status_unknown", "STAT 'SUSPENDED' is not in value_maps nor an allowed status", over={"STAT": "SUSPENDED"},
  in_prev=False)
v = vendor("V2027", "Fallowfield Agronomy", terms=150, date="2022-08-08")
E(v, "rejected", "terms_over_max", "PAY_TERMS NET150 -> 150 > max 120", in_prev=False)
v = vendor("V2028", "Goldcrest Robotics", currency="JPY", date="2023-01-11")
E(v, "rejected", "ccy_not_allowed", "CCY JPY not an allowed currency", in_prev=False)
v = vendor("V2029", "Harrowgate Logistics", date="2020-04-04")
E(v, "rejected", "terms_free_text", "PAY_TERMS '30 days' is not an integer after NET stripping", over={"PAY_TERMS": "30 days"},
  in_prev=False)
v = vendor("V2030", "Inglenook Hearth Supply", email="ap.inglenookhearth.example.com", date="2021-03-23")
E(v, "rejected", "email_no_at", "EMAIL has no '@'", in_prev=False)
long_name = ("Consolidated Midwestern Agricultural Equipment Leasing, Servicing, Parts Distribution "
             "and Field Support Cooperative Association")
assert len(long_name) > 120, len(long_name)
v = vendor("V2031", long_name, date="2019-07-19", email="ap@cmaels.example.com")
E(v, "rejected", "name_too_long", f"VENDOR_NAME is {len(long_name)} chars > max_length 120", in_prev=False)
v = vendor("V2032", "Jessamine Dental Supply", country="", date="2022-12-12")
E(v, "rejected", "country_blank", "CTRY empty (required)", in_prev=False)
v = vendor("V2033", "Kelmscott Bindery", bank="670912884105", date="2018-04-01")
E(v, "rejected", "bank_scientific_text", "BANK_ACCOUNT text '6.70913E+11' (scientific notation pasted as text); digits lost. digits_only would give 67091311 which fits the pattern; not in snapshot so change control cannot catch it",
  over={"BANK_ACCOUNT": "6.70913E+11"}, in_prev=False)

# reviews
v = vendor("V2034", "Lyndhurst Medical Gases", date="2019-02-19")
E(v, "review", "erp_bank_changed", "change_control: bank_account differs from snapshot", prev_over={"bank_account": acct()})
v = vendor("V2035", "Marchwood Timber Merchants", date="2018-10-10")
E(v, "review", "erp_tax_changed", "change_control: tax_id differs from snapshot", prev_over={"tax_id": ein()})
sh2a, sh2r = acct(12), aba()
v = vendor("V2036", "Nightingale Home Health", bank=sh2a, routing=sh2r, date="2022-05-30")
E(v, "review", "erp_shared_bank_a", "shared_bank_account with V2037", in_prev=False)
v = vendor("V2037", "Northfield Care Staffing", bank=sh2a, routing=sh2r, date="2024-07-01")
E(v, "review", "erp_shared_bank_b", "shared_bank_account with V2036; ROUTING written as text with a trailing space",
  over={"ROUTING": sh2r + " "}, in_prev=False)
v = vendor("V2038", "Ottery Signal Systems", email="", date="2023-06-06")
E(v, "review", "erp_active_no_email", "active_vendor_needs_contact (review)", in_prev=False)
v = vendor("V2039", "+Plus Laboratory Supply", date="2023-09-29")
E(v, "review", "formula_prefix_plus", "VENDOR_NAME starts with '+' and is not a number (formula risk)", in_prev=False)
v = vendor("V2040", "Pevensey Mechanical", date="2021-01-04")
E(v, "review", "erp_key_conflict_a", "V2040 twice with different bank accounts", in_prev=False)
E(dict(v, bank_account=acct(), routing_number=v["routing_number"]), "review", "erp_key_conflict_b",
  "Second V2040 row, different BANK_ACCOUNT", in_prev=False)
v = vendor("V2042", "Ravenglass Survey Partners", date="2020-08-26")
E(v, "accepted", "erp_exact_dup_first", "First of two identical V2042 rows")
E(v, "duplicate", "erp_exact_dup_second", "Second V2042 row: identical after normalisation (STAT 'active' lowercase maps to active, NET 30 with a space)",
  over={"STAT": "active", "PAY_TERMS": "NET 30"}, in_prev=False)
shared_tax2 = ein()
v = vendor("V2044", "Saxby Office Cleaning", tax=shared_tax2, date="2021-10-21")
E(v, "review", "erp_same_tax_a", "same_tax_id with V2045", in_prev=False)
v = vendor("V2045", "Saxby Facilities Group", tax=shared_tax2, date="2024-02-12")
E(v, "review", "erp_same_tax_b", "same_tax_id with V2044 (names differ enough not to matter)", in_prev=False)
v = vendor("V2046", "=Tolworth Lifts", email="tolworth lifts at example dot com", date="2022-02-22")
E(v, "rejected", "formula_and_bad_email", "Name starts with '=' (review) and EMAIL invalid (reject) -> rejected", in_prev=False)

# ------------------------------------------------------------------ write vendor files
with open(os.path.join(OUT, "portal.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=PORTAL_COLS)
    w.writeheader()
    w.writerows(portal_rows)

wb = openpyxl.Workbook()
ws = wb.active
ws.title = "VENDOR_EXPORT"
ws.append(ERP_COLS)
for r in erp_rows:
    row = []
    for col in ERP_COLS:
        val = r[col]
        row.append(None if val == "" else val)
    ws.append(row)
for cell in ws["M"][1:]:
    if isinstance(cell.value, datetime.datetime):
        cell.number_format = "yyyy-mm-dd"
# Every string cell stays a string; force text format on text cells for realism
for row in ws.iter_rows(min_row=2):
    for cell in row:
        if isinstance(cell.value, str):
            cell.number_format = "@"
wb.save(os.path.join(OUT, "erp.xlsx"))

with open(os.path.join(OUT, "previous.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=CANON)
    w.writeheader()
    for p in prev:
        w.writerow({k: p[k] for k in CANON})

# ------------------------------------------------------------------ po.csv
expect_by_vid = {}
for t in truth:
    vid = t["_vid"]
    expect_by_vid.setdefault(vid, []).append(t["expect"])
all_vendors = {}
for t in truth:
    pass
ACCEPTED = {vid for vid, ex in expect_by_vid.items() if "accepted" in ex and "review" not in ex and vid}
status_of = {}
for p in portal_rows:
    pass

PO_COLS = ["PO_NUMBER", "VENDOR_NO", "PO_STATUS", "CCY", "LINE", "ITEM", "ITEM_DESC", "QTY", "UNIT_PRICE", "GR_REQUIRED"]
ITEMS = {  # code: (desc, price)
    "A-100": ("Nitrile gloves, box of 100", "24.50"),
    "A-110": ("Safety glasses, clear", "112.00"),
    "A-120": ("Marker pens, pack of 12", "8.75"),
    "B-200": ("Hex nut M10, bag", "3.10"),
    "B-210": ("Hydraulic fitting 1/2in", "67.00"),
    "C-300": ("Catering platter, standard", "14.20"),
    "C-310": ("Event buffet service", "980.00"),
    "D-400": ("Cajas de carton, paquete", "45.00"),
    "E-500": ("Gate valve 2in, brass", "210.00"),
    "E-510": ("Ball valve 2in, brass", "199.00"),
    "F-600": ("Floor cleaner concentrate, litre", "18.40"),
    "G-700": ("Pallet hire, sample", "0.00"),
    "H-800": ("Cable tray 3m", "54.00"),
    "H-810": ("Cable ties, bag of 500", "11.90"),
    "J-900": ("Toner cartridge, black", "88.00"),
    "J-910": ("Copy paper, case", "41.25"),
    "K-050": ("Ear defenders", "19.99"),
    "HYD-220": ("Hydraulic pump, gear type", None),
    "CNC-9000": ("CNC vertical machining centre", "48500.00"),
    "VLV-3": ("Check valve 3/4in", None),
    "M-120": ("Lab beaker set", "62.00"),
}
po_rows = []

def L(po, vid, st, ccy, line, item, qty, price=None, gr="yes", expect="accepted", case="clean_line", hint="Clean line",
      desc=None):
    d, p = ITEMS.get(item, ("", None))
    po_rows.append({"PO_NUMBER": po, "VENDOR_NO": vid, "PO_STATUS": st, "CCY": ccy, "LINE": line, "ITEM": item,
                    "ITEM_DESC": d if desc is None else desc, "QTY": qty, "UNIT_PRICE": p if price is None else price,
                    "GR_REQUIRED": gr})
    truth.append({"file": "po.csv", "row": len(po_rows) + 1, "expect": expect, "codes_hint": hint, "case": case,
                  "_vid": vid})

L("PO-6001", "V1001", "O", "USD", "1", "A-100", "10")
L("PO-6001", "V1001", "O", "USD", "2", "A-110", "5")
L("PO-6001", "V1001", "O", "USD", "3", "A-120", "2", gr="no")
L("PO-6002", "V2001", "O", "usd", "1", "B-200", "20", gr="Y", case="ccy_case_mix", hint="CCY 'usd' vs 'USD' on the same PO: equal after upper-casing, so the PO is consistent")
L("PO-6002", "V2001", "O", "USD", "2", "B-210", "4", gr="Y", case="ccy_case_mix", hint="Same PO as previous line; consistent after normalisation")
L("PO-6003", "V2003", "O", "GBP", "1", "C-300", "12", case="gbp_po", hint="GBP PO for an accepted UK vendor")
L("PO-6003", "V2003", "O", "GBP", "2", "C-310", "1", case="gbp_po", hint="GBP PO for an accepted UK vendor")
L("PO-6004", "V2009", "O", "MXN", "1", "D-400", "100", case="mxn_po", hint="MXN PO, accented-name vendor")
L("PO-6005", "V1018", "C", "USD", "1", "E-500", "6", gr="no", case="similar_vendor_a", hint="Vendor V1018 accepted (similar name but different EIN); closed PO")
L("PO-6006", "V1019", "O", "USD", "1", "E-510", "3", case="similar_vendor_b", hint="Vendor V1019 accepted")
L("PO-6007", "v1021", "O", "USD", "1", "F-600", "2.5", case="lower_vendor_decimal_qty", hint="VENDOR_NO 'v1021' upper-cases to an accepted vendor; quantity 2.5 is a valid decimal")
L("PO-6008", "V1058", "O", "USD", "1", "G-700", "1", gr="no", case="zero_price_dup_vendor", hint="Unit price 0.00 allowed (min 0); vendor V1058 accepted once despite its duplicate row")
L("PO-6009", "V1015", "O", "USD", "1", "H-800", "10", expect="review", case="vendor_inactive", hint="Vendor V1015 is in the master but inactive")
L("PO-6009", "V1015", "O", "USD", "2", "H-810", "3", expect="review", case="vendor_inactive", hint="Vendor V1015 is inactive")
L("PO-6010", "V2008", "O", "CAD", "1", "C-300", "4", expect="review", case="vendor_blocked", hint="Vendor V2008 is blocked (HOLD)")
L("PO-6011", "V1044", "O", "USD", "1", "J-900", "2", expect="rejected", case="vendor_held_review", hint="V1044 was held for review, so it is not in the accepted vendor file")
L("PO-6012", "V1025", "O", "USD", "1", "J-910", "8", expect="rejected", case="vendor_rejected", hint="V1025 was rejected (no EIN), not in vendor file")
L("PO-6013", "V9999", "O", "USD", "1", "K-050", "6", expect="rejected", case="vendor_unknown", hint="V9999 does not exist")
for i, vid in enumerate(["V1001", "V1001", "V1002"], 1):
    L("PO-6014", vid, "O", "USD", str(i), ["A-100", "A-120", "J-910"][i - 1], "3", expect="rejected", case="po_mixed_vendor",
      hint="PO-6014 lines disagree on vendor (V1001 vs V1002): every line rejected")
L("PO-6015", "V1004", "O", "USD", "1", "K-050", "10", expect="rejected", case="po_mixed_currency", hint="PO-6015 lines disagree on currency (USD vs CAD)")
L("PO-6015", "V1004", "O", "CAD", "2", "J-910", "2", expect="rejected", case="po_mixed_currency", hint="PO-6015 lines disagree on currency (USD vs CAD)")
L("PO-6016", "V1009", "O", "USD", "1", "J-900", "1", expect="rejected", case="po_mixed_status", hint="PO-6016 lines disagree on status (open vs closed)")
L("PO-6016", "V1009", "C", "USD", "2", "J-910", "4", expect="rejected", case="po_mixed_status", hint="PO-6016 lines disagree on status (open vs closed)")
L("PO-6017", "V1010", "O", "USD", "1", "H-810", "5", case="status_code_variants", hint="PO_STATUS 'O', 'o', 'open' all mean open: PO consistent")
L("PO-6017", "V1010", "o", "USD", "2", "K-050", "2", case="status_code_variants", hint="lowercase 'o' maps case-insensitively to open")
L("PO-6017", "V1010", "open", "USD", "3", "A-120", "1", case="status_code_variants", hint="'open' is already the canonical value")
# outlier group: HYD-220
hyd = [("PO-6018", "V1001", "412.50", "2"), ("PO-6019", "V1002", "409.00", "1"), ("PO-6020", "V2001", "415.00", "3"),
       ("PO-6021", "V2004", "412.50", "1"), ("PO-6023", "V1003", "410.00", "2")]
for po, vid, pr, q in hyd:
    L(po, vid, "O", "USD", "1", "HYD-220", q, price=pr, case="hyd_normal_price", hint="HYD-220 at ~410: normal price within its item group")
L("PO-6022", "V2005", "O", "USD", "1", "HYD-220", "1", price="4125.00", expect="review", case="price_extra_zero",
  hint="HYD-220 at 4125.00 vs ~410 on 5 other lines (10x, factor 8): typed extra zero")
# expensive consistent
for po, vid, q in [("PO-6024", "V1017", "1"), ("PO-6025", "V2011", "1"), ("PO-6026", "V2012", "2"), ("PO-6027", "V1003", "1"),
                   ("PO-6028", "V2016", "1")]:
    L(po, vid, "O", "USD", "1", "CNC-9000", q, gr="yes", case="expensive_consistent", hint="CNC-9000 at 48,500.00 on every line: expensive but consistent")
# min group not reached
L("PO-6029", "V1009", "O", "USD", "1", "VLV-3", "4", price="35.00", case="small_group", hint="VLV-3 has only 3 lines in total")
L("PO-6030", "V1010", "O", "USD", "1", "VLV-3", "6", price="36.00", case="small_group", hint="VLV-3 has only 3 lines in total")
L("PO-6031", "V1001", "O", "USD", "1", "VLV-3", "1", price="350.00", case="outlier_below_min_group",
  hint="VLV-3 at 350 is ~10x the other two, but the item has only 3 lines (< min_group 4), so no outlier check")
L("PO-6032", "V1001", "O", "USD", "1", "A-100", "1,000", expect="rejected", case="qty_thousands_sep", hint="QTY '1,000' with a thousands separator is not a plain decimal")
L("PO-6032", "V1001", "O", "USD", "2", "A-110", "20", case="clean_line", hint="Clean line on the same PO; the bad quantity on line 1 does not spill over")
L("PO-6033", "V2001", "O", "USD", "1", "B-200", "0", expect="rejected", case="qty_zero", hint="QTY 0 < min 0.001")
L("PO-6034", "V2004", "O", "USD", "1", "M-120", "2", price="-12.00", expect="rejected", case="negative_price", hint="UNIT_PRICE -12.00 < min 0")
L("PO-6035", "V2005", "O", "USD", "0", "H-800", "3", expect="rejected", case="line_zero", hint="LINE 0 < min 1")
L("PO-6035", "V2005", "O", "USD", "1", "H-810", "3", case="clean_line", hint="Clean line next to a bad line_no")
L("PO5036", "V2011", "O", "USD", "1", "J-900", "1", expect="rejected", case="po_number_pattern", hint="PO_NUMBER 'PO5036' lacks the hyphen; pattern PO-\\d{3,10}")
L(" po-6037 ", "V2012", "O", "USD", "1", "J-910", "6", case="po_number_lower_padded", hint="' po-6037 ' trims and upper-cases to PO-6037")
L("PO-6038", "V2015", "O", "USD", "1", "K-050", "5", gr="", expect="rejected", case="gr_blank", hint="GR_REQUIRED empty (required bool)")
L("PO-6038", "V2015", "O", "USD", "2", "H-810", "2", gr="maybe", expect="rejected", case="gr_not_bool", hint="GR_REQUIRED 'maybe' is not a boolean")
L("PO-6038", "V2015", "O", "USD", "3", "A-100", "2", gr="N", case="gr_letter_n", hint="GR_REQUIRED 'N' is a common boolean spelling")
L("PO-6039", "V2016", "O", "USD", "1", "M-120", "1", gr="TRUE", case="gr_true_caps", hint="GR_REQUIRED 'TRUE'")
L("PO-6040", "V2017", "O", "US$", "1", "J-900", "2", expect="rejected", case="ccy_symbol", hint="CCY 'US$' is not an allowed currency")
long_desc = ("Replacement assembly kit including housing, gaskets, seals, fasteners, mounting brackets, wiring harness, "
             "control board, user manual, calibration certificate, spare fuses and protective packaging for site storage")
assert len(long_desc) > 200, len(long_desc)
L("PO-6041", "V2018", "O", "USD", "1", "K-050", "1", desc=long_desc, expect="rejected", case="desc_too_long", hint=f"ITEM_DESC {len(long_desc)} chars > max_length 200")
L("PO-6042", "V1012", "O", "USD", "1", "-10MM-SPACER", "50", price="0.85", desc="Spacer 10mm", expect="review", case="formula_prefix_item",
  hint="ITEM '-10MM-SPACER' starts with '-' and is not a number (formula risk)")
L("PO-6042", "V1012", "O", "USD", "2", "H-800", "2", case="clean_line", hint="Clean line on the same PO")
L("PO-6043", "V1013", "O", "USD", "1", "J-910", "3", desc='=HYPERLINK("http://example.com/x","Invoice")', expect="review",
  case="formula_in_desc", hint="ITEM_DESC starts with '=' (formula injection)")
L("PO-6044", "V1014", "O", "USD", "1", "E-500", "2", case="dup_key_first_other", hint="Clean line")
L("PO-6044", "V1014", "O", "USD", "2", "E-510", "2", case="dup_key_first", hint="First of two identical PO-6044/2 rows")
L("PO-6044", "V1014", "O", "USD", "2", "E-510", "2", expect="duplicate", case="dup_key_second", hint="PO-6044 line 2 repeated identically")
L("PO-6045", "V1021", "O", "USD", "1", "F-600", "5", expect="review", case="key_conflict_a", hint="PO-6045 line 1 appears twice with quantity 5 vs 50")
L("PO-6045", "V1021", "O", "USD", "1", "F-600", "50", expect="review", case="key_conflict_b", hint="PO-6045 line 1 second version, quantity 50")
L("PO-6046", "V1022", "O", "USD", "1", "", "3", price="10.00", desc="Misc parts", expect="rejected", case="item_blank", hint="ITEM empty (required)")
L("PO-6047", "V1023", "Z", "USD", "1", "J-900", "1", expect="rejected", case="status_unknown", hint="PO_STATUS 'Z' not in value_maps")
L("PO-6048", "V2042", "O", "USD", "1", "H-800", "4", case="dup_vendor_erp", hint="Vendor V2042 accepted once (its second row was a duplicate)")
L("PO-6049", "V1012", "O", "USD", "1", "J-900", "2", case="nbsp_vendor", hint="Vendor V1012 (its id had a trailing NBSP in the portal) is accepted")
L("PO-6050", "V2013", "C", "USD", "1", "K-050", "12", gr="no", expect="review", case="vendor_inactive_erp", hint="Vendor V2013 inactive")
L("PO-6051", "V1016", "O", "USD", "1", "H-800", "1", expect="review", case="vendor_blocked_portal", hint="Vendor V1016 blocked")
L("PO-6052", "V2036", "O", "USD", "1", "M-120", "2", expect="rejected", case="vendor_held_shared_bank", hint="V2036 held for review (shared bank), not in vendor file")
L("PO-6053", "V12", "O", "USD", "1", "A-120", "2", expect="rejected", case="vendor_invalid_id", hint="V12 was rejected, not in vendor file")
for i, (it, q) in enumerate([("C-300", "24"), ("C-310", "2"), ("A-110", "1")], 1):
    L("PO-6054", "V2002", "O", "EUR", str(i), it, q, case="eur_po", hint="EUR PO for accepted German vendor")
L("PO-6055", "V2010", "O", "EUR", "1", "J-910", "10", case="eur_po_fr", hint="EUR PO for accepted French vendor")
L("PO-6055", "V2010", "O", "EUR", "2", "J-900", "1", case="eur_po_fr", hint="EUR PO for accepted French vendor")
L("PO-6056", "V1006", "X", "USD", "1", "M-120", "3", gr="no", case="cancelled_po", hint="Cancelled (X) PO for accepted German vendor")
L("PO-6057", "V2018", "O", "USD", "1", "K-050", "40", case="clean_line", hint="Clean line")
L("PO-6057", "V2018", "O", "USD", "2", "A-100", "15", case="clean_line", hint="Clean line")
L("PO-6058", "V1022", "O", "USD", "1", "H-810", "20", case="clean_line", hint="Clean line")
L("PO-6058", "V1022", "O", "USD", "2", "H-800", "6", case="clean_line", hint="Clean line")
L("PO-6059", "V2020", "O", "CAD", "1", "K-050", "8", case="cad_po", hint="CAD PO for the Canadian Northgate Fasteners")
L("PO-6060", "V2006", "O", "USD", "1", "J-910", "12", case="clean_line", hint="Clean line")
L("PO-6060", "V2006", "O", "USD", "2", "M-120", "1", case="clean_line", hint="Clean line")

# --- sanity checks on PO labels vs vendor labels
po_accepted_vendors = ACCEPTED
for t in truth:
    if t["file"] != "po.csv":
        continue
    vid = t["_vid"].strip().upper()
    if t["case"] in ("vendor_held_review", "vendor_rejected", "vendor_unknown", "vendor_held_shared_bank", "vendor_invalid_id"):
        assert vid not in po_accepted_vendors, (t, vid)
    else:
        assert vid in po_accepted_vendors, ("PO vendor not accepted", t)

# vendor status for inactive/blocked checks
canon_status = {}
for p in prev:
    canon_status[p["vendor_id"]] = p["status"]
for vid in ["V1015", "V1016", "V2008", "V2013"]:
    assert vid in po_accepted_vendors

# write po.csv
with open(os.path.join(OUT, "po.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=PO_COLS)
    w.writeheader()
    w.writerows(po_rows)

# outlier sanity: no item other than HYD-220 has >=4 lines with >8x spread
from collections import defaultdict
by_item = defaultdict(list)
for r in po_rows:
    try:
        by_item[r["ITEM"].strip().upper()].append(float(r["UNIT_PRICE"]))
    except ValueError:
        pass
for it, ps in by_item.items():
    pos = [p for p in ps if p > 0]
    if len(ps) >= 4 and pos and max(pos) / min(pos) > 8:
        print("SPREAD", it, ps)

# similarity sanity per file/country
def check_sim(rows, idcol, namecol, ctrycol, label):
    norm = []
    for r in rows:
        n = re.sub(r"\s+", " ", str(r[namecol]).replace(NBSP, " ")).strip().lower()
        norm.append((str(r[idcol]).strip().upper(), n, str(r[ctrycol]).strip().lower()))
    for i in range(len(norm)):
        for j in range(i + 1, len(norm)):
            a, b = norm[i], norm[j]
            if a[0] == b[0] or not a[1] or not b[1]:
                continue
            s = difflib.SequenceMatcher(None, a[1], b[1]).ratio()
            if s >= 0.8:
                print(label, "SIM %.3f" % s, a[0], a[1], "|", b[0], b[1], a[2], b[2])
check_sim(portal_rows, "Supplier ID", "Supplier Name", "Country", "portal")
check_sim(erp_rows, "VENDOR_NO", "VENDOR_NAME", "CTRY", "erp")

# cross-file uniqueness of tax ids / banks (excluding designed pairs)
from collections import Counter
def key_counts(field):
    c = Counter()
    for p in [*portal_rows]:
        pass
print("prev rows", len(prev))

# routing validity report
for p in prev:
    if p["routing_number"]:
        assert aba_ok(p["routing_number"]), p

for t in truth:
    t.pop("_vid", None)
with open(os.path.join(OUT, "truth.json"), "w", encoding="utf-8") as f:
    json.dump(truth, f, indent=1, ensure_ascii=False)

cnt = Counter((t["file"], t["expect"]) for t in truth)
for k in sorted(cnt):
    print(k, cnt[k])
print("rows: portal", len(portal_rows), "erp", len(erp_rows), "po", len(po_rows))
