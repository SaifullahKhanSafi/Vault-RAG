"""Application version, synchronized from the root VERSION by tools/version.py."""
from pathlib import Path

VERSION=Path(__file__).with_name('VERSION').read_text(encoding='utf-8').strip()
