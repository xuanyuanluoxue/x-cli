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
``x.py:SUBCOMMAND_HANDLERS``. No core changes required.

The Phase 4 split (this file) was the final step of the v0.4.y
roadmap item — ``x.py`` is now reduced to entry-point glue (~200
lines) and all action logic lives in plugins/ + core/.
"""