from __future__ import annotations

import pytest

from spreader.profile import Profile, load_profile


@pytest.fixture(scope="session")
def profile() -> Profile:
    return load_profile()


def statement_html(title: str, unit: str, header: list[str], rows: list[tuple], hidden: list[tuple] | None = None,
                   before: str = "") -> str:
    """A small statement table in the style of an SEC filing ("$" and ")" in their own cells)."""
    def cells(vals: tuple) -> str:
        out = []
        for v in vals:
            if v is None:
                out.append("<td></td><td></td><td></td>")
            elif isinstance(v, str) and v.startswith("("):
                out.append(f"<td></td><td>{v[:-1]}</td><td>)</td>")
            else:
                out.append(f"<td>$</td><td>{v}</td><td></td>")
        return "".join(out)

    head = "".join(f'<td colspan="3">{h}</td>' for h in header)
    body = []
    for r in rows:
        label, *vals = r
        style = ' style="padding-left:12pt"' if label.startswith("  ") else ""
        body.append(f"<tr><td{style}>{label.strip()}</td>{cells(tuple(vals))}</tr>")
    for r in hidden or []:
        label, *vals = r
        body.append(f'<tr style="display:none"><td>{label}</td>{cells(tuple(vals))}</tr>')
    return (f"<html><body>{before}<p>{title}</p><p>{unit}</p><table>"
            f"<tr><td></td>{head}</tr>{''.join(body)}</table></body></html>")
