"""Static registry and lazy loader for x-cli's built-in plugins."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Sequence


SubcommandHandler = Callable[[Sequence[str]], int]

# Keep this mapping explicit and ordered. It is both the user-facing help order
# and a security boundary: user input never becomes an arbitrary module path.
SUBCOMMAND_MODULES: dict[str, str] = {
    "todo": "plugins.todo",
    "secret": "plugins.secret",
    "diary": "plugins.diary",
    "note": "plugins.note",
    "web": "plugins.web",
}


def load_subcommand_handler(name: str) -> SubcommandHandler | None:
    """Load and return the registered plugin's ``run`` callable on demand."""
    module_name = SUBCOMMAND_MODULES.get(name)
    if module_name is None:
        return None

    module = importlib.import_module(module_name)
    handler = getattr(module, "run", None)
    if not callable(handler):
        raise TypeError(f"plugin {module_name!r} has no callable run")
    return handler
