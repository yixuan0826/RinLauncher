"""为打包目录生成 ``install-manifest.json``（路径 + SHA-256）。

用法::

    python scripts/build_manifest.py dist/RinLauncher
    python scripts/build_manifest.py dist/RinLauncher --output other.json

* 只收录安装产物；``data/``（用户配置 / 日志 / 图标）、``updates/``、
  ``backup-*`` 与清单自身不进清单。
* 路径统一用 ``/``，跨平台可读。
* 生成后再跑一次校验，确保写出来的清单和磁盘一致。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

MANIFEST_NAME = "install-manifest.json"
EXCLUDED_DIRS = {"data", "updates", "backups", "logs", "thumbnails"}
EXCLUDED_PREFIXES = ("backup-",)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        parts = relative.parts
        if parts and parts[0] in EXCLUDED_DIRS:
            continue
        if any(part.startswith(EXCLUDED_PREFIXES) for part in parts):
            continue
        if relative.as_posix() == MANIFEST_NAME:
            continue
        files.append(path)
    return sorted(files)


def build(root: Path, output: Path, version: str = "") -> dict:
    files = {
        path.relative_to(root).as_posix(): sha256(path)
        for path in iter_files(root)
    }
    manifest = {"version": version, "files": files}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    return manifest


def verify(root: Path, manifest_path: Path) -> list[str]:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    problems: list[str] = []
    for relative, expected in (data.get("files") or {}).items():
        target = root / relative
        if not target.is_file():
            problems.append(f"missing: {relative}")
        elif sha256(target).lower() != str(expected).lower():
            problems.append(f"hash mismatch: {relative}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="打包目录（含 RinLauncher.exe）")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--version", default="")
    parser.add_argument("--check", action="store_true",
                        help="只校验，不重新生成")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2
    output = (args.output or (root / MANIFEST_NAME)).resolve()
    if args.check:
        if not output.is_file():
            print(f"manifest not found: {output}", file=sys.stderr)
            return 2
        problems = verify(root, output)
        for problem in problems:
            print(problem, file=sys.stderr)
        print(f"manifest: {len(problems)} problem(s)")
        return 1 if problems else 0

    manifest = build(root, output, args.version)
    problems = verify(root, output)
    print(f"manifest: {len(manifest['files'])} files -> {output}")
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
