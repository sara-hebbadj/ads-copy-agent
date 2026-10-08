"""ads_agent: draft, check and approve ad copy; analyse a campaign file.

Nothing in this package posts to a real ad account. There is no Meta API connection.
"""

from pathlib import Path

# src/ads_agent/__init__.py -> parents[2] is the repository root.
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
DOCS_DIR = REPO_ROOT / "docs"
EVALS_DIR = REPO_ROOT / "evals"
