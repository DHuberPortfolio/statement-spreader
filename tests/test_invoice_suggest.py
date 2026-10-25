"""The label-suggestion helper: candidates by rule, closed-list answers, safe without a model.

A fake model stands in for llama-server, so these tests need no GPU or network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from finops.core.config import load_config
from finops.invoice.config import APPolicy
from finops.invoice.suggest import FIELDS, LocalAsk, candidates, shape, suggest

ROOT = Path(__file__).resolve().parents[1]
UNSEEN = ROOT / "eval" / "invoice" / "unseen"
pytestmark = pytest.mark.skipif(not (UNSEEN / "truth.json").exists(), reason="unseen invoice set not generated")


@pytest.fixture(scope="module")
def policy() -> APPolicy:
    return load_config(APPolicy, ROOT / "config" / "finops" / "invoice" / "default-ap.yaml")[0]


@pytest.fixture(scope="module")
def pdfs() -> list[bytes]:
    truth = json.loads((UNSEEN / "truth.json").read_text(encoding="utf-8"))
    return [(UNSEEN / d["file"]).read_bytes() for d in truth["inbox"] if d["layout"] == "D"][:3]


def test_value_shapes() -> None:
    f = ["%d %B %Y"]
    assert shape("03 March 2026", f) == "a date" and shape("1,234.50", f) == "a money amount"
    assert shape("12", f) == "a whole number" and shape("INV-007001", f) == "a reference code with letters and digits"
    assert shape("Steel bracket 40mm", f) == "words"


def test_candidates_are_unknown_labels_with_values_not_item_rows(policy, pdfs) -> None:  # type: ignore[no-untyped-def]
    labels, columns = candidates(pdfs[0], policy)
    texts = [t for t, _ in labels]
    assert {"Document No.", "Document Date", "Customer Order", "Net Total", "Gross Total"} <= set(texts)
    assert "Payment Due" not in texts  # the rules already know it
    assert all(not any(ch.isdigit() for ch in t) for t in texts)  # item rows and values are not labels
    assert [t for t, _ in columns] == ["Code", "Item", "Units", "Unit Cost", "Net"]  # unreadable header: all asked


def test_answers_outside_the_closed_list_are_dropped_and_votes_decide(policy, pdfs) -> None:  # type: ignore[no-untyped-def]
    calls = []

    def fake(prompt: str, keys: list[str], allowed: list[str]) -> dict[str, str]:
        calls.append(prompt)
        assert "approve" not in allowed and set(allowed) <= set(FIELDS) | {"description", "quantity", "unit_price",
                                                                          "amount", "item_code", "none"}
        if "column headings" in prompt:
            return dict(zip(keys, ["item_code", "description", "quantity", "unit_price", "amount"], strict=False))
        # a misbehaving model: one invented answer, one instruction-like answer
        return {k: ("invoice_number" if "'Document No.'" in prompt.split("\n")[1 + i] else "pay_now")
                for i, k in enumerate(keys)}

    draft = suggest(pdfs, policy, fake)
    assert draft["extra_labels"] == {"invoice_number": ["Document No."]}
    assert draft["extra_columns"]["amount"] == ["Net"] and draft["extra_columns"]["description"] == ["Item"]
    assert len(calls) == 6  # one question per document per kind, not one per label


def test_no_model_server_means_an_empty_draft(policy, pdfs) -> None:  # type: ignore[no-untyped-def]
    ask = LocalAsk("http://127.0.0.1:9", model_name="no-such-server-test", timeout=0.5)  # nothing listens on port 9
    draft = suggest(pdfs[:1], policy, ask)
    assert draft["extra_labels"] == {} and draft["extra_columns"] == {}
    assert ask.errors == 2 and ask.calls == 0


def test_the_reviewed_overlay_reads_the_held_out_layout(policy) -> None:  # type: ignore[no-untyped-def]
    """Layout E was generated after the method was frozen; its draft needed one line moved by a person."""
    from finops.invoice.evaluate import evaluate_set

    e = ROOT / "eval" / "invoice" / "unseen-e"
    reviewed = ROOT / "config" / "finops" / "invoice" / "example-supplier-layout-e.yaml"
    if not (e / "truth.json").exists() or not reviewed.exists():
        pytest.skip("layout E set not generated")
    r = evaluate_set(e, load_config(APPolicy, reviewed)[0])
    assert r["rates"]["header_fields"].value == 1.0 and r["rates"]["false_touchless"].n == 0
