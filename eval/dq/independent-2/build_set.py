# Builds eval/dq/independent-2: an independent, hand-labelled test set for the data-quality gate.
# All names and numbers are invented.
import csv, json, os, random, datetime
from decimal import Decimal

OUT = os.path.dirname(os.path.abspath(__file__))  # this folder
os.makedirs(OUT, exist_ok=True)
rnd = random.Random(20261024)

FIELDS = ["vendor_id", "name", "aliases", "tax_id", "tax_rate", "bank_account", "routing_number", "status",
          "country", "email", "currency", "payment_terms_days", "onboarded_date"]

# ---------------------------------------------------------------- generators
def aba_check(d8):
    d = [int(c) for c in d8]
    s = 3 * (d[0] + d[3] + d[6]) + 7 * (d[1] + d[4] + d[7]) + (d[2] + d[5])
    return str((-s) % 10)

def aba_valid(s):
    if len(s) != 9 or not s.isascii() or not s.isdigit():
        return False
    d = [int(c) for c in s]
    return (3 * (d[0] + d[3] + d[6]) + 7 * (d[1] + d[4] + d[7]) + (d[2] + d[5] + d[8])) % 10 == 0

used = set()
def uniq(f):
    while True:
        v = f()
        if v not in used:
            used.add(v)
            return v

def new_aba(first="0"):
    def f():
        p = first + "".join(rnd.choice("0123456789") for _ in range(7))
        if first == "0":
            p = "0" + rnd.choice("123456789") + p[2:]
        return p + aba_check(p)
    return uniq(f)

def bad_aba():
    good = new_aba()
    return good[:8] + str((int(good[8]) + 3) % 10)

def new_ein():
    return uniq(lambda: f"{rnd.randint(10, 98)}-{rnd.randint(1000000, 9999999)}")

def new_bank(n=None):
    n = n or rnd.choice([10, 11, 12])
    return uniq(lambda: str(rnd.randint(1, 9)) + "".join(rnd.choice("0123456789") for _ in range(n - 1)))

def slug(name):
    s = "".join(ch.lower() if ch.isascii() and ch.isalnum() else "-" for ch in name)
    while "--" in s:
        s = s.replace("--", "-")
    return s.strip("-")[:30].strip("-")

def rdate():
    return datetime.date(2019, 1, 1) + datetime.timedelta(days=rnd.randint(0, 2000))

def canon(vid, name, country="US", **kw):
    c = {k: "" for k in FIELDS}
    c.update(vendor_id=vid, name=name, country=country, status="active",
             email=f"ap@{slug(name)}.example.com", payment_terms_days="30",
             onboarded_date=rdate().isoformat())
    if country == "US":
        c.update(tax_id=new_ein(), tax_rate=rnd.choice(["0.0825", "0.06", "0.07", "", "0.0475"]),
                 bank_account=new_bank(), routing_number=new_aba())
    for k, v in kw.items():
        c[k] = v
    return c

# ---------------------------------------------------------------- row registry
PORTAL_COLS = ["Supplier ID", "Supplier Name", "Also Known As", "EIN", "Sales Tax %", "Bank Acct", "ABA", "Status",
               "Country", "Contact Email", "Terms (days)", "Onboarded"]
ERP_COLS = ["VENDOR_NO", "VENDOR_NAME", "ALT_NAMES", "TAX_ID", "VAT_RATE", "BANK_ACCOUNT", "ROUTING", "STAT", "CTRY",
            "EMAIL", "CCY", "PAY_TERMS", "CREATED"]
P_STATUS = {"active": "A", "inactive": "I", "blocked": "B"}
P_COUNTRY = {"US": "USA", "CA": "Canada", "GB": "United Kingdom", "DE": "Germany", "FR": "France", "MX": "Mexico"}
E_STATUS = {"active": "ACTIVE", "inactive": "INACTIVE", "blocked": "HOLD"}

def pct(rate):
    if rate == "":
        return ""
    return format((Decimal(rate) * 100).normalize(), "f")

def portal_raw(c):
    d = datetime.date.fromisoformat(c["onboarded_date"])
    return {"Supplier ID": c["vendor_id"], "Supplier Name": c["name"], "Also Known As": c["aliases"],
            "EIN": c["tax_id"], "Sales Tax %": pct(c["tax_rate"]), "Bank Acct": c["bank_account"],
            "ABA": c["routing_number"], "Status": P_STATUS[c["status"]], "Country": P_COUNTRY[c["country"]],
            "Contact Email": c["email"], "Terms (days)": c["payment_terms_days"],
            "Onboarded": d.strftime("%m/%d/%Y")}

_erp_date_style = [0]
def erp_raw(c):
    d = datetime.date.fromisoformat(c["onboarded_date"])
    _erp_date_style[0] += 1
    style = _erp_date_style[0] % 3
    created = d.isoformat() if style == 0 else (d.strftime("%d.%m.%Y") if style == 1 else d)
    return {"VENDOR_NO": c["vendor_id"], "VENDOR_NAME": c["name"], "ALT_NAMES": c["aliases"].replace(";", "|"),
            "TAX_ID": c["tax_id"], "VAT_RATE": float(c["tax_rate"]) if c["tax_rate"] != "" else None,
            "BANK_ACCOUNT": c["bank_account"], "ROUTING": c["routing_number"], "STAT": E_STATUS[c["status"]],
            "CTRY": c["country"], "EMAIL": c["email"], "CCY": c["currency"],
            "PAY_TERMS": f"NET{c['payment_terms_days']}" if c["payment_terms_days"] != "" else None,
            "CREATED": created}

rows = {"portal.csv": [], "erp.xlsx": []}
previous = {}          # vendor_id -> canonical record
held_status = {}       # (file,idx) -> status of the held version, for carry-forward

def add(file, c, expect, case, why, raw=None, prev=None, held=None):
    """c: canonical record (what an accepted row normalises to). raw: overrides on the raw export row.
    prev: True -> previous snapshot holds c unchanged; dict -> previous holds c updated with dict."""
    base = portal_raw(c) if file == "portal.csv" else erp_raw(c)
    if file == "erp.xlsx" and c["currency"] == "":
        pass
    base.update(raw or {})
    rows[file].append({"raw": base, "canon": c, "expect": expect, "case": case, "why": why,
                       "held_status": held if held else c["status"]})
    if prev:
        p = dict(c)
        if isinstance(prev, dict):
            p.update(prev)
        previous[c["vendor_id"]] = p

P, E = "portal.csv", "erp.xlsx"

def pc(vid, name, country="US", **kw):   # portal vendors are always USD (source default)
    return canon(vid, name, country, currency="USD", **kw)

# ================================================================= PORTAL
c = pc("V1001", "Northfield Paper Company")
add(P, c, "accepted", "plain_us_vendor_unchanged", "Clean US vendor, identical to the previous snapshot.", prev=True)

c = pc("V1002", "Ironbridge Fabrication LLC")
add(P, c, "accepted", "ein_without_hyphen_matches_previous",
    "EIN exported as 9 bare digits; ein normalisation gives NN-NNNNNNN, equal to the snapshot, so no tax-id change.",
    raw={"EIN": c["tax_id"].replace("-", "")}, prev=True)

c = pc("V1003", "Quarry Lane Electrical Inc", bank_account="004511239987")
add(P, c, "accepted", "bank_hyphens_match_previous",
    "Bank account printed with hyphens (0045-1123-9987); digits_only makes it equal to the snapshot, leading zeros kept.",
    raw={"Bank Acct": "0045-1123-9987"}, prev=True)

c = pc("V1004", "Saltmarsh Marine Supply")
add(P, c, "accepted", "country_long_name_status_lowercase_code",
    "Country 'United States' and status 'a' both translate through the portal value_maps (case-insensitive).",
    raw={"Country": "United States", "Status": "a"}, prev=True)

c = pc("V1005", "Copperleaf Office Furniture")
add(P, c, "accepted", "vendor_id_lowercase_padded",
    "Supplier ID ' v1005 ' trims and upper-cases to V1005, matching the pattern and the snapshot.",
    raw={"Supplier ID": " v1005 "}, prev=True)

c = pc("V1006", "Granite Peak Tool Works")
add(P, c, "accepted", "tab_and_double_space_in_name",
    "Name contains a tab and a double space and a trailing space; whitespace collapses. Name is not change-controlled.",
    raw={"Supplier Name": "Granite\tPeak  Tool Works "}, prev=True)

c = pc("V1007", "Comercializadora Sol del Norte S.A. de C.V.", "MX", tax_id="CSN010315HK8", tax_rate="0.16")
add(P, c, "accepted", "mexican_sa_de_cv_rfc",
    "Mexican vendor, legal suffix S.A. de C.V., RFC tax id (not an EIN, no pattern for MX), 16% tax, no bank details.",
    prev=True)

c = pc("V1008", "Brückner Werkzeugbau GmbH", "DE", tax_id="143/815/08154", tax_rate="0.19")
add(P, c, "accepted", "german_gmbh_umlaut_steuernummer",
    "German GmbH with an umlaut, Steuernummer with slashes, 19% tax, no bank details.", prev=True)

c = pc("V1009", "Thistlewood & Marsh Ltd.", "GB", tax_id="GB 284 7190 35 001", tax_rate="0.2",
       bank_account="41920037")
add(P, c, "accepted", "uk_ltd_bank_without_routing",
    "UK vendor: 8-digit account and no ABA routing is fine outside the US; VAT number with spaces kept as printed.",
    prev=True)

c = pc("V1010", "Ashgrove Catering Services", status="inactive", email="")
add(P, c, "accepted", "inactive_vendor_without_email",
    "No contact e-mail, but the contact rule only applies to active vendors.", prev=True)

c = pc("V1011", "Brightwater Lab Supply", tax_rate="0.25")
add(P, c, "accepted", "tax_rate_at_max_boundary", "Sales Tax % 25 -> 0.25, exactly the maximum.", prev=True)

c = pc("V1012", "Hollins Freight Brokers", tax_rate="0.005", payment_terms_days="120")
add(P, c, "accepted", "terms_at_max_and_tiny_tax",
    "Terms 120 is the maximum; Sales Tax % '0.5' -> 0.005, small but in range.", prev=True)

n120 = "Consolidated Municipal Infrastructure Maintenance and Environmental Remediation Services of the Tri County Region Inc"
n120 = n120 + "." * (120 - len(n120))
assert len(n120) == 120, len(n120)
c = pc("V1013", n120)
add(P, c, "accepted", "name_exactly_120_chars", "Name is exactly 120 characters (max_length 120).")

al = []
i = 0
while True:
    nxt = f"Larchmont Building Products Division {i:02d}"
    if len(";".join(al + [nxt])) > 400:
        break
    al.append(nxt)
    i += 1
alias400 = ";".join(al)
alias400 = alias400 + "X" * (400 - len(alias400))
assert len(alias400) == 400
c = pc("V1014", "Larchmont Building Products", aliases=alias400)
add(P, c, "accepted", "aliases_exactly_400_chars", "Very long alias list, exactly 400 characters (max_length 400).",
    prev=True)

c = pc("V1015", "Alder Creek Supply Inc")
add(P, c, "accepted", "similar_name_but_different_ein_a",
    "Near-identical name to V1016 in the same country, but both tax ids are filled and different: not flagged.",
    prev=True)
c = pc("V1016", "Alder Creek Supply Inc.")
add(P, c, "accepted", "similar_name_but_different_ein_b",
    "Pair of V1015; different EIN and different bank, so the similar-name check is suppressed by unless_different.")

c = pc("V1017", "Westgate Signage Co", email="AP.Billing+INV@Westgate-Signage.Example.COM")
add(P, c, "accepted", "email_plus_tag_mixed_case", "Valid e-mail with a plus tag, mixed case, multi-part domain.",
    prev=True)

c = pc("V1018", "Pinecrest Janitorial Supply")
r = c["routing_number"]
add(P, c, "accepted", "routing_number_with_spaces",
    "ABA printed as '%s %s %s' (spaces only); the 9 digits have a valid checksum. UNSURE: see README." % (r[:4], r[4:8], r[8]),
    raw={"ABA": f"{r[:4]} {r[4:8]} {r[8]}"})

c = pc("V1019", "Northern Lights Optics Ltd.", "CA", tax_id="812345670RT0001", tax_rate="0.13")
add(P, c, "accepted", "canadian_business_number", "Canadian BN with RT suffix (not an EIN); 13% HST; no bank.", prev=True)

c = pc("V1020", "Redstone Demolition Inc", status="blocked")
add(P, c, "accepted", "blocked_vendor_unchanged",
    "Status B -> blocked. A blocked vendor is a valid record; it is identical to the snapshot.", prev=True)

c = pc("V1021", "Fairhaven Print Studio", onboarded_date="2024-03-07", payment_terms_days="0")
add(P, c, "accepted", "date_without_zero_padding_terms_zero",
    "Onboarded '3/7/2024' reads with %m/%d/%Y (single-digit month/day); Terms 0 (cash) is the minimum.",
    raw={"Onboarded": "3/7/2024"}, prev=True)

c = pc("V1022", "Larkspur Courier Services")
add(P, c, "accepted", "fullwidth_digits_in_terms",
    "Terms typed as full-width digits '\uff13\uff10' (30). UNSURE: see README.", raw={"Terms (days)": "\uff13\uff10"})

c = pc("V1023", "Blue\u200bHeron Logistics")
add(P, c, "accepted", "zero_width_space_in_name",
    "Name contains a zero-width space between Blue and Heron; name has no pattern and nothing else is wrong.")

c = pc("V1026", "O'Malley & Sons Roofing, Inc.")
add(P, c, "accepted", "apostrophe_comma_ampersand_in_name",
    "Name with apostrophe, ampersand and a comma (quoted CSV field). Apostrophe is inside, not a leading text marker.",
    prev=True)

c27 = pc("V1027", "Riverbend Paper Co")
add(P, c27, "accepted", "first_of_exact_duplicate", "First of two V1027 rows that normalise to identical content.",
    prev=True)

c = pc("V1064", "Alder Creek Supply Ltd", "CA", tax_id="", tax_rate="0.05")
add(P, c, "accepted", "similar_name_other_country",
    "Name very close to Alder Creek Supply Inc (V1015/V1016) and no tax id, but country CA vs US: blocking on country "
    "means no comparison. Country 'canada' maps case-insensitively.", raw={"Country": "canada"}, prev=True)

# ---- portal rejected
c = pc("V1031", "Marlowe Precision Castings", tax_id="")
add(P, c, "rejected", "us_vendor_missing_ein", "US vendor with an empty EIN fails rule us_vendor_needs_ein.")

c = pc("V1032", "Bellweather HVAC Services")
add(P, c, "rejected", "ein_trailing_letter", "EIN '%sA' has a trailing letter: fails NN-NNNNNNN." % c["tax_id"],
    raw={"EIN": c["tax_id"] + "A"})

c = pc("V1033", "Cardinal Point Surveying")
d9 = c["tax_id"].replace("-", "")
add(P, c, "rejected", "ein_with_space",
    "EIN '%s %s' uses a space instead of the hyphen. UNSURE: see README." % (d9[:2], d9[2:]),
    raw={"EIN": f"{d9[:2]} {d9[2:]}"})

c = pc("V1034", "Driftwood Packaging Inc", tax_rate="0.075")
add(P, c, "rejected", "tax_percent_decimal_comma",
    "Sales Tax % '7,5' (decimal comma): not a US number, and read as 75 it would be 0.75 > 0.25. In the snapshot, so "
    "its previous version stays in force.", raw={"Sales Tax %": "7,5"}, prev=True)

c = pc("V1035", "Evergreen Fleet Services", bank_account="670913482211")
add(P, c, "rejected", "bank_account_scientific_notation",
    "Bank Acct '6.70913E+11': spreadsheet scientific notation in an identifier. Previous version carried forward.",
    raw={"Bank Acct": "6.70913E+11"}, prev=True)

c = pc("V1036", "Foxglove Floral Wholesale", routing_number=bad_aba())
add(P, c, "rejected", "aba_bad_checksum", "ABA %s has 9 digits but fails the checksum." % c["routing_number"])

c = pc("V1037", "Glenmore Stone & Tile", bank_account="004417726351")
add(P, c, "rejected", "bank_account_leading_apostrophe",
    "Bank Acct \"'004417726351\": the Excel text-forcing apostrophe survived into the CSV; digits_only removes only "
    "spaces and hyphens, so the pattern \\d{6,17} fails.", raw={"Bank Acct": "'004417726351"})

c = pc("V1038", "Harrowgate Bespoke Joinery Ltd", "GB", tax_id="GB 571 0042 88 003")
add(P, c, "rejected", "country_uk_not_mapped", "Country 'UK' is not in the portal value_map nor an allowed code (GB).",
    raw={"Country": "UK"})

c = pc("V1039", "Ivy Lane Bakery Supply", onboarded_date="2024-03-15")
add(P, c, "rejected", "iso_date_in_portal", "Onboarded '2024-03-15' is ISO; the portal only allows %m/%d/%Y.",
    raw={"Onboarded": "2024-03-15"})

c = pc("V1040", "Juniper Analytics Group")
add(P, c, "rejected", "email_double_at", "Contact Email has two @ signs.",
    raw={"Contact Email": "ap@@juniper-analytics.example.com"})

c = pc("V1041", "Keystone Asphalt Paving", routing_number="")
add(P, c, "rejected", "us_bank_without_routing", "US vendor with a bank account but no ABA (us_bank_needs_routing).")

c = pc("V1042", "Lantern Bay Seafood")
add(P, c, "rejected", "net_prefix_in_portal_terms",
    "Terms 'NET30': only the ERP source strips NET; for the portal it is not an integer.", raw={"Terms (days)": "NET30"})

c = pc("V1043", "Meadowlark Event Rentals")
add(P, c, "rejected", "zero_width_space_in_vendor_id",
    "Supplier ID 'V1043' followed by a zero-width space (U+200B): not whitespace for trim, so the pattern fails.",
    raw={"Supplier ID": "V1043\u200b"})

c = pc("V1044", "Nordwerk Anlagenbau GmbH", "DE", tax_id="27/604/31998", tax_rate="0.19",
       bank_account="DE89370400440532013000")
add(P, c, "rejected", "iban_in_bank_account",
    "Bank Acct is an IBAN 'DE89 3704 0044 0532 0130 00': letters remain after digits_only, pattern \\d{6,17} fails.",
    raw={"Bank Acct": "DE89 3704 0044 0532 0130 00"})

n121 = n120[:-1] + "Co"
assert len(n121) == 121
c = pc("V1045", n121)
add(P, c, "rejected", "name_121_chars", "Name is 121 characters, one over max_length 120.")

c = pc("V1046", "Orchard Valley Produce", tax_rate="0.3")
add(P, c, "rejected", "tax_rate_above_max", "Sales Tax % 30 -> 0.30 > 0.25.")

c = pc("V1049", "Ravenswood Security Systems", email="", routing_number=bad_aba())
add(P, c, "rejected", "review_plus_reject_on_one_row",
    "Active with no e-mail (review) AND an ABA with a bad checksum (reject): reject wins.")

c = pc("V1050", "")
add(P, c, "rejected", "name_empty", "Supplier Name is empty (required).", raw={"Supplier Name": "   "})

# ---- portal review
c = pc("V1051", "Tamarack Trail Outfitters", email="")
add(P, c, "review", "active_vendor_without_email", "Active vendor with no contact e-mail (review-severity rule).")

c = pc("V1052", "Union Square Copy Center")
add(P, c, "review", "bank_account_changed", "Bank account differs from the snapshot (change control).",
    prev={"bank_account": new_bank()})

c = pc("V1053", "Vantage Point Optics")
add(P, c, "review", "routing_number_changed", "Routing number differs from the snapshot; account unchanged.",
    prev={"routing_number": new_aba()})

c = pc("V1054", "Wexford & Kell Chartered Surveyors", "GB", tax_id="", tax_rate="0.2", bank_account="55031274")
add(P, c, "review", "tax_id_removed", "UK vendor: tax id was 'GB 391 8820 47 002' in the snapshot and is now empty.",
    prev={"tax_id": "GB 391 8820 47 002"})

shared_bank, shared_aba = new_bank(), new_aba()
c = pc("V1055", "Lakeshore Industrial Supply", bank_account=shared_bank, routing_number=shared_aba)
add(P, c, "review", "shared_bank_account_a", "Same bank account + routing as V1056 (different name, different EIN).",
    prev=True)
c = pc("V1056", "LSI Procurement Services", bank_account=shared_bank, routing_number=shared_aba)
add(P, c, "review", "shared_bank_account_b", "Same bank account + routing as V1055; new vendor id.")

cobalt_ein, cobalt_bank, cobalt_aba = new_ein(), new_bank(), new_aba()
c = pc("V1057", "Cobalt Ridge Fasteners Inc", tax_id=cobalt_ein, bank_account=cobalt_bank, routing_number=cobalt_aba)
add(P, c, "review", "renumbered_vendor_portal_side",
    "Same company exists in the ERP as V2040: same EIN and same bank. In the snapshot, so carried forward.", prev=True)

c = pc("V1058", "@Home Office Interiors")
add(P, c, "review", "name_starts_with_at_sign", "Name starts with '@' and is not a number (formula-injection guard).")

c = pc("V1059", "Yellowpine Lumber Co", aliases='=HYPERLINK("http://example.com/pay","Yellowpine")')
add(P, c, "review", "alias_is_formula_text", "Also Known As starts with '=' (a HYPERLINK formula as text).")

c = pc("V1060", "Kestrel Valley Instruments Ltd", "GB", tax_id="", tax_rate="0.2", bank_account="20481193")
add(P, c, "review", "lookalike_name_original",
    "GB vendor without tax id; V1061 has the same name with a Cyrillic 'а' -> fuzzy match, tax ids not both filled.",
    prev=True)
c = pc("V1061", "Kestrel V\u0430lley Instruments Ltd", "GB", tax_id="", tax_rate="0.2", bank_account="20577340")
add(P, c, "review", "lookalike_name_cyrillic_a",
    "Name uses Cyrillic U+0430 for the 'a' in Valley: looks identical to V1060, different bank, no tax id.")

c = pc("V1062", "Zephyr Cleanroom Products")
add(P, c, "review", "same_id_different_content_a", "V1062 appears twice with different e-mails: both rows held.",
    prev=True)
c2 = dict(c, email="payables@zephyr-cleanroom.example.com")
add(P, c2, "review", "same_id_different_content_b", "Second V1062 row, e-mail differs from the first.")

c = c1063 = pc("V1063", "Arbor Hill Nurseries", payment_terms_days="30")
add(P, c, "review", "same_id_across_systems_conflict",
    "V1063 is also in erp.xlsx, identical except terms 45: same id, different content, both held.")

c = pc("V1065", "Brookfield Pallet Recovery", status="blocked")
add(P, c, "review", "bank_change_on_blocked_vendor",
    "Bank changed vs snapshot -> review. Held version is blocked, so the old active version is NOT carried forward.",
    prev={"bank_account": new_bank(), "status": "active"})

add(P, c27, "duplicate", "exact_duplicate_after_normalisation",
    "Second V1027 row: extra spaces in the name and status 'a' instead of 'A' normalise to identical content.",
    raw={"Supplier Name": "  Riverbend   Paper  Co ", "Status": "a"})

# ================================================================= ERP
def ec(vid, name, country="US", currency="USD", **kw):
    return canon(vid, name, country, currency=currency, **kw)

c = ec("V2001", "Harlow Industrial Coatings Inc", onboarded_date="2022-06-14")
add(E, c, "accepted", "plain_erp_vendor_date_cell", "Clean ERP vendor; CREATED is a real Excel date cell; NET30.",
    raw={"CREATED": datetime.date(2022, 6, 14)}, prev=True)

c = ec("V2002", "Hoffmann & Söhne Präzisionsteile GmbH", "DE", "EUR", tax_id="DE-HRB 48213", tax_rate="0.19",
       aliases="Hoffmann Praezision;HSP GmbH", onboarded_date="2023-03-14")
add(E, c, "accepted", "german_gmbh_dotted_date_pipe_aliases",
    "Umlauts, CREATED '14.03.2023' (%d.%m.%Y), ALT_NAMES with '|' -> ';', VAT 0.19, EUR, no bank.",
    raw={"CREATED": "14.03.2023"}, prev=True)

c = ec("V2003", "Grupo Industrial Arenal S.A. de C.V.", "MX", "MXN", tax_id="GIA980612QX3", tax_rate="0.16",
       payment_terms_days="45")
add(E, c, "accepted", "mexican_vendor_lowercase_ccy_net_space",
    "CCY 'mxn' upper-cases to MXN; PAY_TERMS 'NET 45' (NET\\s* is stripped).", raw={"CCY": "mxn", "PAY_TERMS": "NET 45"},
    prev=True)

c = ec("V2004", "Atelier Lumière SARL", "FR", "EUR", tax_id="SIRET 732 829 320 00074", tax_rate="0.2")
add(E, c, "accepted", "french_sarl_siret", "French SARL, SIRET with spaces kept as printed, VAT 0.2, EUR.", prev=True)

c = ec("V2005", "Penrose & Tait Engineering Ltd", "GB", "GBP", tax_rate="0.2", bank_account="30418827",
       payment_terms_days="60")
add(E, c, "accepted", "email_changed_not_controlled",
    "PAY_TERMS is a numeric cell 60; e-mail differs from the snapshot but only bank/routing/tax id are change-controlled.",
    raw={"PAY_TERMS": 60}, prev={"email": "accounts@penrose-tait.example.co.uk"})

c = ec("V2006", "Quayside Scaffolding Inc", status="blocked")
add(E, c, "accepted", "status_hold_lowercase_newly_blocked",
    "STAT 'hold' maps case-insensitively to blocked. Was active in the snapshot; status is not change-controlled.",
    raw={"STAT": "hold"}, prev={"status": "active"})

c = ec("V2007", "Ridgeline Data Cabling", routing_number=new_aba("0"))
add(E, c, "accepted", "routing_text_cell_leading_zero",
    "ROUTING stored as a text cell (quote-prefixed in Excel) so the leading zero survives.", prev=True)

c = ec("V2008", "Sandpiper Laboratory Glass", bank_account="482019375512")
add(E, c, "accepted", "bank_account_numeric_cell",
    "BANK_ACCOUNT is a numeric cell (integer 482019375512, no leading zero to lose). UNSURE: see README.",
    raw={"BANK_ACCOUNT": 482019375512})

c = ec("V2009", "Maple Hollow Timber Ltd.", "CA", "CAD", tax_id="", tax_rate="0.05", bank_account="001230041234567")
add(E, c, "accepted", "canadian_transit_account_hyphens",
    "Canadian account '00123-004-1234567' (transit-institution-account) -> 15 digits; no ABA needed outside the US.",
    raw={"BANK_ACCOUNT": "00123-004-1234567"})

al2 = "|".join(f"Tern Harbor Marine Electronics Branch Office No {i}" for i in range(1, 8))
assert len(al2) <= 400, len(al2)
c = ec("V2010", "Tern Harbor Marine Electronics", aliases=al2.replace("|", ";"))
add(E, c, "accepted", "long_aliases_under_limit", "ALT_NAMES of %d characters with pipes; under 400." % len(al2),
    prev=True)

c = ec("V2011", "Upland Seed & Feed", onboarded_date="2024-02-29")
add(E, c, "accepted", "leap_day_iso_date", "CREATED '2024-02-29' is a real leap day.", raw={"CREATED": "2024-02-29"},
    prev=True)

c = ec("V2012", "Vireo Pest Control", status="inactive", email="")
add(E, c, "accepted", "erp_inactive_without_email", "INACTIVE vendor without e-mail: contact rule not triggered.",
    prev=True)

ein13 = "45-1234567"
used.add(ein13)
c = ec("V2013", "Whitcomb Elevator Service", tax_id=ein13)
add(E, c, "accepted", "ein_numeric_cell",
    "TAX_ID is a numeric cell 451234567 (9 digits) -> ein gives 45-1234567. UNSURE: see README.",
    raw={"TAX_ID": 451234567})

c = ec("V2014", "Yarrow Botanical Extracts", tax_rate="0")
add(E, c, "accepted", "vat_zero_numeric", "VAT_RATE 0 (tax-exempt) is the minimum.", raw={"VAT_RATE": 0}, prev=True)

c16 = ec("V2016", "Zinnia Event Florals")
add(E, c16, "accepted", "erp_first_of_exact_duplicate", "First of two V2016 rows with identical canonical content.",
    prev=True)

c = ec("V2017", "Pacific Rim Components Ltd", currency="")
add(E, c, "accepted", "lowercase_country_empty_currency",
    "CTRY 'us' upper-cases to US; CCY empty is allowed (currency not required, no ERP default). 'Ltd' on a US vendor.",
    raw={"CTRY": "us", "CCY": ""})

c = ec("V2018", "Blackthorn Courier Co", payment_terms_days="0")
add(E, c, "accepted", "net0_terms", "PAY_TERMS 'NET0' -> 0.", prev=True)

c = ec("V2019", "Cinderford Glassworks Inc", payment_terms_days="60", onboarded_date="2021-11-02")
add(E, c, "accepted", "net_space_60_date_cell", "PAY_TERMS 'NET 60', CREATED is a date cell.",
    raw={"PAY_TERMS": "NET 60", "CREATED": datetime.date(2021, 11, 2)}, prev=True)

# ---- ERP rejected
c = ec("V2021", "Dunmore Fire Protection")
add(E, c, "rejected", "status_is_excel_boolean", "STAT is an Excel boolean TRUE, not ACTIVE/INACTIVE/HOLD.",
    raw={"STAT": True})

c = ec("V2022", "Eastlake Water Systems")
add(E, c, "rejected", "tax_id_formula_cell",
    "TAX_ID is a formula cell =TEXT(...) with no cached value: empty (US needs EIN) or '=...' text (fails pattern). "
    "Either way rejected.", raw={"TAX_ID": '=TEXT(472915508,"00-0000000")'})

c = ec("V2023", "Falkenstein Logistik GmbH", "DE", "EUR", tax_id="", tax_rate="0.19")
add(E, c, "rejected", "erp_country_name_not_mapped",
    "CTRY 'Germany': the country-name map belongs to the portal only; the ERP has none.", raw={"CTRY": "Germany"})

c = ec("V2024", "Gilchrist Plumbing Supply")
add(E, c, "rejected", "erp_status_portal_code",
    "STAT 'A' is a portal code; the ERP map only knows ACTIVE/INACTIVE/HOLD. In the snapshot -> carried forward.",
    raw={"STAT": "A"}, prev=True)

c = ec("V2025", "Hawthorne Office Products")
add(E, c, "rejected", "terms_net_45_eom", "PAY_TERMS 'NET 45 EOM' -> '45 EOM' after stripping: not an integer.",
    raw={"PAY_TERMS": "NET 45 EOM"})

c = ec("V2026", "Inglewood Tile Distributors")
add(E, c, "rejected", "terms_mixed_case_net",
    "PAY_TERMS 'Net 30': strip pattern is '^NET\\s*' (upper-case). UNSURE: see README.", raw={"PAY_TERMS": "Net 30"})

c = ec("V2027", "Jasper Creek Ranch Supply")
add(E, c, "rejected", "us_date_in_erp", "CREATED '03/15/2024' is not %Y-%m-%d or %d.%m.%Y.",
    raw={"CREATED": "03/15/2024"})

c = ec("V2028", "Kittredge Sound & Light")
add(E, c, "rejected", "impossible_dotted_date", "CREATED '31.04.2024': April has 30 days.",
    raw={"CREATED": "31.04.2024"})

c = ec("V2029", "Lindenhof Maschinen GmbH", "DE", "EUR", tax_id="", tax_rate="0.19")
add(E, c, "rejected", "vat_as_whole_percent_in_erp",
    "VAT_RATE 19 (a percent): the ERP has no 0.01 scale, so 19 > 0.25.", raw={"VAT_RATE": 19})

rz = new_aba("0")
c = ec("V2030", "Mossgiel Water Testing", routing_number=rz)
add(E, c, "rejected", "routing_numeric_cell_lost_leading_zero",
    "ROUTING stored as a number %d: the leading zero of %s is gone, 8 digits is not an ABA number." % (int(rz), rz),
    raw={"ROUTING": int(rz)})

c = ec("V2031", "Nettlebed Garden Supply Ltd", "GB", "GBP", tax_rate="0.2")
add(E, c, "rejected", "currency_not_allowed", "CCY 'CHF' is not an allowed currency.", raw={"CCY": "CHF"})

c = ec("V2032", "Overbrook Linen Service")
add(E, c, "rejected", "terms_above_max", "PAY_TERMS 'NET150' -> 150 > 120.", raw={"PAY_TERMS": "NET150"})

c = ec("V2033", "Kirkwood Precision Machining")
add(E, c, "rejected", "email_spelled_out", "EMAIL 'ap at kirkwood dot example' is not an e-mail address.",
    raw={"EMAIL": "ap at kirkwood dot example"})

c = ec("V2034", "Pemberton Sheet Metal Ltd", "CA", "CAD", tax_id="", tax_rate="0.13", routing_number=new_aba())
add(E, c, "rejected", "routing_without_account", "Canadian vendor with a routing number but no bank account.")

c = ec("V2035", "Quarrington Hardware")
add(E, c, "rejected", "vendor_id_missing_prefix", "VENDOR_NO '2035' lacks the V prefix: pattern V\\d{3,8} fails.",
    raw={"VENDOR_NO": "2035"})

c = ec("V2045", "Rosewell Scientific Supply")
add(E, c, "rejected", "ein_too_short", "TAX_ID '29-38471' has 7 digits.", raw={"TAX_ID": "29-38471"})

al3 = ";".join(f"Kingsbridge Event Staffing Regional Office {i}" for i in range(1, 11))
assert len(al3) > 400
c = ec("V2046", "Kingsbridge Event Staffing", aliases=al3)
add(E, c, "rejected", "aliases_over_400", "ALT_NAMES is %d characters, over max_length 400." % len(al3))

# ---- ERP review
c = ec("V2040", "COBALT RIDGE FASTENERS INC", tax_id=cobalt_ein, bank_account=cobalt_bank, routing_number=cobalt_aba)
add(E, c, "review", "renumbered_vendor_erp_side",
    "ERP's number for the portal's V1057: same EIN and same bank account/routing (upper-case name).")

c = dict(c1063, payment_terms_days="45")
add(E, c, "review", "same_id_across_systems_conflict_erp",
    "ERP copy of V1063, identical to the portal row except terms NET45 vs 30: same id, different content.")

c = ec("V2036", "-Twelve Below Cold Storage")
add(E, c, "review", "name_starts_with_minus", "VENDOR_NAME starts with '-' and is not a number.")

c = ec("V2037", "Stonebridge Roofing Supply")
add(E, c, "review", "erp_bank_account_changed", "Bank account differs from the snapshot.",
    prev={"bank_account": new_bank()})

c = ec("V2038", "Thornbury Valve & Fitting", tax_id="38-4410257")
used.add("38-4410257")
add(E, c, "review", "ein_transposed_digits", "EIN 38-4410257 vs 38-4410275 in the snapshot (two digits swapped).",
    prev={"tax_id": "38-4410275"})

sb2, sa2 = new_bank(), new_aba()
c = ec("V2039", "Upton Mechanical Group", bank_account=sb2, routing_number=sa2)
add(E, c, "review", "erp_shared_bank_a", "Same bank account + routing as V2041, different names and EINs.")
c = ec("V2041", "Hartwell Facility Partners", bank_account=sb2, routing_number=sa2)
add(E, c, "review", "erp_shared_bank_b", "Same bank account + routing as V2039.")

c = ec("V2042", "Wickham Paint & Coatings", email="")
add(E, c, "review", "erp_active_without_email", "ACTIVE vendor with no EMAIL.")

c = ec("V2043", "Yorkshire Dales Fleece Ltd", "GB", "GBP", tax_rate="0.2", bank_account="71130284")
add(E, c, "review", "erp_same_id_different_content_a", "V2043 twice with different VAT_RATE: both held.", prev=True)
c2 = dict(c, tax_rate="0.05")
add(E, c2, "review", "erp_same_id_different_content_b", "Second V2043 row, VAT_RATE 0.05 vs 0.2.")

c = ec("V2044", "Bramble Bay Seafoods Ltd", "CA", "CAD", tax_rate="0.05", bank_account="")
add(E, c, "review", "bank_account_removed", "Canadian vendor: snapshot had account 004219874410392, now empty.",
    prev={"bank_account": "004219874410392"})

add(E, c16, "duplicate", "erp_exact_duplicate_numeric_terms",
    "Second V2016 row: PAY_TERMS numeric 30 instead of 'NET30' and a trailing space in the name -> identical content.",
    raw={"PAY_TERMS": 30, "VENDOR_NAME": "Zinnia Event Florals "})

# ================================================================= write vendor files
with open(os.path.join(OUT, "portal.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(PORTAL_COLS)
    for r in rows[P]:
        w.writerow([r["raw"][k] for k in PORTAL_COLS])

import openpyxl
from openpyxl.cell.cell import TYPE_STRING
wb = openpyxl.Workbook()
ws = wb.active
ws.title = "VENDORS"
ws.append(ERP_COLS)
for i, r in enumerate(rows[E]):
    rr = i + 2
    for j, k in enumerate(ERP_COLS):
        v = r["raw"][k]
        if v == "":
            v = None
        cell = ws.cell(row=rr, column=j + 1)
        cell.value = v
        if isinstance(v, datetime.date):
            cell.number_format = "yyyy-mm-dd"
        if k == "ROUTING" and isinstance(v, str):
            try:
                cell.quotePrefix = True
            except Exception:
                pass
wb.save(os.path.join(OUT, "erp.xlsx"))

# ================================================================= previous + reference
def wcsv(name, recs):
    with open(os.path.join(OUT, name), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(FIELDS)
        for rec in recs:
            w.writerow([rec[k] for k in FIELDS])

wcsv("previous.csv", [previous[k] for k in sorted(previous)])

ref = {}
held_ids = {}
for file in (P, E):
    for r in rows[file]:
        vid = r["canon"]["vendor_id"]
        if r["case"] in ("vendor_id_missing_prefix", "zero_width_space_in_vendor_id"):
            vid = None
        if r["expect"] == "accepted":
            assert vid not in ref, vid
            ref[vid] = r["canon"]
        elif r["expect"] in ("review", "rejected") and vid:
            held_ids.setdefault(vid, []).append(r["held_status"])
for vid, sts in held_ids.items():
    if vid in previous and vid not in ref and not any(s in ("blocked", "inactive") for s in sts):
        ref[vid] = previous[vid]
wcsv("vendors_reference.csv", [ref[k] for k in sorted(ref)])
ref_status = {k: v["status"] for k, v in ref.items()}

# ================================================================= PO lines
PO_COLS = ["PO_NUMBER", "VENDOR_NO", "PO_STATUS", "CCY", "LINE", "ITEM", "ITEM_DESC", "QTY", "UNIT_PRICE", "GR_REQUIRED"]
po = []
def L(po_no, vendor, st, ccy, line, item, desc, qty, price, gr, expect, case, why):
    po.append(dict(zip(PO_COLS, [po_no, vendor, st, ccy, line, item, desc, qty, price, gr]),
                   expect=expect, case=case, why=why))

A = "accepted"
L("PO-5001", "V1001", "O", "USD", 1, "BLT-M8", "Bolt set M8, zinc", "50", "10.40", "yes", A, "plain_po_line", "Clean line; active vendor.")
L("PO-5001", "V1001", "O", "USD", 2, "GLV-L", "Safety gloves, size L", "12", "24.00", "yes", A, "plain_po_line", "Clean line.")
L("PO-5001", "V1001", "O", "USD", 3, "TNR-BK", "Printer toner, black", "2", "280.00", "no", A, "plain_po_line", "Clean line.")
L("PO-5002", "V1002", "O", "USD", 1, "BLT-M8", "Bolt set M8, zinc", "40", "10.75", "yes", A, "plain_po_line", "Clean line.")
L("PO-5002", "V1002", "O", "USD", 2, "CPR-WIRE", "Copper wire, bare, per kg", "2.5", "1,234.50", "yes", A, "decimal_qty_thousands_price", "Quantity 2.5 kg; price '1,234.50' uses a US thousands separator.")
L("PO-5002", "V1002", "O", "USD", 3, "GLV-L", "Safety gloves, size L", "20", "25.50", "yes", A, "plain_po_line", "Clean line.")
L("PO-5002", "V1002", "O", "USD", 4, "HRD-HAT", "Hard hat, white", "10", "15.00", "yes", A, "plain_po_line", "Clean line.")
L("PO-5003", "v1003", "o", "USD", 1, "TNR-BK", "Printer toner, black", "3", "295.00", "no", A, "lowercase_vendor_and_status_code", "Vendor 'v1003' upper-cases; status 'o' maps case-insensitively to open.")
L("PO-5003", "v1003", "o", "USD", 2, "BLT-M8", "Bolt set M8, zinc", "25", "11.20", "yes", A, "lowercase_vendor_and_status_code", "Same PO, consistent.")
L("PO-5004", "V2002", "O", "eur ", 1, "SPN-4410", "Spindle assembly 4410", "1", "845.00", "yes", A, "eur_lowercase_trailing_space", "CCY 'eur ' trims/upper-cases to EUR; German vendor.")
L("PO-5004", "V2002", "O", "EUR", 2, "BRG-6204", "Ball bearing 6204-2RS", "16", "7.35", "yes", A, "eur_lowercase_trailing_space", "Other line says 'EUR': after normalisation the PO is consistent.")
L("PO-5005", "V1001", "C", "EUR", 1, "FLT-HEPA", "HEPA filter 24x24", "6", "118.00", "no", A, "closed_po_currency_differs_from_vendor", "US vendor ordered in EUR on a closed PO: no rule ties PO currency to the vendor.")
L("PO-5006", "V1020", "O", "USD", 1, "DEMO-SVC", "Interior demolition, bay 4", "1", "4500.00", "no", "review", "vendor_blocked", "V1020 is blocked in the vendor reference.")
L("PO-5006", "V1020", "O", "USD", 2, "SKP-20", "20 yd roll-off container", "2", "650.00", "no", "review", "vendor_blocked", "V1020 is blocked.")
L("PO-5007", "V2012", "O", "USD", 1, "PEST-QTR", "Quarterly pest service", "1", "380.00", "no", "review", "vendor_inactive", "V2012 is inactive.")
L("PO-5008", "V1052", "O", "USD", 1, "PPR-A4", "Copy paper, case", "10", "42.00", "yes", A, "vendor_held_but_carried_forward", "V1052 is held for a bank change, but its previous accepted version is in force.")
L("PO-5008", "V1052", "O", "USD", 2, "BLT-M8", "Bolt set M8, zinc", "30", "9.90", "yes", A, "vendor_held_but_carried_forward", "Same.")
L("PO-5009", "V1034", "O", "USD", 1, "BOX-18", "Shipping box 18x18x12", "1,200", "0.86", "yes", A, "rejected_vendor_carried_forward_qty_thousands", "V1034's new row is rejected but its previous version stays in force; quantity '1,200' = 1200.")
L("PO-5010", "V1056", "O", "USD", 1, "MRO-KIT", "MRO consumables kit", "4", "96.00", "yes", "rejected", "vendor_held_not_in_force", "V1056 is new and held (shared bank): not in the reference.")
L("PO-5010", "V1056", "O", "USD", 2, "MRO-TAPE", "Duct tape, case", "2", "54.00", "yes", "rejected", "vendor_held_not_in_force", "Same.")
L("PO-5011", "V9999", "O", "USD", 1, "OFF-CHR", "Office chair", "4", "210.00", "yes", "rejected", "unknown_vendor", "V9999 does not exist.")
L("PO-5012", "V1031", "O", "USD", 1, "CST-VALVE", "Cast valve body", "8", "77.00", "yes", "rejected", "vendor_rejected_not_in_snapshot", "V1031 was rejected and has no previous version.")
L("PO-5013", "V1001", "O", "USD", 1, "LBL-4X6", "Shipping labels 4x6", "10", "18.00", "yes", "rejected", "po_vendor_inconsistent", "PO-5013 lines name two vendors (V1001, V1002).")
L("PO-5013", "V1002", "O", "USD", 2, "LBL-2X1", "Barcode labels 2x1", "10", "12.00", "yes", "rejected", "po_vendor_inconsistent", "Same PO, different vendor.")
L("PO-5013", "V1001", "O", "USD", 3, "RBN-110", "Thermal ribbon 110mm", "5", "9.50", "yes", "rejected", "po_vendor_inconsistent", "Every line of the PO is rejected.")
L("PO-5014", "V1004", "O", "USD", 1, "ROPE-12", "Mooring rope 12mm, per m", "150", "2.10", "yes", "rejected", "po_currency_inconsistent", "PO-5014 mixes USD and CAD.")
L("PO-5014", "V1004", "O", "USD", 2, "FNDR-L", "Boat fender, large", "6", "64.00", "yes", "rejected", "po_currency_inconsistent", "Same.")
L("PO-5014", "V1004", "O", "CAD", 3, "SHKL-10", "Shackle 10mm", "12", "8.75", "yes", "rejected", "po_currency_inconsistent", "The CAD line.")
L("PO-5015", "V1005", "O", "USD", 1, "DSK-60", "Desk 60in", "2", "540.00", "yes", "rejected", "po_status_inconsistent", "PO-5015 is open on line 1 and closed on line 2.")
L("PO-5015", "V1005", "C", "USD", 2, "CHR-TASK", "Task chair", "2", "310.00", "yes", "rejected", "po_status_inconsistent", "Same.")
L("PO-5016", " V1003", "O", "usd", 1, "BLT-M8", "Bolt set M8, zinc", "60", "10.10", "yes", A, "po_consistent_after_normalisation", "' V1003'/'v1003', 'usd'/'USD'/'Usd', 'O'/'open'/'o' all normalise to the same values.")
L("PO-5016", "v1003", "open", "USD", 2, "GLV-L", "Safety gloves, size L", "24", "26.10", "yes", A, "po_consistent_after_normalisation", "Same PO.")
L("PO-5016", "V1003", "o", "Usd", 3, "TNR-BK", "Printer toner, black", "1", "288.00", "no", A, "po_consistent_after_normalisation", "Same PO.")
L("PO-5017", "V2001", "O", "USD", 1, "PIPE-2IN", "Steel pipe 2in, per ft", "40", "18.60", "yes", A, "plain_po_line", "Clean line.")
L("PO-5017", "V2001", "O", "USD", 2, "PIPE-2IN", "Return credit, damaged pipe", "4", "-18.60", "no", "rejected", "negative_price_credit_line", "unit_price -18.60 < min 0 (a credit entered as a negative price).")
L("PO-5018", "V2003", "O", "MXN", 1, "TRM-50", "Tarima de madera 50", "20", "$1,250.00", "yes", "rejected", "price_with_currency_symbol", "UNIT_PRICE '$1,250.00' has a currency symbol. UNSURE: see README.")
L("PO-5018", "V2003", "O", "MXN", 2, "FLM-STR", "Película estirable", "12", "389.00", "yes", A, "accented_description", "Spanish description with accents; clean line.")
L("PO-5019", "V1006", "O", "USD", 1, "AU-LEAF", "Gold leaf, per gram", "0", "92.00", "yes", "rejected", "quantity_zero", "QTY 0 < min 0.001.")
L("PO-5019", "V1006", "O", "USD", 2, "AU-LEAF2", "Gold leaf 23k, per gram", "0.0005", "95.00", "yes", "rejected", "quantity_below_min", "QTY 0.0005 < 0.001.")
L("PO-5019", "V1006", "O", "USD", 3, "AU-LEAF3", "Gold leaf 24k, per gram", "0.001", "98.00", "yes", A, "quantity_at_min", "QTY 0.001 is exactly the minimum.")
L("PO-5020", "V1015", "O", "USD", 1, "SMP-KIT", "Free sample kit", "1", "0", "no", A, "zero_price_sample", "Unit price 0 is allowed (min 0); item has no peers for the outlier check.")
L("PO-5021", "V1002", "O", "USD", 1, "WLD-ROD", "Welding rod 3/32, 10 lb", "5", "41.00", "X", "rejected", "receipt_flag_x", "GR_REQUIRED 'X' (SAP-style tick) is not a boolean. UNSURE: see README.")
L("PO-5021", "V1002", "O", "USD", 2, "WLD-GAS", "Argon cylinder refill", "2", "63.00", "no", A, "plain_po_line", "Clean line.")
L("PO-5022", "V2007", "O", "USD", 0, "CBL-C6A", "Cat6A cable, 1000 ft", "3", "289.00", "yes", "rejected", "line_zero", "LINE 0 < min 1.")
L("PO-5022", "V2007", "O", "USD", 999, "PNL-24", "Patch panel 24-port", "4", "58.00", "yes", A, "line_at_max", "LINE 999 is the maximum.")
L("PO-5022", "V2007", "O", "USD", 1000, "JCK-C6A", "Keystone jack Cat6A", "100", "4.20", "yes", "rejected", "line_above_max", "LINE 1000 > 999.")
L("PO5023", "V1001", "O", "USD", 1, "ENV-10", "Envelopes #10, box", "10", "11.00", "yes", "rejected", "po_number_missing_hyphen", "PO number 'PO5023' fails pattern PO-\\d{3,10}.")
L("po-5024", "V1004", "O", "USD", 1, "GLV-L", "Safety gloves, size L", "18", "23.75", "yes", A, "lowercase_po_number", "'po-5024' upper-cases to PO-5024.")
L("po-5024", "V1004", "O", "USD", 2, "TNR-BK", "Printer toner, black", "2", "270.00", "no", A, "lowercase_po_number", "Same PO.")
L("PO-5025", "V1005", "O", "USD", 1, "", "Misc. hardware", "1", "15.00", "yes", "rejected", "item_code_empty", "ITEM is empty (required).")
L("PO-5025", "V1005", "O", "USD", 2, "CBN-FILE", "Filing cabinet, 4 drawer", "1", "289.00", "yes", A, "plain_po_line", "Clean line.")
d200 = ("Custom fabricated stainless steel enclosure per drawing DWG-22-0417 rev C, 16 gauge 304, brushed finish, "
        "with gasketed door, three-point latch, and mounting flange; ")
d200 = (d200 + "x" * 200)[:200]
d201 = d200 + "Z"
L("PO-5026", "V2019", "O", "USD", 1, "ENC-SS1", d201, "1", "1840.00", "yes", "rejected", "description_201_chars", "ITEM_DESC is 201 characters (max 200).")
L("PO-5026", "V2019", "O", "USD", 2, "ENC-SS2", d200, "1", "1840.00", "yes", A, "description_200_chars", "ITEM_DESC is exactly 200 characters.")
L("PO-5027", "V2001", "X", "USD", 1, "PNT-EPX", "Epoxy floor coating, 5 gal", "4", "212.00", "no", A, "cancelled_po", "Status X -> cancelled is valid.")
L("PO-5027", "V2001", "X", "USD", 2, "PNT-PRM", "Primer, 5 gal", "2", "148.00", "no", A, "cancelled_po", "Same.")
L("PO-5028", "V1053", "O", "USD", 1, "HRD-HAT", "Hard hat, white", "12", "16.20", "yes", A, "vendor_held_but_carried_forward", "V1053 held for routing change; previous version in force.")
L("PO-5028", "V1053", "O", "USD", 2, "GLV-L", "Safety gloves, size L", "200", "0.25", "yes", "review", "price_outlier_low", "GLV-L at 0.25 vs ~24-26 on four other lines (~100x below): decimal slip.")
L("PO-5029", "V1055", "O", "USD", 1, "RSTK-FEE", "-10% restocking adjustment", "1", "35.00", "no", "review", "description_starts_with_minus", "ITEM_DESC starts with '-' and is not a number.")
L("PO-5029", "V1055", "O", "USD", 2, "BLT-M8", "Bolt set M8, zinc", "10", "1045.00", "yes", "review", "price_outlier_high", "BLT-M8 at 1045.00 vs 9.90-11.20 on five other lines (~100x): decimal slip.")
L("PO-5030", "V2005", "O", "US$", 1, "GSK-NBR", "NBR gasket set", "10", "14.00", "yes", "rejected", "currency_code_with_symbol", "CCY 'US$' is not an allowed currency.")
L("PO-5031", "V1057", "O", "USD", 1, "1.23E+05", "Hex nut M10 (item 123000)", "500", "0.12", "yes", "rejected", "item_code_scientific_notation", "ITEM '1.23E+05': a spreadsheet turned item 123000 into scientific notation. UNSURE: see README.")
L("PO-5031", "V1057", "O", "USD", 2, "HRD-HAT", "Hard hat, white, premium", "1", "162.00", "yes", A, "outlier_but_group_too_small", "HRD-HAT has only 3 lines in total: below min_group 4, so no outlier check. V1057 carried forward.")
L("PO-5032", "V2006", "O", "USD", 1, "SCF-FRM", "Scaffold frame 5x6", "20", "88.00", "yes", "review", "vendor_blocked_hold", "V2006 is blocked (ERP HOLD) in the reference.")
L("PO-5033", "V2040", "O", "USD", 1, "FST-KIT", "Fastener assortment", "6", "73.00", "yes", "rejected", "renumbered_vendor_not_in_force", "V2040 is the ERP duplicate of V1057, held and new: not in the reference.")
L("PO-5034", "V1062", "O", "USD", 1, "CLR-WIPE", "Cleanroom wipes, case", "8", "129.00", "yes", A, "vendor_conflict_carried_forward", "V1062 held (two different rows) but its snapshot version is in force.")
L("PO-5036", "V1010", "C", "USD", 1, "CTR-LUNCH", "Catered lunch, 40 people", "40", "18.50", "no", "review", "vendor_inactive_closed_po", "V1010 is inactive; the rule does not exempt closed POs.")
L("PO-5037", "V2043", "O", "GBP", 1, "FLC-ROLL", "Fleece roll 1.5m", "6", "210.00", "yes", A, "gbp_vendor_carried_forward", "V2043 held (same-id conflict); previous version in force.")
L("PO-5037", "V2043", "O", "GBP", 2, "FLC-OFF", "Fleece offcuts, kg", "12.5", "6.40", "yes", A, "gbp_vendor_carried_forward", "Decimal quantity.")
L("PO-5038", "V1060", "O", "GBP", 1, "CAL-SVC", "Calibration service, gauge", "3", "145.00", "no", A, "lookalike_original_carried_forward", "V1060 held (look-alike pair) but its previous version is in force.")
L("PO-5039", "V1061", "O", "GBP", 1, "CAL-SVC2", "Calibration service, gauge", "3", "145.00", "no", "rejected", "lookalike_vendor_not_in_force", "V1061 (Cyrillic look-alike) is new and held: not in the reference.")
L("PO-5040", "V2019", "O", "USD", 1, "TNR-BK", "Printer toner, black, high-yield", "1", "1650.00", "no", A, "price_high_but_below_factor", "TNR-BK 1650 vs 270-295 on four other lines: ~5.8x, below factor 8.")
L("PO-5041", "V1054", "O", "GBP", 1, "SRV-HR", "Survey consultancy, hours", "12.75", "95.00", "no", A, "decimal_hours_carried_vendor", "Decimal quantity of hours; V1054 held but carried forward.")
L("PO-5043", "V2038", "O", "USD", 1, "VLV-BALL1", "Ball valve 1in", "24", "31.00", "yes", A, "vendor_tax_change_carried_forward", "V2038 held for EIN change; previous version in force.")
L("PO-5043", "V2038", "O", "USD", 2, "VLV-GATE2", "Gate valve 2in", "6", "88.00", "yes", A, "vendor_tax_change_carried_forward", "Same.")
L("PO-5044", "V2024", "O", "USD", 1, "PLM-PEX", "PEX tubing 1/2in, 100 ft", "5", "46.00", "yes", A, "erp_rejected_vendor_carried_forward", "V2024 rejected today (STAT 'A') but its snapshot version is in force.")
L("PO-5045", "V1065", "O", "USD", 1, "PLT-48", "Recycled pallet 48x40", "100", "6.50", "yes", "rejected", "blocked_held_vendor_not_carried", "V1065's held version is blocked, so its old version is not carried forward; not in the reference. UNSURE: see README.")
L("PO-5046", "V2002", "C", "EUR", 1, "BRG-6205", "Ball bearing 6205-2RS", "1,000", "8.10", "yes", A, "closed_po_thousands_qty", "Closed PO; quantity '1,000' = 1000.")

# vendor sanity: every PO vendor's expectation agrees with the reference
for l in po:
    v = l["VENDOR_NO"].strip().upper()
    if l["case"] in ("vendor_held_not_in_force", "unknown_vendor", "vendor_rejected_not_in_snapshot",
                     "renumbered_vendor_not_in_force", "lookalike_vendor_not_in_force", "blocked_held_vendor_not_carried"):
        assert v not in ref, (l, v)
    else:
        assert v in ref, (l["PO_NUMBER"], v)
        if l["expect"] == "accepted":
            assert ref_status[v] == "active", (l["PO_NUMBER"], v)
        if l["case"].startswith("vendor_blocked") or l["case"].startswith("vendor_inactive"):
            assert ref_status[v] in ("blocked", "inactive")

with open(os.path.join(OUT, "po.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(PO_COLS)
    for l in po:
        w.writerow([l[k] for k in PO_COLS])

# ================================================================= truth
truth = []
for file in (P, E):
    for i, r in enumerate(rows[file]):
        truth.append({"file": file, "row": i + 2, "expect": r["expect"], "case": r["case"], "why": r["why"]})
for i, l in enumerate(po):
    truth.append({"file": "po.csv", "row": i + 2, "expect": l["expect"], "case": l["case"], "why": l["why"]})
with open(os.path.join(OUT, "truth.json"), "w", encoding="utf-8") as f:
    json.dump(truth, f, indent=1, ensure_ascii=False)

# ================================================================= self-checks
from collections import Counter
for file in ("portal.csv", "erp.xlsx", "po.csv"):
    cnt = Counter(t["expect"] for t in truth if t["file"] == file)
    print(file, sum(cnt.values()), dict(cnt))
print("previous", len(previous), "reference", len(ref))

for rec in list(previous.values()) + list(ref.values()):
    if rec["routing_number"]:
        assert aba_valid(rec["routing_number"]), rec
for file in (P, E):
    for r in rows[file]:
        rn = r["canon"]["routing_number"]
        if r["expect"] == "accepted" and rn:
            assert aba_valid(rn), r

# accidental collisions among current (non-duplicate) rows: tax id and bank
from rapidfuzz import fuzz, utils
cur = []
for file in (P, E):
    for i, r in enumerate(rows[file]):
        if r["expect"] != "duplicate":
            cur.append((file, i + 2, r["canon"], r["case"]))
for a in range(len(cur)):
    for b in range(a + 1, len(cur)):
        ca, cb = cur[a][2], cur[b][2]
        if ca["vendor_id"] == cb["vendor_id"]:
            continue
        if ca["tax_id"] and ca["tax_id"] == cb["tax_id"]:
            print("SAME TAX", cur[a][:2], cur[b][:2], cur[a][3], cur[b][3])
        if ca["bank_account"] and ca["bank_account"] == cb["bank_account"]:
            print("SAME BANK", cur[a][:2], cur[b][:2], cur[a][3], cur[b][3])
        if ca["country"] == cb["country"]:
            na, nb = ca["name"], cb["name"]
            s = max(fuzz.ratio(na, nb, processor=utils.default_process), fuzz.token_set_ratio(na, nb),
                    fuzz.partial_ratio(na, nb, processor=utils.default_process), fuzz.WRatio(na, nb),
                    fuzz.ratio(na, nb))
            if s >= 75:
                print("FUZZY %.0f" % s, cur[a][:2], na, "|", cur[b][:2], nb, "| tax:", ca["tax_id"], cb["tax_id"])
# previous-only values that collide with a different current vendor
for vid, p in previous.items():
    for f_, rr, cc, case in cur:
        if cc["vendor_id"] != vid:
            if p["bank_account"] and p["bank_account"] == cc["bank_account"]:
                print("PREV BANK COLLIDE", vid, rr)
            if p["tax_id"] and p["tax_id"] == cc["tax_id"]:
                print("PREV TAX COLLIDE", vid, rr)
