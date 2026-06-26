"""Box primitive shared by the structure engine — the recognizer's output unit."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Box:
    """One recognized text region. Coordinates are page pixels/points, origin top-left.

    label is a coarse region kind when the recognizer provides one ('text'|'title'|'figure'|'table'|
    'formula'|'caption'); empty otherwise. font_size/bold come free from native PDF text and drive the
    hierarchy stage. id is the box's original index (stable identity through reordering)."""

    id: int
    x0: float
    y0: float
    x1: float
    y1: float
    text: str = ""
    label: str = ""
    font_size: float = 0.0
    bold: bool = False
    meta: dict = field(default_factory=dict)

    @property
    def w(self) -> float:
        return self.x1 - self.x0

    @property
    def h(self) -> float:
        return self.y1 - self.y0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2.0
