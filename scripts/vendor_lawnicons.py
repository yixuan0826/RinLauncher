#!/usr/bin/env python3
"""把 Lawnicons 里挑选的图标并入 assets/icons/lawnicons。

Lawnicons（Apache-2.0）的 SVG 放在仓库的 ``svgs/`` 目录下，文件名即图标名。
本脚本只做两件事：

1. 复制 ``BUNDLED`` 里列出的图标；
2. 给缺少 ``viewBox`` 的文件补上 ``viewBox="0 0 192 192"``。

第 2 步是必须的：上游相当一部分文件只写了 ``width``/``height``，Qt 的
QSvgRenderer 在没有 viewBox 时不会按 192×192 的坐标系缩放，图标会糊或直接被
裁掉。这是一处对上游文件的修改，Apache-2.0 §4(b) 要求显著标注 —— 见
assets/icons/lawnicons/NOTICE。

用法::

    python scripts/vendor_lawnicons.py --source /path/to/lawnicons/svgs
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TARGET_DIR = PROJECT_ROOT / "assets" / "icons" / "lawnicons"

# 只挑 generic_* —— 这些是上游为「没有专属图标的普通应用」准备的通用图案，
# 不牵涉第三方商标。honkai_star_rail 是作者指定的应用主图标，单独列出。
BUNDLED: tuple[str, ...] = (
    "app_manager",
    "generic_audio_editor",
    "generic_background_eraser",
    "generic_bluetooth",
    "generic_book",
    "generic_braces",
    "generic_browser",
    "generic_calculator_plus_minus_multi_equal",
    "generic_camera",
    "generic_card",
    "generic_chess",
    "generic_clock",
    "generic_compass",
    "generic_contacts",
    "generic_dialer",
    "generic_download_arrow",
    "generic_download_circle",
    "generic_earth",
    "generic_earth_pro",
    "generic_email",
    "generic_files",
    "generic_files_pro",
    "generic_flashlight",
    "generic_gallery",
    "generic_gallery_dev",
    "generic_games",
    "generic_grid_3x3",
    "generic_heart",
    "generic_keyboard",
    "generic_lock",
    "generic_microphone",
    "generic_moon",
    "generic_notes",
    "generic_pdf_file",
    "generic_pi",
    "generic_player",
    "generic_player_pro",
    "generic_power",
    "generic_printer",
    "generic_qr_reader",
    "generic_rotation",
    "generic_scanner",
    "generic_search",
    "generic_settings",
    "generic_shell",
    "generic_silverware",
    "generic_sudoku",
    "generic_trash_can",
    "generic_voice",
    "honkai_star_rail",
)

VIEW_BOX = 'viewBox="0 0 192 192"'
_SVG_TAG = re.compile(r"<svg\b[^>]*>")


def add_view_box(text: str) -> tuple[str, bool]:
    """Return the (possibly rewritten) markup and whether it was changed."""
    match = _SVG_TAG.search(text)
    if match is None or "viewBox" in match.group(0):
        return text, False
    tag = match.group(0)
    patched = tag[:-1].rstrip() + f" {VIEW_BOX}>"
    return text[:match.start()] + patched + text[match.end():], True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True,
                        help="上游 Lawnicons 仓库里的 svgs/ 目录")
    args = parser.parse_args()

    source = Path(args.source).expanduser()
    if not source.is_dir():
        print(f"找不到源目录: {source}", file=sys.stderr)
        return 1

    TARGET_DIR.mkdir(parents=True, exist_ok=True)

    copied = 0
    patched: list[str] = []
    missing: list[str] = []

    for name in BUNDLED:
        origin = source / f"{name}.svg"
        if not origin.is_file():
            missing.append(name)
            continue
        text = origin.read_text(encoding="utf-8")
        text, changed = add_view_box(text)
        if changed:
            patched.append(name)
        (TARGET_DIR / f"{name}.svg").write_text(text, encoding="utf-8")
        copied += 1

    print(f"已并入 {copied} 个图标 -> {TARGET_DIR.relative_to(PROJECT_ROOT)}")
    print(f"补写 viewBox 的有 {len(patched)} 个: {', '.join(patched) or '无'}")
    if missing:
        print(f"上游缺少这些图标（已跳过）: {', '.join(missing)}", file=sys.stderr)
    print("不要忘记同步 assets/icons/lawnicons/NOTICE 里的修改声明。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
