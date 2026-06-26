"""Self-developed section-hierarchy inference — font/numbering/geometry -> levels -> stack tree.

Turns a reading-ordered block list into a section tree (the chunk tree RAG needs), with no model:
detect heading candidates by typography + numbering + geometry, assign a level (numbering depth when
present, else style-signature rank), then a single stack pass induces the tree (HiPS arXiv:2509.00909).
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

from app.services.parse.structure.box import Box

# numbering patterns -> explicit depth
_NUM_DOTTED = re.compile(r"^\s*(\d+(?:\.\d+)*)[.)]?\s+\S")          # 1 / 1.2 / 1.2.3
_NUM_CHAPTER = re.compile(r"^\s*(chapter|章|第[一二三四五六七八九十百\d]+[章节])\b", re.I)
_NUM_APPENDIX = re.compile(r"^\s*(appendix|附录)\b", re.I)
_NUM_ROMAN = re.compile(r"^\s*([IVXLC]+)[.)]\s+\S")
_BULLET = re.compile(r"^\s*[•·\-\*▪◦]\s+")


@dataclass
class Node:
    title: str = ""
    level: int = 0
    boxes: list[Box] = field(default_factory=list)     # content blocks under this node
    children: list["Node"] = field(default_factory=list)
    page_start: int | None = None
    page_end: int | None = None


def _numbering_depth(text: str) -> int | None:
    """Return heading depth from a leading numbering pattern, or None if not numbered like a heading."""
    if _BULLET.match(text):
        return None
    m = _NUM_DOTTED.match(text)
    if m:
        return text[:60].count(".", 0, m.end(1) - m.start(1)) + 1 if "." in m.group(1) else 1
    if _NUM_CHAPTER.match(text):
        return 1
    if _NUM_APPENDIX.match(text) or _NUM_ROMAN.match(text):
        return 1
    return None


def _style_sig(b: Box) -> tuple:
    return (round(b.font_size), b.bold, b.text[:40].isupper())


def _is_heading_candidate(b: Box, body_size: float) -> bool:
    t = b.text.strip()
    if not t or len(t) > 200 or _BULLET.match(t):
        return False
    if b.label == "title":
        return True
    if _numbering_depth(t) is not None:
        return True
    if b.font_size > body_size * 1.05:
        return True
    if b.bold and len(t) < 80:
        return True
    return False


def build_hierarchy(ordered: list[Box], page_of=None) -> Node:
    """Build the section tree from reading-ordered boxes. page_of(box)->int optional for page ranges."""
    root = Node(title="", level=0)
    if not ordered:
        return root

    sizes = [b.font_size for b in ordered if b.font_size > 0]
    body_size = statistics.mode(sizes) if sizes else 0.0

    headings = [b for b in ordered if _is_heading_candidate(b, body_size)]
    # style-signature -> level rank (used when numbering is absent)
    sigs = sorted({_style_sig(b) for b in headings},
                  key=lambda s: (-s[0], not s[1], not s[2]))   # bigger font, bold, caps => higher
    sig_level = {s: i + 1 for i, s in enumerate(sigs)}

    def level_of(b: Box) -> int:
        d = _numbering_depth(b.text.strip())
        if d is not None:
            return d
        return sig_level.get(_style_sig(b), 1)

    heading_ids = {id(b) for b in headings}
    stack: list[Node] = [root]
    for b in ordered:
        pg = page_of(b) if page_of else None
        if id(b) in heading_ids:
            lvl = level_of(b)
            while len(stack) > 1 and stack[-1].level >= lvl:
                stack.pop()
            node = Node(title=b.text.strip()[:300], level=lvl, page_start=pg, page_end=pg)
            stack[-1].children.append(node)
            stack.append(node)
        else:
            cur = stack[-1]
            cur.boxes.append(b)
            if pg is not None:
                cur.page_start = pg if cur.page_start is None else min(cur.page_start, pg)
                cur.page_end = pg if cur.page_end is None else max(cur.page_end, pg)
    # propagate page ranges up
    def _fix(n: Node):
        for c in n.children:
            _fix(c)
            if c.page_start is not None:
                n.page_start = c.page_start if n.page_start is None else min(n.page_start, c.page_start)
                n.page_end = c.page_end if n.page_end is None else max(n.page_end, c.page_end)
    _fix(root)
    return root
