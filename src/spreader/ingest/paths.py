"""A parser-independent path to an element: /html[1]/body[1]/div[547]/table[1]/tr[5]/td[3].

The HTML reader parses with lxml's HTML parser and the answer-key builder with its XML parser
(inline XBRL is XHTML with namespaces). Their own getpath() strings differ, so both use this
path, built from local tag names and positions among same-named siblings, to point at a cell.
"""

from __future__ import annotations

from lxml import etree


def local_name(tag: object) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1].rsplit(":", 1)[-1].lower()


def element_path(el: etree._Element) -> str:
    parts: list[str] = []
    node: etree._Element | None = el
    while node is not None and isinstance(node.tag, str):
        name = local_name(node.tag)
        idx = 1 + sum(1 for sib in node.itersiblings(preceding=True) if local_name(sib.tag) == name)
        parts.append(f"{name}[{idx}]")
        node = node.getparent()
    return "/" + "/".join(reversed(parts))
