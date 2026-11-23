"""发布 zip 的结构与运行时文件排除。"""

from __future__ import annotations

import zipfile

from scripts.build_zip import build


def test_build_zip_keeps_payload_and_drops_runtime(tmp_path):
    root = tmp_path / "RinLauncher"
    (root / "data").mkdir(parents=True)
    (root / "data" / "config.yaml").write_text("secret", encoding="utf-8")
    (root / "RinLauncher.exe").write_bytes(b"exe")
    (root / "install-manifest.json").write_text("{}", encoding="utf-8")
    (root / "appmodset.conf").write_text("first-run==false", encoding="utf-8")
    (root / "backup-20260101").mkdir()
    (root / "backup-20260101" / "old.yaml").write_text("old", encoding="utf-8")

    output = tmp_path / "RinLauncher.zip"
    build(root, output)

    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
    assert names == {"RinLauncher.exe", "install-manifest.json"}
