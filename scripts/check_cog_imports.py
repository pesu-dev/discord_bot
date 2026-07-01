#!/usr/bin/env python3
"""Verify all cog packages import without circular dependency errors."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.utils.cogs import COGS_PACKAGE, discover_cog_extensions, get_cogs_dir  # noqa: E402


def main() -> int:
    extensions = discover_cog_extensions(get_cogs_dir(), COGS_PACKAGE)
    for extension in extensions:
        importlib.import_module(extension)
    print(f"Imported {len(extensions)} cog packages: {', '.join(extensions)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
