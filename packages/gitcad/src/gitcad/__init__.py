"""gitcad — headless, git-native B-rep CAD. This is the namespace root.

The ``gitcad`` namespace is shared by four distributions (``gitcad-core``,
``gitcad-mech``, ``gitcad-ecad``, and this metapackage), each contributing a
portion. This file makes the root a pkgutil-style package so the metapackage
can carry ``gitcad.__version__`` (issue #5) while ``extend_path`` keeps every
sibling portion importable — including split editable installs, where the
portions live in four separate directories.

Only the metapackage ships this file. With ``gitcad-core`` alone installed the
root stays a native namespace package and ``gitcad.__file__`` is ``None`` —
introspect with ``gitcad.__path__`` or ``importlib.metadata``, never
``os.path.dirname(gitcad.__file__)``.
"""

__path__ = __import__("pkgutil").extend_path(__path__, __name__)


def __getattr__(name: str) -> str:
    if name == "__version__":
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version("gitcad")
        except PackageNotFoundError:  # sources on sys.path, nothing installed
            return "0+unknown"
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
