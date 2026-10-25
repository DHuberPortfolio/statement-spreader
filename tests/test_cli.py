"""The `spreader` command that pyproject.toml declares (it pointed at a module that did not exist)."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest
from openpyxl import load_workbook

from conftest import statement_html
from spreader import cli
from test_redteam import HEAD, IS


def test_the_declared_entry_point_exists() -> None:
    scripts = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text())["project"]["scripts"]
    module, _, func = scripts["spreader"].partition(":")
    assert module == "spreader.cli" and callable(getattr(cli, func))


def test_spread_writes_json_and_xlsx(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src = tmp_path / "is.htm"
    src.write_text(statement_html("STATEMENTS OF OPERATIONS", "(In thousands)", HEAD, IS), encoding="utf-8")
    assert cli.main(["spread", str(src)]) == 0
    out = json.loads((tmp_path / "is.spread.json").read_text(encoding="utf-8"))
    rev = [v for v in out["spread"]["values"] if v["line"] == "revenue" and v["period"] == "2025-12-31/12M"]
    assert rev and rev[0]["value"] == "400000"
    assert out["meta"]["approved"] is None
    assert "income_statement" in capsys.readouterr().out
    assert cli.main(["spread", str(src), "--out", str(tmp_path / "is.xlsx")]) == 0
    assert load_workbook(tmp_path / "is.xlsx").sheetnames


def test_spread_refuses_a_file_without_tables(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src = tmp_path / "empty.htm"
    src.write_text("<html><body><p>No statements here.</p></body></html>", encoding="utf-8")
    assert cli.main(["spread", str(src)]) == 2
    assert "No tables with numbers" in capsys.readouterr().err
    assert not (tmp_path / "empty.spread.json").exists()
