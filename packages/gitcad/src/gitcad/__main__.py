"""``python -m gitcad`` — the PATH-proof spelling of the ``gitcad`` command
(Windows per-user installs land console scripts off PATH, issue #5)."""

from gitcad.cli import main

if __name__ == "__main__":
    main()
