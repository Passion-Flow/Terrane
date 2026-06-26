"""Terrane Parse -- Excel DrawingML flow extraction (xlsx shapes + connectors -> Mermaid). See design/11-allfile-parsing-roadmap.md F2 / G4.

Excel is the roadmap's explicit EXCEPTION to "never serialise topology as text": a flowchart drawn on the
sheet canvas carries its edges as *explicit* connector references (``a:stCxn``/``a:endCxn`` -> shape id), so the
directed graph is recoverable DETERMINISTICALLY (no pixel geometry, no VLM edge inference). We read the raw
``xl/drawings/drawingN.xml`` from the xlsx zip with stdlib ``zipfile`` + ``xml.etree`` (no new dependency;
openpyxl drops sp/cxnSp on read), build node + edge lists, and serialise a Mermaid ``flowchart TD`` block.

Output per sheet is assembled by ``engine._parse_xlsx``: (a) the Mermaid flowchart (if shapes/connectors exist)
then (b) the cleaned cell grid.
"""

from __future__ import annotations

import re
import zipfile
from xml.etree import ElementTree as ET

import structlog

log = structlog.get_logger("terrane.parse.xlsx_drawing")

# DrawingML namespaces (spreadsheetDrawing container + the shared "a:" main vocabulary).
_NS_XDR = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
_NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_X = "{" + _NS_XDR + "}"
_A = "{" + _NS_A + "}"

# prstGeom preset -> Mermaid node shape. Decision/diamond -> {..}; terminator -> ([..]); io -> [/../]; else [..].
_DECISION = {"flowChartDecision", "diamond"}
_TERMINATOR = {"flowChartTerminator", "flowChartConnector"}
_IO = {"flowChartInputOutput", "parallelogram"}

# Shape presets that are pure flow-glue (tiny junction dots / off-page connectors), not real labelled steps.
# Kept as nodes only when they participate in an edge; never contribute "step" text on their own.

_FULLWIDTH_SPACE = "　"


class _Shape:
    __slots__ = ("sid", "text", "prst", "from_col", "from_row", "to_col", "to_row")

    def __init__(self, sid: str, text: str, prst: str,
                 from_col: int, from_row: int, to_col: int, to_row: int) -> None:
        self.sid = sid
        self.text = text
        self.prst = prst
        self.from_col = from_col
        self.from_row = from_row
        self.to_col = to_col
        self.to_row = to_row

    @property
    def sort_key(self) -> tuple[int, int]:
        # Top-to-bottom then left-to-right by anchor origin -> deterministic node order.
        return (self.from_row, self.from_col)


class _Edge:
    __slots__ = ("src", "dst", "label", "inferred")

    def __init__(self, src: str, dst: str, label: str, inferred: bool) -> None:
        self.src = src
        self.dst = dst
        self.label = label
        self.inferred = inferred


def _clean_text(s: str) -> str:
    """Collapse runs of whitespace introduced by paragraph joins; keep CJK / full-width content intact."""
    if not s:
        return ""
    # Normalise full-width space to a normal space only for trimming purposes; keep internal text faithful.
    s = s.replace("\r", "")
    # Collapse 3+ newlines, strip outer whitespace (incl. full-width).
    s = re.sub(r"\n{2,}", "\n", s)
    return s.strip().strip(_FULLWIDTH_SPACE).strip()


def _shape_text(sp: ET.Element) -> str:
    """Concatenate ``a:t`` runs, inserting a newline between ``a:p`` paragraphs."""
    parts: list[str] = []
    txbody = sp.find(_X + "txBody")
    if txbody is None:
        return ""
    for p in txbody.findall(_A + "p"):
        run = "".join(t.text or "" for t in p.iter(_A + "t"))
        parts.append(run)
    return _clean_text("\n".join(parts))


def _anchor_cell(anchor: ET.Element, tag: str) -> tuple[int, int]:
    """Return (col, row) 0-based from an ``xdr:from`` / ``xdr:to`` child. Missing -> (0, 0)."""
    node = anchor.find(_X + tag)
    if node is None:
        return (0, 0)
    col = node.find(_X + "col")
    row = node.find(_X + "row")
    try:
        c = int(col.text) if col is not None and col.text else 0
        r = int(row.text) if row is not None and row.text else 0
    except (TypeError, ValueError):
        c = r = 0
    return (c, r)


def _collect(anchor: ET.Element, shapes: dict[str, _Shape], edges: list[_Edge]) -> None:
    """Walk one top-level anchor, collecting every ``xdr:sp`` (node) and ``xdr:cxnSp`` (edge), recursing into
    ``xdr:grpSp`` groups. Anchor (col,row) of the enclosing anchor is used as the position for direct children;
    grouped shapes inherit the group anchor (good enough for stable ordering)."""
    fc, fr = _anchor_cell(anchor, "from")
    tc, tr = _anchor_cell(anchor, "to")

    def _walk(el: ET.Element) -> None:
        for child in el:
            tag = child.tag
            if tag == _X + "sp":
                cn = child.find("." + _X + "nvSpPr/" + _X + "cNvPr")
                if cn is None:
                    cn = next((e for e in child.iter(_X + "cNvPr")), None)
                if cn is None:
                    continue
                sid = cn.get("id")
                if sid is None:
                    continue
                geom = child.find("." + _X + "spPr/" + _A + "prstGeom")
                prst = geom.get("prst", "") if geom is not None else ""
                shapes[sid] = _Shape(sid, _shape_text(child), prst, fc, fr, tc, tr)
            elif tag == _X + "cxnSp":
                st = next((e for e in child.iter(_A + "stCxn")), None)
                en = next((e for e in child.iter(_A + "endCxn")), None)
                label = ""
                txbody = child.find(_X + "txBody")
                if txbody is not None:
                    label = _clean_text("".join(t.text or "" for t in txbody.iter(_A + "t")))
                if st is not None and en is not None:
                    src, dst = st.get("id"), en.get("id")
                    if src and dst:
                        # Honour arrow direction: tailEnd=arrow means flow st->end (default); a headEnd arrow on
                        # the start side means the visual arrow points back -> swap so edge follows the arrow.
                        if _arrow_reversed(child):
                            src, dst = dst, src
                        edges.append(_Edge(src, dst, label, inferred=False))
                # one-sided / no-endpoint connectors: geometry fallback handled after all shapes are known.
                elif st is not None or en is not None:
                    known = (st if st is not None else en).get("id")
                    if known:
                        # mark a dangling half-edge for geometry snapping later
                        edges.append(_Edge(known, "", label, inferred=True))
            elif tag == _X + "grpSp":
                _walk(child)
            else:
                # twoCellAnchor wraps a single sp/cxnSp/grpSp/pic; recurse generically.
                if tag in (_X + "pic", _X + "graphicFrame"):
                    continue
                _walk(child)

    _walk(anchor)


def _arrow_reversed(cxn: ET.Element) -> bool:
    """Connector arrowheads: if the line has a headEnd arrow but no tailEnd arrow, the visible arrow points at the
    *start* connection -> the flow direction is end->start, so callers should swap."""
    ln = cxn.find("." + _X + "spPr/" + _A + "ln")
    if ln is None:
        return False
    head = ln.find(_A + "headEnd")
    tail = ln.find(_A + "tailEnd")
    head_arrow = head is not None and head.get("type", "none") not in ("", "none")
    tail_arrow = tail is not None and tail.get("type", "none") not in ("", "none")
    return head_arrow and not tail_arrow


def _snap_dangling(edges: list[_Edge], shapes: dict[str, _Shape]) -> None:
    """For half-connectors (only one endpoint referenced), snap the free end to the nearest shape by anchor
    distance. Marked inferred. Edges that cannot be resolved are dropped."""
    nodes = list(shapes.values())
    resolved: list[_Edge] = []
    for e in edges:
        if e.dst:
            resolved.append(e)
            continue
        src = shapes.get(e.src)
        if src is None:
            continue
        # nearest other shape by anchor manhattan distance
        best = None
        best_d = None
        for s in nodes:
            if s.sid == e.src:
                continue
            d = abs(s.from_row - src.from_row) * 100 + abs(s.from_col - src.from_col)
            if best_d is None or d < best_d:
                best_d, best = d, s
        if best is not None:
            e.dst = best.sid
            resolved.append(e)
    edges[:] = resolved


def _node_id(idx: int) -> str:
    return f"N{idx}"


_MERMAID_ESCAPE = {
    '"': "'",   # quotes inside a "..."-quoted Mermaid label break parsing -> use single quote
}


def _mermaid_label(text: str, placeholder: str) -> str:
    if not text:
        return placeholder
    # Mermaid breaks on raw " and newlines inside a quoted label; use <br/> for line breaks, ' for quotes.
    out = text
    for k, v in _MERMAID_ESCAPE.items():
        out = out.replace(k, v)
    out = out.replace("\n", "<br/>")
    # backslashes and pipes can also confuse the renderer
    out = out.replace("\\", "/").replace("|", "/")
    return out


def _wrap(label: str, prst: str) -> str:
    """Wrap a Mermaid node label in the shape that matches the DrawingML preset."""
    q = f'"{label}"'
    if prst in _DECISION:
        return "{" + q + "}"
    if prst in _IO:
        return "[/" + q + "/]"
    if prst in _TERMINATOR:
        return "([" + q + "])"
    return "[" + q + "]"


def _build_mermaid(shapes: dict[str, _Shape], edges: list[_Edge]) -> tuple[str, int, int]:
    """Serialise shapes+edges to a Mermaid ``flowchart TD`` block. Returns (text, node_count, edge_count).

    Only shapes that carry text OR participate in an edge become nodes (drops decorative glue). Nodes are ordered
    by anchor (row, col) for stable output and assigned ids N1.., so the same workbook always serialises the same.
    """
    # Which shapes are referenced by an edge?
    referenced: set[str] = set()
    for e in edges:
        referenced.add(e.src)
        if e.dst:
            referenced.add(e.dst)

    keep = [s for s in shapes.values() if s.text or s.sid in referenced]
    keep.sort(key=lambda s: (s.sort_key, s.sid))
    if not keep and not edges:
        return ("", 0, 0)

    sid_to_node: dict[str, str] = {}
    for i, s in enumerate(keep, 1):
        sid_to_node[s.sid] = _node_id(i)

    lines = ["```mermaid", "flowchart TD"]
    # Declare every node once with its label, so even isolated (un-connected) steps appear.
    for s in keep:
        nid = sid_to_node[s.sid]
        label = _mermaid_label(s.text, placeholder=f"step {nid}")
        lines.append(f"    {nid}{_wrap(label, s.prst)}")

    edge_count = 0
    seen_edges: set[tuple[str, str, str]] = set()
    for e in edges:
        a = sid_to_node.get(e.src)
        b = sid_to_node.get(e.dst) if e.dst else None
        if a is None or b is None:
            continue
        key = (a, b, e.label)
        if key in seen_edges:
            continue
        seen_edges.add(key)
        lbl = _mermaid_label(e.label, placeholder="") if e.label else ""
        arrow = f"-->|{lbl}|" if lbl else "-->"
        suffix = "  %% inferred" if e.inferred else ""
        lines.append(f"    {a} {arrow} {b}{suffix}")
        edge_count += 1

    lines.append("```")
    return ("\n".join(lines), len(keep), edge_count)


def _drawing_for_sheet(zf: zipfile.ZipFile, sheet_path: str) -> str | None:
    """Resolve ``xl/worksheets/sheetN.xml`` -> its drawing part via the worksheet rels + the ``<drawing r:id>``."""
    # sheet_path like "xl/worksheets/sheet1.xml"
    base = sheet_path.rsplit("/", 1)[-1]
    rels_path = sheet_path.rsplit("/", 1)[0] + "/_rels/" + base + ".rels"
    try:
        sheet_xml = zf.read(sheet_path)
    except KeyError:
        return None
    try:
        sroot = ET.fromstring(sheet_xml)
    except ET.ParseError:
        return None
    drawing_el = next((e for e in sroot.iter() if e.tag.endswith("}drawing")), None)
    if drawing_el is None:
        return None
    rid = drawing_el.get("{" + _NS_R + "}id")
    if not rid:
        return None
    try:
        rels = ET.fromstring(zf.read(rels_path))
    except (KeyError, ET.ParseError):
        return None
    for rel in rels:
        if rel.get("Id") == rid:
            target = rel.get("Target", "")
            # Normalise "../drawings/drawing1.xml" relative to xl/worksheets/
            return _resolve(sheet_path.rsplit("/", 1)[0], target)
    return None


def _resolve(base_dir: str, target: str) -> str:
    parts = base_dir.split("/")
    for seg in target.split("/"):
        if seg == "..":
            parts = parts[:-1]
        elif seg in ("", "."):
            continue
        else:
            parts.append(seg)
    return "/".join(parts)


def extract_sheet_flow(zf: zipfile.ZipFile, sheet_path: str) -> tuple[str, int, int]:
    """Extract a Mermaid flowchart for one worksheet. Returns (mermaid_block, node_count, edge_count).

    ``mermaid_block`` is "" when the sheet has no shapes/connectors. Never raises -- on any malformed part it
    returns ("", 0, 0) so the cell-grid path always still runs."""
    try:
        drawing_path = _drawing_for_sheet(zf, sheet_path)
        if not drawing_path:
            return ("", 0, 0)
        try:
            dxml = zf.read(drawing_path)
        except KeyError:
            return ("", 0, 0)
        root = ET.fromstring(dxml)
        shapes: dict[str, _Shape] = {}
        edges: list[_Edge] = []
        for anchor in root:
            # top-level children are twoCellAnchor / oneCellAnchor / absoluteAnchor
            _collect(anchor, shapes, edges)
        _snap_dangling(edges, shapes)
        return _build_mermaid(shapes, edges)
    except (ET.ParseError, KeyError, ValueError) as exc:  # noqa: BLE001
        log.warning("xlsx_drawing_extract_failed", sheet=sheet_path, error=str(exc))
        return ("", 0, 0)
