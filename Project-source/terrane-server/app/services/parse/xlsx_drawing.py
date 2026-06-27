"""Terrane Parse -- Excel DrawingML SWIMLANE flow extraction (xlsx shapes + connectors -> Mermaid). See
design/11-allfile-parsing-roadmap.md F2 / G4.

Excel is the roadmap's explicit EXCEPTION to "never serialise topology as text": a flowchart drawn on the
sheet canvas carries its edges as *explicit* connector references (``a:stCxn``/``a:endCxn`` -> shape id), so the
directed graph is recoverable DETERMINISTICALLY (no pixel geometry, no VLM edge inference). We read the raw
``xl/drawings/drawingN.xml`` from the xlsx zip with stdlib ``zipfile`` + ``xml.etree`` (no new dependency;
openpyxl drops sp/cxnSp on read), build node + edge lists, and serialise a Mermaid ``flowchart TD`` block.

These workbooks are Japanese システム間処理フロー (cross-system process flow) SWIMLANE diagrams. The faithful
representation is therefore NOT a flat graph but a swimlane chart:

  * The **lanes** are not shapes -- they are HEADER CELLS in the worksheet grid (a top-level "管理者 / 使用者 /
    BCW / 認証 / 審査 / 他システム" row over a finer sub-lane "WebApコンテナ / SQS / DB・S3 / TRUSTDOCK ..." row).
    Each header occupies a column position; the lane's column *range* runs from that column to the next header's.
  * Each flow **shape** is assigned to a lane by the column its anchor box centres on.
  * Above the lane header rows sits a **凡例 (legend / key)** block and a title table with ``#REF!`` cells -- both
    are EXCLUDED from the flow (the legend is the key, not the process; current output wrongly emitted its 26
    icons -- 機能名/オンライン機能/バッチ機能/データストア/コメント/開始条件... -- as flow nodes).
  * **Comment callouts** (``borderCallout1`` boxes, e.g. "アカウント特定キー、権限区分...") are annotations, not
    steps -- emitted as Mermaid ``%%`` notes, never as flow nodes.

We render one ``subgraph "lane"`` per lane (top-level Mermaid subgraphs render as swimlanes) holding that lane's
nodes, then the cross-lane edges (the connectors). Textless flow-glue (off-page connector dots / junctions) is
spliced through transitively so no ``step Nxx`` placeholder survives.

Output per sheet is assembled by ``engine._parse_xlsx``: (a) this Mermaid flowchart (if shapes/connectors exist)
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

# prstGeom preset -> Mermaid node shape. Decision/diamond -> {..}; terminator -> ([..]); io -> [/../]; db -> [(..)].
_DECISION = {"flowChartDecision", "diamond"}
_TERMINATOR = {"flowChartTerminator"}
_IO = {"flowChartInputOutput", "parallelogram"}
_DATASTORE = {"flowChartMagneticDisk", "flowChartOnlineStorage", "can", "cylinder"}

# Pure flow-glue: tiny junction / off-page connector dots. Carry no own label; when textless they are spliced
# through (pred -> succ) so the directed flow stays connected without leaving a textless placeholder node.
_GLUE = {"flowChartConnector", "flowChartOffpageConnector", "ellipse"}

# Comment / annotation callout presets -> emitted as notes, never as flow steps.
_CALLOUT = {
    "borderCallout1", "borderCallout2", "borderCallout3",
    "callout1", "callout2", "callout3",
    "wedgeRectCallout", "wedgeRoundRectCallout", "wedgeEllipseCallout", "cloudCallout",
}

_FULLWIDTH_SPACE = "　"

# Spreadsheet error codes (also handled in engine._cell_str) -- a lane header that is just "#REF!" is dropped.
_XLSX_ERRORS = frozenset({
    "#REF!", "#NAME?", "#VALUE!", "#DIV/0!", "#N/A", "#NULL!", "#NUM!", "#SPILL!", "#CALC!", "#GETTING_DATA",
})

# Legend label vocabulary: the 凡例 key of these templates. Used as a SECONDARY guard (the primary guard is
# position -- anything at/above the lane-header row is legend/title) so a stray legend shape anchored low cannot
# leak into the flow.
_LEGEND_LABELS = frozenset({
    "凡例", "機能名", "オンライン機能", "オンライン機能(スマートフォン)", "オンライン機能(画面)",
    "バッチ機能", "データ出力機能", "帳票出力機能", "機能グループ", "メール通知", "他システムの処理",
    "データストア", "処理の流れ", "データ読み書き", "メッセージ", "後続で検討する範囲", "コメント",
    "開始条件", "終了条件", "時刻",
})


class _Lane:
    __slots__ = ("top", "sub", "col_start", "col_end")

    def __init__(self, top: str, sub: str, col_start: int, col_end: int) -> None:
        self.top = top              # top-level lane header (e.g. "BCW", "審査", "管理者")
        self.sub = sub              # sub-lane header (e.g. "WebApコンテナ", "Mxxxc") or "" if none
        self.col_start = col_start  # 0-based inclusive
        self.col_end = col_end      # 0-based exclusive (next lane's start; sentinel for the last lane)

    @property
    def label(self) -> str:
        return f"{self.top} / {self.sub}" if self.sub and self.sub != self.top else self.top


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
    def center_col(self) -> float:
        return (self.from_col + self.to_col) / 2.0

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


# --------------------------------------------------------------------------------------------------------------
# text helpers
# --------------------------------------------------------------------------------------------------------------

def _clean_text(s: str) -> str:
    """Collapse runs of whitespace introduced by paragraph joins; keep CJK / full-width content intact."""
    if not s:
        return ""
    s = s.replace("\r", "")
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


# --------------------------------------------------------------------------------------------------------------
# lane detection (from the worksheet cell grid, not from shapes)
# --------------------------------------------------------------------------------------------------------------

def _cell(ws, r: int, c: int) -> str:
    """1-based (row, col) -> trimmed string, with spreadsheet error codes suppressed."""
    try:
        v = ws.cell(row=r, column=c).value
    except (ValueError, IndexError):
        return ""
    if v is None:
        return ""
    s = str(v).strip()
    if s in _XLSX_ERRORS:
        return ""
    return s


def _find_header_rows(ws) -> tuple[int, int]:
    """Locate the lane-header band: the 1-based (top_row, sub_row) whose cells name the lanes.

    Heuristic: the lane header row is the one with the most distinct short text cells just below a "凡例" legend
    block. We scan the first ~40 rows for the densest pair of adjacent rows of short labels. Returns (0, 0) if no
    plausible header band is found (sheet then has no swimlanes -> flat fallback)."""
    max_scan = min(ws.max_row or 0, 40)
    max_col = min(ws.max_column or 0, 120)
    if max_scan < 1 or max_col < 1:
        return (0, 0)

    def row_labels(r: int) -> dict[int, str]:
        out: dict[int, str] = {}
        for c in range(1, max_col + 1):
            t = _cell(ws, r, c)
            # lane headers are short labels; skip long sentences / the title block
            if t and len(t) <= 16 and t not in _XLSX_ERRORS:
                out[c] = t
        return out

    best_row = 0
    best_score = 0
    counts = {r: row_labels(r) for r in range(1, max_scan + 1)}
    for r in range(1, max_scan + 1):
        n = len(counts[r])
        # a real lane row has several headers AND headers spread across many columns
        if n >= 4:
            spread = max(counts[r]) - min(counts[r]) if counts[r] else 0
            score = n + (spread // 8)
            if score > best_score:
                best_score, best_row = score, r
    if best_row == 0:
        return (0, 0)
    # the sub-lane row is the adjacent row (below) that also looks like a header row
    sub_row = 0
    if best_row + 1 <= max_scan and len(counts.get(best_row + 1, {})) >= 3:
        sub_row = best_row + 1
    return (best_row, sub_row)


def _build_lanes(ws, top_row: int, sub_row: int) -> list[_Lane]:
    """Build lanes from the top-level + sub-lane header rows.

    Lane column boundaries are the UNION of header columns across both rows (finest grain): each header owns the
    half-open column range [its_col, next_header_col). A top-level header with no finer sub-headers underneath it
    stays a single lane; a top-level header spanning several sub-headers becomes one lane per sub-header (the
    top label is carried as the lane's group, e.g. "BCW / WebApコンテナ")."""
    max_col = min(ws.max_column or 0, 200)
    top = {c: _cell(ws, top_row, c) for c in range(1, max_col + 1) if _cell(ws, top_row, c)}
    sub = {c: _cell(ws, sub_row, c) for c in range(1, max_col + 1) if _cell(ws, sub_row, c)} if sub_row else {}
    if not top:
        return []

    # finest-grain boundary columns = union of both header rows' columns
    boundary_cols = sorted(set(top) | set(sub))

    def top_for(col: int) -> str:
        # the nearest top header at or left of this column
        chosen = ""
        for tc in sorted(top):
            if tc <= col:
                chosen = top[tc]
            else:
                break
        return chosen

    lanes: list[_Lane] = []
    for i, col in enumerate(boundary_cols):
        nxt = boundary_cols[i + 1] if i + 1 < len(boundary_cols) else 10 ** 6
        sub_label = sub.get(col, "")
        top_label = top.get(col) or top_for(col)
        if not top_label and not sub_label:
            continue
        # convert to 0-based column range (DrawingML anchors are 0-based)
        lanes.append(_Lane(top_label or sub_label, sub_label, col - 1, nxt - 1))
    return lanes


def _lane_for(center_col: float, lanes: list[_Lane]) -> _Lane | None:
    for lane in lanes:
        if lane.col_start <= center_col < lane.col_end:
            return lane
    # left of the first lane -> first lane; right of the last -> last lane (clamp, never lose a shape)
    if lanes:
        if center_col < lanes[0].col_start:
            return lanes[0]
        return lanes[-1]
    return None


# --------------------------------------------------------------------------------------------------------------
# DrawingML walk
# --------------------------------------------------------------------------------------------------------------

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
    ``xdr:grpSp`` groups. Anchor (col,row) of the enclosing anchor is used as the position for all descendants
    (grouped legend shapes share the legend group's anchor -- that anchor sits above the lane row so the whole
    legend group is excluded by position)."""
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
                        if _arrow_reversed(child):
                            src, dst = dst, src
                        edges.append(_Edge(src, dst, label, inferred=False))
                elif st is not None or en is not None:
                    known = (st if st is not None else en).get("id")
                    if known:
                        edges.append(_Edge(known, "", label, inferred=True))
            elif tag == _X + "grpSp":
                _walk(child)
            else:
                if tag in (_X + "pic", _X + "graphicFrame"):
                    continue
                _walk(child)

    _walk(anchor)


def _arrow_reversed(cxn: ET.Element) -> bool:
    """If the connector has a headEnd arrow but no tailEnd arrow, the visible arrow points at the *start*
    connection -> flow is end->start, so callers should swap."""
    ln = cxn.find("." + _X + "spPr/" + _A + "ln")
    if ln is None:
        return False
    head = ln.find(_A + "headEnd")
    tail = ln.find(_A + "tailEnd")
    head_arrow = head is not None and head.get("type", "none") not in ("", "none")
    tail_arrow = tail is not None and tail.get("type", "none") not in ("", "none")
    return head_arrow and not tail_arrow


def _snap_dangling(edges: list[_Edge], shapes: dict[str, _Shape]) -> None:
    """Half-connectors (one endpoint): snap the free end to the nearest shape by anchor distance. Unresolvable
    edges are dropped."""
    nodes = list(shapes.values())
    resolved: list[_Edge] = []
    for e in edges:
        if e.dst:
            resolved.append(e)
            continue
        src = shapes.get(e.src)
        if src is None:
            continue
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


# --------------------------------------------------------------------------------------------------------------
# region classification + glue splicing
# --------------------------------------------------------------------------------------------------------------

def _is_legend(s: _Shape, header_row0: int) -> bool:
    """A shape is legend/title (not flow) if it is anchored at or above the lane-header row, OR its text is a
    known legend label. ``header_row0`` is the 0-based lane (top) header row."""
    if s.to_row <= header_row0:
        return True
    if s.text and s.text.replace(_FULLWIDTH_SPACE, "").replace(" ", "") in _LEGEND_LABELS:
        return True
    return False


def _splice_glue(edges: list[_Edge], glue: set[str]) -> list[_Edge]:
    """Remove textless flow-glue nodes from the edge set by transitive bypass: for each glue node g, every
    (p -> g) + (g -> s) becomes (p -> s); glue with only one side is dropped (the half-edge vanishes). Iterates to
    a fixpoint so chained glue collapses. Self/duplicate edges are deduped."""
    work = [(e.src, e.dst, e.label, e.inferred) for e in edges if e.src and e.dst]
    changed = True
    guard = 0
    while changed and guard < 50:
        changed = False
        guard += 1
        for g in list(glue):
            preds = [(s, d, l, inf) for (s, d, l, inf) in work if d == g]
            succs = [(s, d, l, inf) for (s, d, l, inf) in work if s == g]
            if not (preds or succs):
                continue
            # remove every edge touching g
            work = [(s, d, l, inf) for (s, d, l, inf) in work if s != g and d != g]
            for (ps, _pd, pl, pinf) in preds:
                for (_ss, sd, sl, sinf) in succs:
                    if ps == sd:
                        continue
                    lbl = pl or sl
                    work.append((ps, sd, lbl, pinf or sinf or True))
            changed = True
    out: list[_Edge] = []
    seen: set[tuple[str, str, str]] = set()
    for (s, d, l, inf) in work:
        if s in glue or d in glue:
            continue
        key = (s, d, l)
        if key in seen:
            continue
        seen.add(key)
        out.append(_Edge(s, d, l, inf))
    return out


# --------------------------------------------------------------------------------------------------------------
# Mermaid serialisation
# --------------------------------------------------------------------------------------------------------------

_MERMAID_ESCAPE = {'"': "'"}


def _mermaid_label(text: str) -> str:
    out = text
    for k, v in _MERMAID_ESCAPE.items():
        out = out.replace(k, v)
    out = out.replace("\n", "<br/>")
    out = out.replace("\\", "/").replace("|", "/")
    return out


def _wrap(label: str, prst: str) -> str:
    """Wrap a Mermaid node label in the shape that matches the DrawingML preset."""
    q = f'"{label}"'
    if prst in _DECISION:
        return "{" + q + "}"
    if prst in _IO:
        return "[/" + q + "/]"
    if prst in _DATASTORE:
        return "[(" + q + ")]"
    if prst in _TERMINATOR:
        return "([" + q + "])"
    return "[" + q + "]"


def _sanitize_lane_id(label: str, idx: int) -> str:
    return f"lane{idx}"


def _build_swimlane_mermaid(
    nodes: list[_Shape], edges: list[_Edge], notes: list[tuple[_Shape, _Lane | None]],
    lanes: list[_Lane], lane_of_sid: dict[str, _Lane],
) -> tuple[str, int, int, int]:
    """Serialise nodes (grouped into ``subgraph`` lanes), cross-lane edges and comment notes to a Mermaid
    ``flowchart TD`` swimlane block. Returns (text, node_count, edge_count, lane_count)."""
    if not nodes:
        return ("", 0, 0, 0)

    nodes_sorted = sorted(nodes, key=lambda s: (s.sort_key, s.sid))
    sid_to_node: dict[str, str] = {}
    for i, s in enumerate(nodes_sorted, 1):
        sid_to_node[s.sid] = f"N{i}"

    # group nodes by lane, preserving flow order; nodes with no lane go in an "(未分類)" bucket only if any exist
    by_lane: dict[int, list[_Shape]] = {}
    unassigned: list[_Shape] = []
    lane_index = {id(l): i for i, l in enumerate(lanes)}
    for s in nodes_sorted:
        lane = lane_of_sid.get(s.sid)
        if lane is None:
            unassigned.append(s)
        else:
            by_lane.setdefault(lane_index[id(lane)], []).append(s)

    lines = ["```mermaid", "flowchart TD"]

    def emit_node(s: _Shape, indent: str) -> None:
        nid = sid_to_node[s.sid]
        # decision diamonds are often textless (branch labels live in adjacent rects) -> generic faithful label
        text = s.text or ("判定" if s.prst in _DECISION else "")
        if not text:
            return
        lines.append(f"{indent}{nid}{_wrap(_mermaid_label(text), s.prst)}")

    lanes_emitted = 0
    for i, lane in enumerate(lanes):
        members = by_lane.get(i)
        if not members:
            continue
        lid = _sanitize_lane_id(lane.label, i)
        lines.append(f'    subgraph {lid}["{_mermaid_label(lane.label)}"]')
        for s in members:
            emit_node(s, "        ")
        lines.append("    end")
        lanes_emitted += 1

    for s in unassigned:
        emit_node(s, "    ")

    # cross-lane (and intra-lane) edges
    edge_count = 0
    seen: set[tuple[str, str, str]] = set()
    declared = {s.sid for s in nodes_sorted if (s.text or s.prst in _DECISION)}
    for e in edges:
        if e.src not in declared or (e.dst not in declared):
            continue
        a = sid_to_node.get(e.src)
        b = sid_to_node.get(e.dst)
        if a is None or b is None:
            continue
        key = (a, b, e.label)
        if key in seen:
            continue
        seen.add(key)
        lbl = _mermaid_label(e.label) if e.label else ""
        arrow = f"-->|{lbl}|" if lbl else "-->"
        suffix = "  %% inferred" if e.inferred else ""
        lines.append(f"    {a} {arrow} {b}{suffix}")
        edge_count += 1

    # comment callouts as Mermaid notes (annotations, not flow steps)
    for s, lane in notes:
        if not s.text:
            continue
        where = f" [{lane.label}]" if lane else ""
        flat = s.text.replace("\n", " ")
        lines.append(f"    %% コメント{where}: {flat}")

    lines.append("```")
    return ("\n".join(lines), len(declared), edge_count, lanes_emitted)


# --------------------------------------------------------------------------------------------------------------
# part resolution
# --------------------------------------------------------------------------------------------------------------

def _drawing_for_sheet(zf: zipfile.ZipFile, sheet_path: str) -> str | None:
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


# --------------------------------------------------------------------------------------------------------------
# public entry
# --------------------------------------------------------------------------------------------------------------

def extract_sheet_flow(zf: zipfile.ZipFile, sheet_path: str, ws=None) -> tuple[str, int, int]:
    """Extract a Mermaid SWIMLANE flowchart for one worksheet. Returns (mermaid_block, node_count, edge_count).

    ``ws`` is the openpyxl worksheet (for lane-header detection from the cell grid); if None, lanes can't be
    detected and the chart degrades to a flat (single implicit lane) flow. ``mermaid_block`` is "" when the sheet
    has no shapes/connectors. Never raises -- on any malformed part returns ("", 0, 0) so the cell grid path runs.
    """
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
            _collect(anchor, shapes, edges)
        _snap_dangling(edges, shapes)

        # --- lanes from the worksheet grid ---
        lanes: list[_Lane] = []
        header_row0 = -1
        if ws is not None:
            top_row, sub_row = _find_header_rows(ws)
            if top_row:
                lanes = _build_lanes(ws, top_row, sub_row)
                header_row0 = (sub_row or top_row) - 1  # 0-based; shapes at/above this are legend/title

        # --- classify shapes: legend (drop) / callout note / glue / real node ---
        legend: set[str] = set()
        glue: set[str] = set()
        notes: list[tuple[_Shape, _Lane | None]] = []
        flow_nodes: list[_Shape] = []
        for s in shapes.values():
            if header_row0 >= 0 and _is_legend(s, header_row0):
                legend.add(s.sid)
                continue
            if s.prst in _CALLOUT:
                lane = _lane_for(s.center_col, lanes) if lanes else None
                notes.append((s, lane))
                continue
            if (s.prst in _GLUE) and not s.text:
                glue.add(s.sid)
                continue
            flow_nodes.append(s)

        # drop legend/callout endpoints from edges, then splice glue transitively
        drop = legend | {s.sid for s, _ in notes}
        edges = [e for e in edges if e.src not in drop and e.dst not in drop]
        edges = _splice_glue(edges, glue)

        # keep only real flow shapes that carry text OR are a (textless) decision -> never a "step Nxx"
        keep = [s for s in flow_nodes if s.text or s.prst in _DECISION]

        # assign each kept node to a lane by its anchor centre column
        lane_of_sid: dict[str, _Lane] = {}
        if lanes:
            for s in keep:
                lane = _lane_for(s.center_col, lanes)
                if lane is not None:
                    lane_of_sid[s.sid] = lane

        if not keep:
            return ("", 0, 0)

        block, n_nodes, n_edges, _n_lanes = _build_swimlane_mermaid(
            keep, edges, notes, lanes, lane_of_sid,
        )
        return (block, n_nodes, n_edges)
    except (ET.ParseError, KeyError, ValueError) as exc:  # noqa: BLE001
        log.warning("xlsx_drawing_extract_failed", sheet=sheet_path, error=str(exc))
        return ("", 0, 0)
