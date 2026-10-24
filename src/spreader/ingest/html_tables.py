"""HTML (including SEC inline XBRL filings) -> DocumentIR.

What it deliberately ignores:
- Inline XBRL tags. They are a ready-made answer key, and a private company's statements will
  not have them, so the extractor reads only the visible text, as a person would. The evaluator
  reads the tags separately (evaluation/ixbrl_truth.py).
- Hidden content (display:none, <script>, <style>). Text a person cannot see must not become a
  number in a spread; hidden rows are also a way to smuggle values or instructions into a file.
"""

from __future__ import annotations

import re

from lxml import etree, html

from ..contracts import DocumentIR, RawRow, RawTable, SourceFormat, SourceRef, Token
from ..numbers import clean_text, is_amount_like
from . import IngestError, doc_id_for
from .paths import element_path

_HIDDEN = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*(hidden|collapse)|font-size\s*:\s*0(?![.\d])|opacity\s*:\s*0(?![.\d]*[1-9])"
    r"|(?:left|top|text-indent|margin-left|margin-top)\s*:\s*-\d{3,}|clip\s*:\s*rect\(\s*0|transform\s*:\s*scale\(\s*0\s*\)"
    r"|(?:max-)?height\s*:\s*0(?![.\d])[^;]*;?.*overflow\s*:\s*hidden|overflow\s*:\s*hidden.*(?:max-)?height\s*:\s*0(?![.\d])",
    re.I)
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_CSS_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_HIDDEN_SELECTORS: set[str] = set()  # set per document from its <style> blocks (see read_html)


def _normalise_css(style: str) -> str:
    """Remove comments and escapes so "display:/**/none" and "d\\isplay:none" read as written."""
    style = _CSS_COMMENT.sub("", style)
    style = re.sub(r"\\([0-9a-fA-F]{1,6}\s?)", lambda m: chr(int(m.group(1), 16)) if int(m.group(1), 16) < 0x110000 else "", style)
    return style.replace("\\", "")


def _stylesheet_hidden(root: etree._Element) -> set[str]:
    """Class, id and tag selectors that a <style> block hides (".x{display:none}")."""
    hidden: set[str] = set()
    for el in root.iter():
        if _local(el.tag) != "style":
            continue
        css = _normalise_css("".join(el.itertext()))
        for selectors, body in _CSS_RULE.findall(css):
            if _HIDDEN.search(body):
                for sel in selectors.split(","):
                    last = sel.strip().split()[-1] if sel.strip() else ""
                    if last:
                        hidden.add(last.lower())
    return hidden
_INDENT = re.compile(r"(padding-left|text-indent|margin-left)\s*:\s*(-?[\d.]+)\s*(pt|px|em|in|rem|%)?", re.I)
_BOLD = re.compile(r"font-weight\s*:\s*(bold|[6-9]00)", re.I)
_SKIP_TAGS = {"script", "style", "head", "title", "noscript", "template"}
CONTEXT_CHARS = 700
MAX_GRID_CELLS = 200_000


def _local(tag: object) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1].rsplit(":", 1)[-1].lower()


def _hidden(el: etree._Element) -> bool:
    style = _normalise_css(el.get("style") or "")
    tag = el.tag.lower() if isinstance(el.tag, str) else ""
    if _HIDDEN_SELECTORS:
        names = {f".{c.lower()}" for c in (el.get("class") or "").split()}
        if el.get("id"):
            names.add(f"#{el.get('id', '').lower()}")
        names.add(_local(el.tag))
        if names & _HIDDEN_SELECTORS:
            return True
    # ix:header holds inline XBRL's hidden facts; an HTML5 <header> is ordinary visible content.
    return bool(_HIDDEN.search(style)) or el.get("hidden") is not None or tag.endswith("ix:header")


def _visible_text(el: etree._Element) -> str:
    """Text of an element, skipping hidden descendants (iXBRL puts its hidden facts in ix:header)."""
    parts: list[str] = []

    def walk(node: etree._Element) -> None:
        if _local(node.tag) in _SKIP_TAGS or _hidden(node):
            if node.tail:
                parts.append(node.tail)
            return
        if node.text:
            parts.append(node.text)
        for child in node:
            walk(child)
        if node is not el and node.tail:
            parts.append(node.tail)

    walk(el)
    return clean_text(" ".join(parts))


def _to_points(value: float, unit: str | None) -> float:
    unit = (unit or "px").lower()
    return {"pt": 1.0, "px": 0.75, "em": 12.0, "rem": 12.0, "in": 72.0, "%": 0.0}.get(unit, 0.75) * value


def _indent_and_bold(td: etree._Element) -> tuple[float, bool]:
    indent = 0.0
    bold = False
    for node in td.iter():
        if not isinstance(node.tag, str):
            continue
        style = node.get("style") or ""
        for prop, num, unit in _INDENT.findall(style):
            pts = _to_points(float(num), unit)
            if prop.lower() == "text-indent" and pts < 0:
                continue  # a hanging indent wraps lines; it does not move the label
            indent += pts
        if _BOLD.search(style) or _local(node.tag) in {"b", "strong"}:
            bold = True
    text = td.text or ""
    leading = len(text) - len(text.lstrip("  "))
    return indent + leading * 3.0, bold


def _merge_fragments(tokens: list[Token]) -> list[Token]:
    """Join the pieces SEC tables split across cells: "$" | "1,234" and "(1,234" | ")"."""
    out: list[Token] = []
    pending_prefix: Token | None = None
    for tok in tokens:
        t = tok.text
        if t in {"$", "€", "£", "(", "($", "$("}:
            pending_prefix = tok if pending_prefix is None else _join(pending_prefix, tok, "")
            continue
        if pending_prefix is not None:
            tok = _join(pending_prefix, tok, " ")
            pending_prefix = None
        if out and (t in {")", ")%", "%", "%)"} or (t.startswith(")") and len(t) <= 3)):
            out[-1] = _join(out[-1], tok, "")
            continue
        out.append(tok)
    if pending_prefix is not None and pending_prefix.text not in {"$", "€", "£"}:
        out.append(pending_prefix)
    return out


def _join(a: Token, b: Token, sep: str) -> Token:
    text = (a.text + sep + b.text).strip()
    has_digits = any(ch.isdigit() for ch in b.text) or not any(ch.isdigit() for ch in a.text)
    ref = (b.ref if has_digits else a.ref).model_copy(update={"text": text})
    return Token(text=text, x0=min(a.x0, b.x0), x1=max(a.x1, b.x1), ref=ref)


def _table_rows(table: etree._Element, tree: etree._ElementTree, doc_id: str, t_index: int) -> list[RawRow]:
    rows: list[RawRow] = []
    occupied: dict[tuple[int, int], bool] = {}
    r_index = 0
    n_rows = sum(1 for tr in table.iter() if _local(tr.tag) == "tr")
    for tr in table.iter():
        if _local(tr.tag) != "tr":
            continue
        if _hidden(tr):
            continue
        # skip rows of nested tables: they belong to the inner table
        parent_table = next((a for a in tr.iterancestors() if _local(a.tag) == "table"), None)
        if parent_table is not table:
            continue
        col = 0
        tokens: list[Token] = []
        row_indent = 0.0
        row_bold = False
        first_text = True
        for td in tr:
            if _local(td.tag) not in {"td", "th"}:
                continue
            while occupied.get((r_index, col)):
                col += 1
            try:
                span = max(1, min(int(td.get("colspan") or 1), 50))
                rspan = max(1, min(int(td.get("rowspan") or 1), 50))
            except ValueError:
                span, rspan = 1, 1
            rspan = min(rspan, max(1, n_rows - r_index))  # a span cannot reach past the table
            for dr in range(1, rspan):
                for dc in range(span):
                    occupied[(r_index + dr, col + dc)] = True
            if len(occupied) > MAX_GRID_CELLS:
                raise IngestError("A table's row and column spans describe an implausibly large grid; not read")
            if _hidden(td):
                col += span
                continue
            text = _visible_text(td)
            if text:
                ref = SourceRef(doc_id=doc_id, format=SourceFormat.HTML, table=t_index, row=r_index,
                                xpath=element_path(td), text=text)
                tokens.append(Token(text=text, x0=float(col), x1=float(col + span), ref=ref))
                if first_text:
                    row_indent, row_bold = _indent_and_bold(td)
                    first_text = False
                elif not row_bold:
                    _, row_bold = _indent_and_bold(td)
            col += span
        tokens = _merge_fragments(tokens)
        rows.append(RawRow(index=r_index, tokens=tokens, indent=row_indent, bold=row_bold))
        r_index += 1
    return rows


def read_html(filename: str, data: bytes) -> DocumentIR:
    doc_id = doc_id_for(data)
    parser = html.HTMLParser(remove_comments=True, remove_pis=True, no_network=True, huge_tree=True,
                             encoding="utf-8")
    try:
        root = html.document_fromstring(data, parser=parser)
    except (etree.ParserError, ValueError) as exc:
        raise IngestError(f"Could not parse HTML: {exc}") from exc
    tree = root.getroottree()
    global _HIDDEN_SELECTORS
    _HIDDEN_SELECTORS = _stylesheet_hidden(root)
    tables: list[RawTable] = []
    warnings: list[str] = []
    buffer: list[str] = []
    buffer_len = 0

    preface: list[str] = []

    def reset_buffer() -> None:
        nonlocal buffer_len
        buffer.clear()
        buffer_len = 0

    def push(text: str | None) -> None:
        nonlocal buffer_len
        if text and text.strip():
            if not tables and sum(len(x) for x in preface) < 6000:
                preface.append(text)
            buffer.append(text)
            buffer_len += len(text)
            while buffer_len > CONTEXT_CHARS * 3 and len(buffer) > 1:
                buffer_len -= len(buffer.pop(0))

    def walk(node: etree._Element) -> None:
        tag = _local(node.tag)
        if tag in _SKIP_TAGS or _hidden(node):
            push(node.tail)
            return
        if tag == "table":
            context = clean_text(" ".join(buffer))[-CONTEXT_CHARS:]
            try:
                rows = _table_rows(node, tree, doc_id, len(tables))
            except IngestError as exc:
                warnings.append(str(exc))
                push(node.tail)
                return
            value_tokens = sum(1 for r in rows for t in r.tokens if is_amount_like(t.text))
            if len(rows) >= 2 and value_tokens >= 2:
                tables.append(RawTable(index=len(tables), rows=rows, context=context))
                # The next table's context starts here: a title above one table ("Unaudited pro
                # forma ...") must not become the title of the table after it.
                reset_buffer()
            else:
                push(_visible_text(node))  # a layout table: its text is context for what follows
            push(node.tail)
            return
        push(node.text)
        for child in node:
            walk(child)
        push(node.tail)

    walk(root)
    if not tables:
        raise IngestError("No tables with numbers were found in this HTML file")
    # Re-number tables so SourceRef.table matches the RawTable index.
    for i, t in enumerate(tables):
        if t.index != i:  # pragma: no cover - indexes are assigned in order above
            t.index = i
    return DocumentIR(doc_id=doc_id, filename=filename, format=SourceFormat.HTML, tables=tables, warnings=warnings,
                      preface=clean_text(" ".join(preface))[:6000])
