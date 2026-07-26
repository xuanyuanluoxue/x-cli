"""plugins — subcommand plugin package for x-cli.

Each module under this package implements a single top-level subcommand
(e.g. ``x todo``, ``x secret``) and exposes the contract that
``x.py`` expects:

* ``register(parser: argparse.ArgumentParser) -> None`` — bind subparsers
  + flags for all actions of this subcommand
* ``run(args: Sequence[str]) -> int`` — parse ``sys.argv[1:]`` for this
  subcommand and dispatch to the right handler; return exit code

To add a new subcommand, drop a file in this package (e.g. ``foo.py``),
implement ``register`` + ``run``, and add it to
``core.dispatch.SUBCOMMAND_MODULES``. The entry point loads the selected
module on demand and must not statically import concrete plugins.

The Phase 4 split moved action logic out of ``x.py``. The v0.7.x lazy
dispatcher further keeps version/help startup paths independent of plugin
imports.
"""
