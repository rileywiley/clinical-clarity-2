"""Structural enforcement of CLAUDE.md golden rule #2.

After importing the engine package and walking its full transitive module
graph, none of the forbidden modules may be reachable. If any is, someone has
added a web/DB/HTTP dependency to the engine and the rule is broken before
the PR can land.

The forbidden list is the union of things the engine should never reach for —
web frameworks, ORMs, network/HTTP clients, the backend's app package.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys

FORBIDDEN_PREFIXES = (
    "fastapi",
    "starlette",
    "sqlalchemy",
    "alembic",
    "asyncpg",
    "psycopg",
    "redis",
    "arq",
    "httpx",
    "requests",
    "urllib3",
    "aiohttp",
    "uvicorn",
    "app",  # the backend's package
)


def _walk_engine_modules() -> set[str]:
    """Force-import every submodule of `engine`, returning their names."""
    import engine as engine_pkg

    seen: set[str] = {engine_pkg.__name__}
    for mod in pkgutil.walk_packages(engine_pkg.__path__, prefix="engine."):
        importlib.import_module(mod.name)
        seen.add(mod.name)
    return seen


def test_engine_imports_nothing_forbidden() -> None:
    _walk_engine_modules()
    leaked = {
        name
        for name in sys.modules
        if any(name == p or name.startswith(p + ".") for p in FORBIDDEN_PREFIXES)
    }
    assert not leaked, (
        f"engine package transitively imported forbidden modules: {sorted(leaked)}. "
        "CLAUDE.md golden rule #2: the engine stays pure."
    )
