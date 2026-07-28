# x-cli TODO format spec

This document defines the on-disk format for `x todo` data. It is the
in-project source of truth — older revisions referenced an external
spec file under a legacy system directory; that path is no longer
used.

## Storage layout

```
<todo_dir>/
├── 任务/<name>/TODO.md        # active tasks
└── 归档/<YYYYMMDD>-<name>/TODO.md   # archived tasks
```

`<todo_dir>` defaults to:

* Windows: `%LOCALAPPDATA%\x-cli\todo\`
* Unix: `$XDG_DATA_HOME/x-cli/todo/` (or `~/.local/share/x-cli/todo/`)

Override via `XCLI_TODO_DIR` env var (or the legacy alias
`XAVIER_TODO_DIR`, which prints a one-time deprecation warning).
Tests use this to redirect to a `tmp_path`.

`<name>` is the kebab-case slug derived from the task title (see
`core/slug.py` for the slug algorithm). The folder name is the slug
plus, for active tasks, an optional disambiguation suffix on
duplicate titles.

For archived tasks, the `YYYYMMDD-` prefix is the archive date in the
user's local timezone. It is appended at archive time and used to
sort archived tasks chronologically.

## File format (TODO.md)

Each task is a single Markdown file with a YAML frontmatter header:

```
---
id: <kebab-case-slug>
name: <original task title>
status: <pending | in_progress | blocked | waiting>
priority: <high | medium | low>
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
deadline: <YYYY-MM-DD>      # optional
folder: <relative folder path>
tags: [<tag1>, <tag2>, ...]  # optional
subtasks:                    # optional
  - id: <slug>
    text: <description>
    status: <free text>     # e.g. "⚠️ 未开始"
    done: <bool>
reason: <done | cancelled | expired | failed>  # only on archived tasks
---

# <original task title>

<free-form markdown body>
```

### Field rules

- `id` — kebab-case slug from `name`. Set on creation, never changed.
- `name` — original title (CJK supported). Editable via `x todo update`.
- `status` — one of the four active values, or `archived` (only
  set by the archive command). See `core/models.py:TaskStatus`.
- `priority` — one of `high` / `medium` / `low`. Default `medium`.
  See `core/models.py:Priority`.
- `created` / `updated` — `YYYY-MM-DD` in local timezone. `created`
  is set once; `updated` is bumped on every mutation.
- `deadline` — optional `YYYY-MM-DD`. Used by `x todo stats` to
  classify tasks as "due-soon" / "overdue".
- `tags` — optional YAML list. Tags are free-form short strings.
  CJK supported. Commas / quotes / angle brackets inside a tag
  value should be wrapped in double quotes.
- `subtasks` — optional list of `id` / `text` / `status` / `done`
  rows. x-cli preserves the structure on round-trip but does NOT
  manage subtask state (no `x todo subtask set` command).
- `reason` — only present on archived tasks. One of `done` /
  `cancelled` / `expired` / `failed`. See
  `core/models.py:ArchiveReason`.
- Folder path stored in `folder` is the **path relative to
  `<todo_dir>`** at the time of last write. It is informational —
  the file is found by scanning directories, not by parsing `folder`.

### Free-form body

The markdown body (everything after the second `---`) is preserved
verbatim on round-trip. The CLI does not parse it. It is the user's
notebook for the task — notes, links, checklists.

## Invariants

- The directory tree under `<todo_dir>/任务/` and `<todo_dir>/归档/`
  is the single source of truth. The CLI must NEVER track metadata
  in a sidecar index — there is no `index.json`, no SQLite DB.
- YAML frontmatter is parsed by a hand-rolled lenient parser
  (`core/parser.py`) — unknown fields are preserved on round-trip.
  This means a user can add custom fields (e.g. `paused_at`,
  `description`, `pause_reason`) without breaking the CLI.
- The store is single-process. Concurrent writes are NOT
  serialised. The on-disk format is git-friendly (plain text +
  YAML), so users can use `git init` inside the TODO dir for
  version control if desired.
- No transformation on import (`x todo import --from <dir>`) and
  no transformation on archive. What you write is what you get
  back.

## Migration from another TODO system

`x todo import --from <dir>` reads a foreign directory and
materialises the tasks into the x-cli layout above. The source
directory is read-only — x-cli never writes back. See
`docs/behaviors/todo-import-behavior.md` for the exact rules.
