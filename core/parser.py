"""core/parser.py — Hand-written YAML frontmatter parser/dumper.

We intentionally avoid PyYAML to keep the dependency surface minimal
(see AGENTS.md §9: "能少即少"). This module supports only the subset of
YAML actually used in x-cli's TODO.md files:

* ``key: value`` flat pairs (scalars are string / int / float / bool / null)
* ``key: [a, b, c]`` flow-style lists of scalars
* ``key:`` followed by a block-style list (``- item``)
* ``key:`` followed by a block-style list of mappings (e.g. ``subtasks``)
* ``key:`` followed by a block-style mapping (less common, supported)
* Quoted strings (``"..."`` or ``'...'``)
* Trailing comments (``# ...``)

Unknown fields (anything outside the small set the storage layer
recognises) are preserved verbatim through :func:`parse_frontmatter`
and :func:`dump_frontmatter` so user-managed metadata like
``paused_at`` and ``pause_reason`` survives every read-modify-write
cycle. The dumper is a *best-effort* serializer: it produces YAML that
round-trips back to the same in-memory dict, but it does not guarantee
byte-identical output to the input file (e.g. a value that *needs*
quoting in strict YAML will be quoted on dump even if the original
file left it unquoted).
"""

from __future__ import annotations

from typing import Any


# ============================================================
#  Public API
# ============================================================


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse a markdown document with YAML frontmatter.

    Returns ``(metadata, body)`` where ``metadata`` is a dict of all
    frontmatter fields (including any unknown ones the caller does not
    recognise) and ``body`` is the text after the closing ``---``
    delimiter (preserving the original line breaks).

    Raises ``ValueError`` if the file is missing the opening or closing
    ``---`` marker, or if the frontmatter block is not a YAML mapping.
    """
    if text is None:
        raise ValueError("text must not be None")
    if text == "":
        return {}, ""
    # Normalise line endings so the parser is portable across platforms.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        raise ValueError("frontmatter must start with '---' on the first line")
    end: int | None = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        raise ValueError("frontmatter is missing closing '---'")
    meta_text = "\n".join(lines[1:end])
    body = "\n".join(lines[end + 1 :])
    # Strip the leading blank lines (the format separator between the
    # closing `---` and the content). Trailing newlines are preserved
    # so user-written content (which typically ends with `\n`) survives
    # the round-trip without loss.
    body = body.lstrip("\n")
    metadata = parse_yaml(meta_text) if meta_text.strip() else {}
    if not isinstance(metadata, dict):
        raise ValueError("frontmatter must be a YAML mapping at the top level")
    return metadata, body


def dump_frontmatter(metadata: dict[str, Any], body: str = "") -> str:
    """Serialise ``metadata`` + ``body`` back to a markdown document.

    The output starts with ``---\\n``, then YAML key/value lines, then
    ``---\\n``, then a blank line, then ``body`` (if non-empty), then
    a trailing newline. Field order is whatever ``metadata`` provides
    (Python 3.7+ guarantees dict insertion order, so unknown fields
    keep their original position when round-tripping).
    """
    out: list[str] = ["---"]
    _dump_yaml_block(metadata, out, indent=0)
    out.append("---")
    if body:
        # Body should not start with the blank line we already have.
        out.append("")
        out.append(body.rstrip("\n"))
    out.append("")
    return "\n".join(out)


# ============================================================
#  Internal: scalar helpers
# ============================================================


def _strip_comment(line: str) -> str:
    """Remove trailing ``# ...`` from ``line`` (respects single/double quotes)."""
    in_quote: str | None = None
    for i, ch in enumerate(line):
        if ch in ('"', "'"):
            if in_quote is None:
                in_quote = ch
            elif in_quote == ch:
                in_quote = None
        elif ch == "#" and in_quote is None:
            return line[:i].rstrip()
    return line


def _parse_scalar(text: str) -> Any:
    """Parse a YAML scalar literal (string / int / float / bool / null)."""
    s = text.strip()
    if s == "":
        return None
    # Quoted string
    if len(s) >= 2 and (
        (s[0] == '"' and s[-1] == '"')
        or (s[0] == "'" and s[-1] == "'")
    ):
        inner = s[1:-1]
        # Unescape double-quoted strings minimally
        if s[0] == '"':
            inner = inner.replace('\\"', '"').replace("\\\\", "\\")
        return inner
    lower = s.lower()
    if lower in ("true", "yes", "on"):
        return True
    if lower in ("false", "no", "off"):
        return False
    if lower in ("null", "~"):
        return None
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def _parse_flow_list(text: str) -> list[Any]:
    """Parse a flow-style list literal like ``[a, b, c]`` (no nested flows)."""
    s = text.strip()
    if not (s.startswith("[") and s.endswith("]")):
        raise ValueError(f"not a flow list: {text!r}")
    inner = s[1:-1].strip()
    if not inner:
        return []
    items: list[str] = []
    buf: list[str] = []
    depth = 0
    in_quote: str | None = None
    for ch in inner:
        if in_quote is not None:
            buf.append(ch)
            if ch == in_quote:
                in_quote = None
        elif ch in ('"', "'"):
            in_quote = ch
            buf.append(ch)
        elif ch in "[{":
            depth += 1
            buf.append(ch)
        elif ch in "]}":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            items.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        items.append("".join(buf).strip())
    return [_parse_scalar(item) for item in items]


# ============================================================
#  Internal: block parser
# ============================================================


def parse_yaml(text: str) -> Any:
    """Parse a YAML block (top-level mapping or sequence)."""
    raw_lines = text.split("\n")
    entries: list[tuple[int, str]] = []
    for raw in raw_lines:
        stripped = _strip_comment(raw)
        if not stripped.strip():
            continue
        indent = len(stripped) - len(stripped.lstrip())
        content = stripped[indent:]
        entries.append((indent, content))

    if not entries:
        return {}

    root: dict[str, Any] = {}
    # Each stack entry: (indent_level, container). -1 sentinel keeps the
    # root from being popped when we encounter top-level entries.
    stack: list[tuple[int, Any]] = [(-1, root)]

    i = 0
    while i < len(entries):
        indent, content = entries[i]
        # Pop until the top of the stack is at a strictly smaller indent.
        while stack[-1][0] >= indent:
            stack.pop()
        _, parent = stack[-1]

        if content == "-" or content.startswith("- "):
            # List item
            if not isinstance(parent, list):
                raise ValueError(
                    f"unexpected list item at indent {indent}: {content!r}"
                )
            item_content = content[2:].strip() if content != "-" else ""
            if not item_content:
                parent.append(None)
            elif _looks_like_dict_entry(item_content):
                key, _, value = item_content.partition(":")
                key = key.strip()
                value = value.strip()
                new_dict: dict[str, Any] = {key: None}
                parent.append(new_dict)
                if value.startswith("[") and value.endswith("]"):
                    new_dict[key] = _parse_flow_list(value)
                elif value:
                    new_dict[key] = _parse_scalar(value)
                # Always push the new dict so subsequent lines at deeper
                # indent (continuation of the same list item) can attach.
                stack.append((indent, new_dict))
            else:
                parent.append(_parse_scalar(item_content))
        elif ":" in content:
            key, _, value = content.partition(":")
            key = key.strip()
            value = value.strip()
            if not isinstance(parent, dict):
                raise ValueError(
                    f"dict entry in non-dict container at indent {indent}: {content!r}"
                )
            if value.startswith("[") and value.endswith("]"):
                parent[key] = _parse_flow_list(value)
            elif value:
                parent[key] = _parse_scalar(value)
            else:
                # Empty value: peek to decide list vs mapping
                if i + 1 < len(entries):
                    _next_indent, next_content = entries[i + 1]
                    if next_content == "-" or next_content.startswith("- "):
                        new_list: list[Any] = []
                        parent[key] = new_list
                        stack.append((indent, new_list))
                    else:
                        new_dict = {}
                        parent[key] = new_dict
                        stack.append((indent, new_dict))
                else:
                    parent[key] = None
        else:
            # Bare scalar at top level (no key, no dash) — ignore.
            # Real YAML would error, but in TODO.md this should not occur.
            pass

        i += 1
    return root


def _looks_like_dict_entry(item: str) -> bool:
    """Heuristic: does ``item`` look like ``key: value`` (start of a mapping)?

    Returns True only when the key before the first ``:`` is a simple
    ASCII identifier (letters/digits/underscore/dash, starting with a
    letter or underscore). This intentionally rejects Chinese keys
    and keys containing spaces, which we treat as scalar strings.
    """
    if ":" not in item:
        return False
    key = item.split(":", 1)[0].strip()
    if not key:
        return False
    if not (key[0].isalpha() or key[0] == "_"):
        return False
    return all(c.isalnum() or c in "_-" for c in key)


# ============================================================
#  Internal: dumper
# ============================================================


# Characters that mandate quoting a string scalar (per YAML 1.2).
_QUOTE_TRIGGER_CHARS = set("[]{},:?#&*!|>'\"%@`")


def _needs_quoting(s: str) -> bool:
    """Return True if string ``s`` must be quoted to be parsed unambiguously."""
    if not s:
        return True
    # Leading characters that have special meaning
    if s[0] in "#&*!|>[{}-'\"" or s[0] in "%@`":
        return True
    # Leading/trailing whitespace
    if s != s.strip():
        return True
    # Any character with structural meaning in YAML (flow indicators,
    # key separator, comment, list separator, etc.).
    if any(c in s for c in _QUOTE_TRIGGER_CHARS):
        return True
    # ":" followed by space (would be parsed as key:value)
    if ": " in s or s.endswith(":"):
        return True
    # " #" mid-string (would start a comment)
    if " #" in s:
        return True
    # Booleans / null markers
    if s.lower() in ("true", "false", "null", "~", "yes", "no", "on", "off"):
        return True
    # Numbers (incl. negatives and floats)
    try:
        float(s)
        return True
    except ValueError:
        pass
    return False


def _format_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        if _needs_quoting(value):
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        return value
    return str(value)


def _dump_yaml_block(data: Any, out: list[str], indent: int) -> None:
    """Dump a YAML value at the given indent (no leading key)."""
    prefix = " " * indent
    if isinstance(data, dict):
        for k, v in data.items():
            _dump_key_value(k, v, out, indent)
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                _dump_dict_as_list_item(item, out, indent)
            else:
                out.append(f"{prefix}- {_format_scalar(item)}")
    else:
        out.append(f"{prefix}{_format_scalar(data)}")


def _dump_key_value(key: str, value: Any, out: list[str], indent: int) -> None:
    prefix = " " * indent
    if value is None:
        out.append(f"{prefix}{key}:")
    elif isinstance(value, (str, int, float, bool)):
        out.append(f"{prefix}{key}: {_format_scalar(value)}")
    elif isinstance(value, list):
        if not value:
            out.append(f"{prefix}{key}: []")
        elif all(isinstance(item, (str, int, float, bool, type(None))) for item in value):
            items = [_format_scalar(item) for item in value]
            out.append(f"{prefix}{key}: [{', '.join(items)}]")
        else:
            out.append(f"{prefix}{key}:")
            for item in value:
                if isinstance(item, dict):
                    _dump_dict_as_list_item(item, out, indent)
                else:
                    out.append(f"{prefix}  - {_format_scalar(item)}")
    elif isinstance(value, dict):
        out.append(f"{prefix}{key}:")
        for k, v in value.items():
            _dump_key_value(k, v, out, indent + 2)
    else:
        out.append(f"{prefix}{key}: {_format_scalar(value)}")


def _dump_dict_as_list_item(d: dict[str, Any], out: list[str], indent: int) -> None:
    """Dump a dict as a YAML list item (first key on ``- `` line, rest aligned)."""
    prefix = " " * indent
    items = list(d.items())
    for j, (k, v) in enumerate(items):
        # First key is prefixed with `- ` at indent+2; subsequent keys align at indent+4.
        first_prefix = f"{prefix}  - {k}: "
        rest_prefix = f"{prefix}    {k}: "
        line_prefix = first_prefix if j == 0 else rest_prefix
        if v is None:
            out.append(f"{prefix}  - {k}:" if j == 0 else f"{prefix}    {k}:")
        elif isinstance(v, (str, int, float, bool)):
            out.append(f"{line_prefix}{_format_scalar(v)}")
        elif isinstance(v, list):
            if not v:
                out.append(f"{line_prefix}[]")
            elif all(isinstance(item, (str, int, float, bool, type(None))) for item in v):
                inner = ", ".join(_format_scalar(item) for item in v)
                out.append(f"{line_prefix}[{inner}]")
            else:
                out.append(f"{prefix}  - {k}:" if j == 0 else f"{prefix}    {k}:")
                child_indent = indent + 4 if j == 0 else indent + 6
                for sub_item in v:
                    if isinstance(sub_item, dict):
                        _dump_dict_as_list_item(sub_item, out, child_indent - 2)
                    else:
                        out.append(
                            f"{' ' * child_indent}- {_format_scalar(sub_item)}"
                        )
        elif isinstance(v, dict):
            out.append(f"{prefix}  - {k}:" if j == 0 else f"{prefix}    {k}:")
            child_indent = indent + 4 if j == 0 else indent + 6
            for sk, sv in v.items():
                _dump_key_value(sk, sv, out, child_indent)
        else:
            out.append(f"{line_prefix}{_format_scalar(v)}")
