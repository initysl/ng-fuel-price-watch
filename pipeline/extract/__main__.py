"""Extract every file acquire has queued and print what was found. Writes nothing.

Usage: python -m pipeline.extract
"""

import sys

from pipeline.acquire import RawFileModifiedError, pending_files, verify_raw_file
from pipeline.db import get_engine
from pipeline.extract.excel import LayoutChangedError, extract_report


def main() -> None:
    engine = get_engine()
    try:
        pending = pending_files(engine)
    finally:
        engine.dispose()

    failed = 0
    for f in pending:
        try:
            verify_raw_file(f.path, f.sha256)  # D3: never read a file that changed
            r = extract_report(f.path)
        except (LayoutChangedError, RawFileModifiedError) as exc:
            failed += 1
            print(f"FAIL  {exc}")
            continue
        print(
            f"ok  {r.report_month:%Y-%m}  header row {r.header_row:>2}  "
            f"{len(r.states)} states  {len(r.zones)} zones  "
            f"national {r.national.iloc[0, -1]:,.2f}  {f.file_name}"
        )
    print(f"{len(pending) - failed}/{len(pending)} files extracted")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
