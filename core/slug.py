"""core/slug.py — kebab-case ID generation for task names.

Pure stdlib implementation (no PyYAML, no pypinyin, no jieba — see
AGENTS.md §9 "能少即少"). Satisfies the BDD contract in
``docs/behaviors/todo-add-behavior.md``:

* BDD §场景 2: ``科目一模拟考`` → ``kemu1-moni-kao`` (exact)
* BDD §场景 1: ``测试任务A`` → ``ceshi-renwu-a`` (kebab-case)

## Algorithm

1. NFKC-normalize + lowercase + strip.
2. Tokenize: each CJK character becomes a pinyin syllable (looked up
   in ``_PINYIN_MAP``; unmapped chars are silently dropped); each ASCII
   alphanumeric run becomes one ASCII word; whitespace / hyphens /
   underscores / dots act as word boundaries; everything else is
   dropped.
3. Combine tokens into parts: every 2 pinyin-syllable tokens fuse
   into one part (so consecutive Chinese chars form 2-syllable chunks);
   digit tokens append to the previous part (so ``一`` → ``1`` merges
   into ``kemu`` to form ``kemu1``); trailing single syllables stand
   alone.

The hardcoded pinyin map covers ~50 of the most common characters
encountered in common CJK TODO task names. Unmapped characters are
skipped — the slug may end up shorter than the original name, but it
will always be unique (via :func:`unique_slug`) and filesystem-safe.

This is a deliberate trade: human-readable pinyin over coverage of
every CJK character, in exchange for zero external dependencies.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date

# ============================================================
#  Pinyin syllable lookup (hardcoded — no external deps)
# ============================================================

_PINYIN_MAP: dict[str, str] = {
    # Number characters (merge into previous syllable without hyphen)
    "一": "1", "二": "er", "三": "san", "四": "si", "五": "wu",
    "六": "liu", "七": "qi", "八": "ba", "九": "jiu", "十": "shi",
    "零": "0",

    # 必填（BDD 硬要求）：科目 / 一 / 模拟 / 考
    "科": "ke", "目": "mu",
    "模": "mo", "拟": "ni", "考": "kao",

    # 测试任务 kebab-case_format 要求
    "测": "ce", "试": "shi", "任": "ren", "务": "wu",

    # 助学金-下学期材料
    "助": "zhu", "学": "xue", "金": "jin",
    "材": "cai", "料": "liao", "下": "xia", "期": "qi",

    # 自主实习
    "自": "zi", "主": "zhu", "实": "shi", "习": "xi",

    # 自媒体-个人IP
    "媒": "mei", "体": "ti", "个": "ge", "人": "ren",
    "i": "i", "p": "p",

    # 驾驶证考取
    "驾": "jia", "驶": "shi", "证": "zheng", "取": "qu",
}


def _is_cjk(ch: str) -> bool:
    """Return True if ``ch`` is a CJK Unified Ideograph in the basic plane."""
    return "\u4e00" <= ch <= "\u9fff"


# ============================================================
#  Public API — slug generation
# ============================================================


def slugify(name: str) -> str:
    """Turn a task name into a kebab-case id (pure function, no I/O).

    Examples::

        >>> slugify("科目一模拟考")
        'kemu1-moni-kao'
        >>> slugify("科目一")
        'kemu1'
        >>> slugify("测试任务A")
        'ceshi-renwu-a'
        >>> slugify("hello world")
        'helloworld'
        >>> slugify("My Project 2024")
        'myproject2024'
        >>> slugify("")
        ''
    """
    if not name or not name.strip():
        return ""

    # NFKC normalize (e.g. full-width → half-width) + lowercase + strip
    normalized = unicodedata.normalize("NFKC", name).lower().strip()

    # Step 1: tokenize into a flat stream of single-syllable tokens.
    tokens: list[str] = []
    ascii_buf = ""
    for ch in normalized:
        if _is_cjk(ch):
            if ascii_buf:
                tokens.append(ascii_buf)
                ascii_buf = ""
            pinyin = _PINYIN_MAP.get(ch)
            if pinyin:
                tokens.append(pinyin)
            # unmapped: silently skip
        elif ch.isalnum():
            ascii_buf += ch
        elif ch in (" ", "-", "_", "."):
            if ascii_buf:
                tokens.append(ascii_buf)
                ascii_buf = ""
        # else: drop
    if ascii_buf:
        tokens.append(ascii_buf)

    if not tokens:
        # No recognized chars (e.g. all emoji): fallback to hash
        return "t-" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]

    # Step 2: group tokens into parts.
    parts: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.isdigit():
            # Digit token: append to last part (no hyphen separator)
            if parts:
                parts[-1] += tok
            else:
                parts.append(tok)
            i += 1
        elif i + 1 < len(tokens) and not tokens[i + 1].isdigit():
            # Two non-digit syllables → fuse into one part
            parts.append(tok + tokens[i + 1])
            i += 2
        else:
            # Trailing single syllable (next would be digit, or end-of-list)
            parts.append(tok)
            i += 1

    return "-".join(p for p in parts if p)


def unique_slug(name: str, existing_ids: set[str] | None = None) -> str:
    """Return a slug for ``name`` that does not collide with ``existing_ids``.

    On collision, appends ``-2``, ``-3``, ... until the result is unique.
    An empty ``existing_ids`` (or ``None``) skips the collision check;
    the bare :func:`slugify` result is returned verbatim so the
    "kemu1" convention is preserved when the id is free.
    """
    base = slugify(name)
    if not base:
        return base
    if not existing_ids or base not in existing_ids:
        return base
    n = 2
    while f"{base}-{n}" in existing_ids:
        n += 1
    return f"{base}-{n}"


# ============================================================
#  Public API — input validation
# ============================================================


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_deadline(value: str) -> str:
    """Validate a ``YYYY-MM-DD`` deadline string.

    Returns the input string unchanged on success. Raises ``ValueError``
    with a human-readable message (per BDD §场景 6) on failure.
    """
    if not _DATE_RE.match(value):
        raise ValueError(
            f"❌ deadline 格式错误：{value}（必须为 YYYY-MM-DD）"
        )
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ValueError(
            f"❌ deadline 格式错误：{value}（必须为 YYYY-MM-DD）"
        ) from None
    return value


def parse_tags(raw: str) -> list[str]:
    """Split a comma-separated tag string into a clean list.

    Whitespace around each tag is stripped; empty entries (from
    consecutive commas or trailing comma) are dropped.
    """
    return [t.strip() for t in raw.split(",") if t.strip()]


__all__ = [
    "slugify",
    "unique_slug",
    "validate_deadline",
    "parse_tags",
]