#!/usr/bin/env python3
"""pre-commit entry point: runs unseen from this folder (stdlib only, so nothing to install)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unseen.cli import main
sys.exit(main())
