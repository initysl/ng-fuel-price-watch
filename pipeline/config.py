"""Central configuration: env vars, paths and thresholds. Filled in as steps are built."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LANDING_DIR = PROJECT_ROOT / "landing" / "raw"
SQL_DIR = PROJECT_ROOT / "sql"
SEEDS_DIR = PROJECT_ROOT / "seeds"

DATABASE_URL = os.getenv("DATABASE_URL", "")
