"""The app's filing library never holds a sealed filing (D68)."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import load_library  # noqa: E402


def _set(root: Path, name: str, filings: dict[str, tuple[str, str]]) -> None:
    folder = root / name
    (folder / "raw").mkdir(parents=True)
    manifest = {}
    for key, (split, profile) in filings.items():
        data = key.encode()
        (folder / "raw" / f"{key}.htm").write_bytes(data)
        manifest[key] = {"file": f"{key}.htm", "split": split, "profile": profile, "company": key, "sha256": hashlib.sha256(data).hexdigest()}
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_sealed_filings_stay_out_and_so_do_banks(tmp_path: Path) -> None:
    _set(tmp_path, "eval/wide", {"keep": ("dev", "us-commercial"), "shut": ("sealed", "us-commercial"), "bank": ("dev", "us-bank")})
    assert [m["company"] for _, m in load_library.library_files(tmp_path)] == ["keep"]


def test_a_copy_of_a_sealed_filing_in_another_set_stays_out(tmp_path: Path) -> None:
    """Georgia Power (sealed) and Southern Company (tuning) are one combined filing, listed under each."""
    _set(tmp_path, "eval/wide", {"same": ("sealed", "us-commercial")})
    _set(tmp_path, "eval/vocab", {"same": ("dev", "us-commercial")})
    assert load_library.library_files(tmp_path) == []


def test_a_sample_takes_every_industry_in_turn_and_repeats_exactly() -> None:
    files = [(Path(f"{s}{i}.htm"), {"sector": s, "file": f"{s}{i}"}) for s in ("energy", "retail") for i in range(5)]
    picked = load_library.sample(files, 4)
    assert sorted(m["sector"] for _, m in picked) == ["energy", "energy", "retail", "retail"]
    assert load_library.sample(files, 4) == picked


def test_no_real_sealed_filing_is_in_the_library() -> None:
    sealed = load_library.sealed_hashes(ROOT)
    assert sealed
    assert not sealed & {m.get("sha256") for _, m in load_library.library_files(ROOT)}


def test_a_company_name_broken_across_lines_is_shown_on_one_line() -> None:
    from spreader.company import detect_filing

    html = '<ix:nonNumeric name="dei:EntityRegistrantName">Xmax\nInc.</ix:nonNumeric><ix:nonNumeric name="dei:DocumentType">10-K</ix:nonNumeric>'
    assert detect_filing(html.encode())["company_name"] == "Xmax Inc."


def test_title_case_does_not_capitalise_after_an_apostrophe() -> None:
    from spreader.company import detect_filing

    html = '<ix:nonNumeric name="dei:EntityRegistrantName">THE WENDY\'S COMPANY</ix:nonNumeric><ix:nonNumeric name="dei:DocumentType">10-K</ix:nonNumeric>'
    assert detect_filing(html.encode())["company_name"] == "The Wendy's Company"

