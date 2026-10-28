"""Standalone offline training tools; imports do not start services."""
from pathlib import Path
import sys

# Existing AI modules use script-style imports. Keep one implementation of them.
AI=Path(__file__).resolve().parents[1]
if str(AI) not in sys.path:sys.path.insert(0,str(AI))
