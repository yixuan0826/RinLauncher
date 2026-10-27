"""启动台搜索：拼音全拼、首字母与普通子串。

pypinyin 是可选依赖：没装时自动退化为普通子串匹配，界面不会因此报错。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:  # pragma: no cover - 依赖缺失时只走退化分支
    from pypinyin import Style, lazy_pinyin
except Exception:  # pragma: no cover
    Style = None
    lazy_pinyin = None


def _variants(text: str) -> list[str]:
    base = str(text or "").strip().lower()
    if not base:
        return []
    variants = [base]
    if lazy_pinyin is not None:
        try:
            variants.append("".join(lazy_pinyin(base)))
            variants.append("".join(lazy_pinyin(base, style=Style.FIRST_LETTER)))
        except Exception:
            logger.debug("pinyin conversion failed for %r", base, exc_info=True)
    return variants


def matches(query: str, *fields: str) -> bool:
    """query 为空时视为全部命中；否则任一字段的原文/全拼/首字母包含它即命中。"""
    needle = str(query or "").strip().lower()
    if not needle:
        return True
    for field in fields:
        for variant in _variants(field):
            if needle in variant:
                return True
    return False
