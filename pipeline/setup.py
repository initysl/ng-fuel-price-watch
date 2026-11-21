"""Create schemas/tables and load seeds. Safe to run any number of times.

Usage: python -m pipeline.setup
"""

import logging

from pipeline.db import get_engine, load_seeds, run_migrations


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    engine = get_engine()
    try:
        ran = run_migrations(engine)
        counts = load_seeds(engine)
    finally:
        engine.dispose()
    print(f"migrations: {', '.join(ran)}")
    for table, n in counts.items():
        print(f"{table}: {n} rows")


if __name__ == "__main__":
    main()
