"""Terrane self-developed document structure engine (pure-algorithm, no model, CPU-trivial).

Operates on a list of recognizer boxes (from PyMuPDF native text, or any OCR that yields boxes) and
reconstructs reading order, section hierarchy, and tables — entirely in our own code. Models are only
used upstream for the irreducible "pixels -> text" recognition step; everything here is geometry.

Modules:
  reading_order — XY-Cut++ (pre-mask spanning elements -> density-adaptive recursive cut -> re-insertion)
  hierarchy     — font/numbering/geometry -> level assignment -> stack-based section tree
"""

from app.services.parse.structure.box import Box  # noqa: F401
