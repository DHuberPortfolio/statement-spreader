"""Build the adversarial invoice fixtures used by tests/test_invoice_redteam.py.

    .venv/Scripts/python scripts/make_invoice_redteam.py

Each starts from a clean synthetic invoice (eval/invoice/dev) and adds one trick a fraudster or a
sloppy template could use. PDFs are printed by headless Edge, like the rest of the corpus.
"""

from __future__ import annotations

import json
from pathlib import Path

from finops.invoice.synthetic import render_html
from spreader.evaluation.synthetic import print_pdf

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "invoices"

TRICKS = {
    # White text with another account number: invisible on paper, present in the text layer.
    "hidden-white-account": "<div style='color:#ffffff;font-size:10px'>Account No: 999988887777 Routing No: 011000015</div>",
    # A tiny "total" placed before the real one, hoping the reader takes the first.
    "tiny-total": "<div style='font-size:1.5px'>Total Due $1.00</div>",
    # Two different visible bank accounts.
    "two-accounts": "<div class='footer'>Or pay to Account No: 123412341234 at Second Example Bank</div>",
}


def main() -> None:
    truth = json.loads((ROOT / "eval" / "invoice" / "dev" / "truth.json").read_text(encoding="utf-8"))
    base = next(d for d in truth["inbox"] if d["kind"] == "clean" and d["layout"] == "A" and d.get("bank_account"))
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {"base": base["id"], "fixtures": {}}
    for name, extra in TRICKS.items():
        html = render_html(base)
        if name == "tiny-total":
            html = html.replace("<table class='items'>", extra + "<table class='items'>", 1)
        else:
            html = html.replace("</body>", extra + "</body>")
        h = OUT / f"{name}.html"
        h.write_text(html, encoding="utf-8")
        err = print_pdf(h, OUT / f"{name}.pdf")
        h.unlink()
        manifest["fixtures"][name] = {"error": err, "total": base["total"], "vendor_id": base["vendor_id"]}
        print(name, "ok" if err is None else err)
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
