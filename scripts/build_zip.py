"""Create the ``RinLauncher.zip`` self-update payload.

PowerShell ``Compress-Archive`` uses a lower deflate level than zlib; for a
~150 MB payload that is roughly 2 MB on the wire.  This script writes the same
flat zip layout (files at the archive root) with level-9 deflate and refuses to
ship runtime files.

Usage::

    python scripts/build_zip.py dist/RinLauncher RinLauncher.zip
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

EXCLUDED_DIRS = {"data", "updates", "backups", "logs", "thumbnails"}
EXCLUDED_FILES = {
    "appmodset.conf",
    "channel.txt",
    "launcher.log",
    "update-in-progress.json",
}
EXCLUDED_PREFIXES = ("backup-",)


def iter_payload(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if relative.parts[0] in EXCLUDED_DIRS:
            continue
        if relative.name in EXCLUDED_FILES:
            continue
        if any(part.startswith(EXCLUDED_PREFIXES) for part in relative.parts):
            continue
        yield path, relative.as_posix()


def build(root: Path, output: Path) -> int:
    root = root.resolve()
    output = output.resolve()
    if not (root / "RinLauncher.exe").is_file():
        raise SystemExit(f"payload has no RinLauncher.exe: {root}")
    output.unlink(missing_ok=True)
    files = list(iter_payload(root))
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, name in files:
            archive.write(path, name)
    size = output.stat().st_size / (1024 * 1024)
    print(f"zip: {len(files)} files, {size:.2f} MB -> {output}")
    return len(files)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="dist/RinLauncher")
    parser.add_argument("output", type=Path, nargs="?", default=Path("RinLauncher.zip"))
    args = parser.parse_args(argv)
    try:
        build(args.root, args.output)
    except OSError as exc:
        print(f"zip failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
