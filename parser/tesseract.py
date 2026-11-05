"""Find the Tesseract OCR program, wherever it was installed.

Tesseract is a separate install (README, step 2). The installer can put it under
Program Files or the user's AppData, and may or may not add it to PATH.
"""
import os
import shutil
from pathlib import Path

import pytesseract


def _candidates():
    yield os.environ.get("TESSERACT_CMD")  # explicit override
    yield shutil.which("tesseract")
    for base in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        root = os.environ.get(base)
        if root:
            sub = "Programs/Tesseract-OCR" if base == "LOCALAPPDATA" else "Tesseract-OCR"
            yield str(Path(root) / sub / "tesseract.exe")


def find():
    return next((c for c in _candidates() if c and Path(c).is_file()), None)


def configure():
    """Point pytesseract at Tesseract. Returns its path, or None if it isn't installed."""
    path = find()
    if path:
        pytesseract.pytesseract.tesseract_cmd = path
    return path
