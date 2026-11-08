"""GitHub Release 列表与更新说明的解析。

这里只放**纯函数**与常量：不碰 Qt、不碰网络，所以能直接用样例 JSON 单测。
``updater.py`` 只负责状态机、下载与安装。
"""

from __future__ import annotations

import html
import re
from typing import Any

from rin_launcher import __version__ as APP_VERSION

REPO = "yixuan0826/RinLauncher"
API_ROOT = f"https://api.github.com/repos/{REPO}/releases"
ASSET_NAME = "rinlauncher.zip"
USER_AGENT = f"RinLauncher/{APP_VERSION}"

MIRRORS: dict[str, str] = {
    "ghfast": "https://ghfast.top/",
    "ghproxy": "https://ghproxy.net/",
}
MIRROR_LABELS = {"github": "GitHub", "ghfast": "ghfast", "ghproxy": "ghproxy"}
SPEED_URLS = {
    "github": f"https://api.github.com/repos/{REPO}/releases/latest",
    "ghfast": f"https://ghfast.top/https://raw.githubusercontent.com/{REPO}/main/README.md",
    "ghproxy": f"https://ghproxy.net/https://raw.githubusercontent.com/{REPO}/main/README.md",
}

STATE_IDLE = "idle"
STATE_CHECKING = "checking"
STATE_UP_TO_DATE = "up-to-date"
STATE_DOWNLOADING = "downloading"
STATE_READY = "ready"
STATE_INSTALLING = "installing"
STATE_ERROR = "error"


def version_tuple(tag: str) -> tuple[int, ...]:
    """把 ``v1.2.3-beta`` 这类 tag 变成可比较的数字元组。"""
    numbers = [int(part) for part in re.findall(r"\d+", str(tag))[:4]]
    return tuple(numbers) if numbers else (0,)


_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_HTML_BREAK = re.compile(r"<br\s*/?>", re.IGNORECASE)


def clean_release_notes(body: str) -> str:
    """GitHub Release 正文的最小清洗：丢掉 HTML 注释、把 ``<br>`` 换成换行。"""
    text = _HTML_COMMENT.sub("", str(body or ""))
    text = _HTML_BREAK.sub("\n", text)
    return text.strip()


# ── Release 列表 ────────────────────────────────────────────────────
#
# 更新页不再是「有新版就自动下载」，而是把整张 Release 列表交给用户挑。
# 这样「回滚」就是选一个旧版本重装，不需要 old.zip 那套备份/还原。

RELEASE_LIST_LIMIT = 30


def parse_releases(payload: Any, *,
                   limit: int = RELEASE_LIST_LIMIT) -> list[dict[str, Any]]:
    """把 GitHub ``/releases`` 的响应整理成界面能直接用的列表。

    纯函数（不碰网络 / Qt），方便测试。跳过草稿与没有 tag 的条目，按版本号
    从新到旧排序；每条带上下载地址、SHA-256 digest（GitHub 没给时为空串）
    以及 ``current`` 标记（就是当前运行的版本）。
    """
    if not isinstance(payload, list):
        return []
    items: list[dict[str, Any]] = []
    for raw in payload:
        if not isinstance(raw, dict) or raw.get("draft"):
            continue
        tag = str(raw.get("tag_name") or "").strip()
        if not tag:
            continue
        # 历史上的 tag 写法不统一（v1.1.0 / v.1.1.2），统一成纯版本号
        version = tag.lstrip("vV").lstrip(".")
        if not version:
            continue
        assets = raw.get("assets") if isinstance(raw.get("assets"), list) else []
        asset = next(
            (item for item in assets
             if isinstance(item, dict)
             and str(item.get("name") or "").lower() == ASSET_NAME),
            None,
        )
        items.append({
            "tag": tag,
            "version": version,
            "name": str(raw.get("name") or tag),
            "prerelease": bool(raw.get("prerelease")),
            "published": str(raw.get("published_at") or "")[:10],
            "url": str(raw.get("html_url") or ""),
            "downloadUrl": str((asset or {}).get("browser_download_url") or ""),
            "digest": str((asset or {}).get("digest") or ""),
            "assetName": str((asset or {}).get("name") or ""),
            "current": version == APP_VERSION,
            "notes": clean_release_notes(str(raw.get("body") or "")),
        })
    items.sort(key=lambda item: version_tuple(item["version"]), reverse=True)
    return items[:max(1, limit)]


def release_label(item: dict[str, Any]) -> str:
    """下拉菜单里的一行文本，例如 ``v1.1.8-pre · 预发布 · 当前``。"""
    parts = [f"v{item.get('version') or item.get('tag') or '?'}"]
    if item.get("current"):
        parts.append("当前")
    if item.get("prerelease"):
        parts.append("预发布")
    if item.get("published"):
        parts.append(str(item["published"]))
    if not item.get("downloadUrl"):
        parts.append("无更新包")
    return " · ".join(parts)


# ── Markdown → 结构化块 ──────────────────────────────────────────────
#
# 为什么不直接在 QML 里用 ``Text.MarkdownText``：Qt 6.12 的 QQuickText 在
# 「先空文本、后填 Markdown」这条路径上会按默认字号排版、按 Markdown 字号绘制，
# 标题行距被压扁甚至重叠。改成后端把正文拆成块、QML 一块一个 Text 之后，
# 每个块都是「创建时就有内容」，行距稳定，也顺手拿到了可控的字号与间距。

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_BULLET = re.compile(r"^[-*+]\s+(.+)$")
_ORDERED = re.compile(r"^(\d{1,3})[.)]\s+(.+)$")
_RULE = re.compile(r"^(?:-{3,}|\*{3,}|_{3,})$")

_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_STRIKE = re.compile(r"~~(.+?)~~")
_ITALIC_STAR = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
_ITALIC_UNDER = re.compile(r"(?<!_)_([^_\n]+)_(?!_)")


def _inline_markdown(text: str) -> str:
    """把行内 Markdown 变成 RichText 片段。

    先整体转义 HTML，再把代码、链接这些「里面的内容不该再解析」的部分暂存成
    占位符，最后统一还原 —— 免得代码里的星号被当成斜体。
    """
    tokens: list[str] = []

    def stash(fragment: str) -> str:
        tokens.append(fragment)
        return f"\x00{len(tokens) - 1}\x00"

    escaped = html.escape(text, quote=False)
    escaped = _INLINE_CODE.sub(
        lambda match: stash(f"<code>{match.group(1)}</code>"), escaped)
    escaped = _LINK.sub(
        lambda match: stash(
            f'<a href="{html.escape(match.group(2), quote=True)}">{match.group(1)}</a>'),
        escaped)
    escaped = _BOLD.sub(r"<b>\1</b>", escaped)
    escaped = _STRIKE.sub(r"<s>\1</s>", escaped)
    escaped = _ITALIC_STAR.sub(r"<i>\1</i>", escaped)
    escaped = _ITALIC_UNDER.sub(r"<i>\1</i>", escaped)

    for index, fragment in enumerate(tokens):
        escaped = escaped.replace(f"\x00{index}\x00", fragment)
    return escaped


def parse_release_notes(body: str) -> list[dict[str, Any]]:
    """把 Release 正文拆成 QML 能直接渲染的块列表。

    每块带 ``kind`` / ``html`` / ``spaceBefore``，标题额外带 ``level``。
    只覆盖 GitHub Release 里常见的语法：标题、段落、无序/有序列表、引用、
    围栏代码块、分隔线；表格与图片按普通段落处理。
    """
    blocks: list[dict[str, Any]] = []
    paragraph: list[str] = []
    code_lines: list[str] = []
    in_code = False

    def flush_paragraph() -> None:
        if not paragraph:
            return
        blocks.append({
            "kind": "paragraph",
            "html": _inline_markdown(" ".join(paragraph)),
            "spaceBefore": 8 if blocks else 0,
        })
        paragraph.clear()

    for raw_line in clean_release_notes(body).splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if in_code:
            if stripped.startswith("```"):
                blocks.append({
                    "kind": "code",
                    "html": html.escape("\n".join(code_lines), quote=False),
                    "spaceBefore": 10,
                })
                code_lines = []
                in_code = False
            else:
                code_lines.append(line)
            continue

        if stripped.startswith("```"):
            flush_paragraph()
            in_code = True
            continue

        if not stripped:
            flush_paragraph()
            continue

        heading = _HEADING.match(stripped)
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            blocks.append({
                "kind": "heading",
                "level": level,
                "html": _inline_markdown(heading.group(2)),
                "spaceBefore": 16 if level == 1 else 12 if level == 2 else 10,
            })
            continue

        if _RULE.match(stripped):
            flush_paragraph()
            blocks.append({"kind": "rule", "html": "", "spaceBefore": 12})
            continue

        bullet = _BULLET.match(stripped)
        if bullet:
            flush_paragraph()
            blocks.append({
                "kind": "bullet",
                "html": "• " + _inline_markdown(bullet.group(1)),
                "spaceBefore": 4 if blocks else 0,
            })
            continue

        ordered = _ORDERED.match(stripped)
        if ordered:
            flush_paragraph()
            blocks.append({
                "kind": "ordered",
                "html": f"{ordered.group(1)}. " + _inline_markdown(ordered.group(2)),
                "spaceBefore": 4 if blocks else 0,
            })
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            blocks.append({
                "kind": "quote",
                "html": _inline_markdown(stripped.lstrip(">").strip()),
                "spaceBefore": 10,
            })
            continue

        paragraph.append(stripped)

    if in_code and code_lines:
        blocks.append({
            "kind": "code",
            "html": html.escape("\n".join(code_lines), quote=False),
            "spaceBefore": 10,
        })
    flush_paragraph()
    return blocks
