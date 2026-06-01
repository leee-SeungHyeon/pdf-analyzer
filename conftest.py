import sys
import os
from unittest.mock import MagicMock

# opendataloader_pdf is a top-level import in src/pdf_extractor.py but is not
# used by _parse_sections.  Stub it out so tests can import without the package
# being installed.
sys.modules.setdefault("opendataloader_pdf", MagicMock())

sys.path.insert(0, os.path.dirname(__file__))
