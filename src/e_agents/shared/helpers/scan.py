"""Agnostic module scanner — discovers classes and callable instances by type hierarchy."""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import inspect
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

##### RESULT #####


@dataclass(frozen=True, slots=True)
class ScanResult:
    """Discovered classes and function-like instances."""

    classes: dict[str, type] = field(default_factory=dict)
    functions: dict[str, Any] = field(default_factory=dict)


##### PRIVATE HELPERS #####


def _sc_discover(root: Path, pattern: str = "*.py") -> list[Path]:
    """Collect files matching *pattern* recursively, skip __pycache__ and hidden dirs."""
    return sorted(
        f
        for f in root.rglob(pattern)
        if "__pycache__" not in f.parts and not any(part.startswith(".") for part in f.relative_to(root).parts)
    )


def _sc_resolve(file: Path, entries: list[Path]) -> str | None:
    """Map a .py file to its dotted module name against pre-sorted sys.path entries."""
    resolved = file.resolve()
    for entry in entries:
        try:
            rel = resolved.relative_to(entry)
        except ValueError:
            continue
        parts = list(rel.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts) if parts else None
    return None


def _sc_import(name: str) -> ModuleType | None:
    """Import by dotted name, returning None on any failure."""
    return sys.modules.get(name) or _sc_try_import(name)


def _sc_try_import(name: str) -> ModuleType | None:
    try:
        return importlib.import_module(name)
    except Exception:  # noqa: BLE001
        return None


def _sc_param_names(obj: Any) -> frozenset[str]:
    """Extract parameter names from a (possibly wrapped) callable."""
    target = getattr(obj, "__wrapped__", obj)
    with contextlib.suppress(ValueError, TypeError):
        return frozenset(inspect.signature(target).parameters)
    return frozenset()


def _sc_is_subclass(cls: type, bases: tuple[type, ...], exclude: set[type]) -> bool:
    """Safe issubclass check, excluding base types themselves."""
    with contextlib.suppress(TypeError):
        return issubclass(cls, bases) and cls not in exclude
    return False


def _sc_extract(
    module: ModuleType,
    bases: tuple[type, ...],
    scope: frozenset[str],
    name_filter: list[str] | None,
    kwargs_filter: list[str] | None,
) -> tuple[dict[str, type], dict[str, Any]]:
    """Partition module members into subclasses and instances of bases."""
    classes: dict[str, type] = {}
    functions: dict[str, Any] = {}
    base_set = set(bases)

    for attr in dir(module):
        if attr.startswith("_"):
            continue
        try:
            obj = getattr(module, attr)
        except Exception:  # noqa: BLE001
            continue

        obj_mod = getattr(obj, "__module__", None)
        if obj_mod and obj_mod not in scope:
            continue

        match obj:
            case type() as cls if _sc_is_subclass(cls, bases, base_set):
                classes[attr] = cls
            case _ if (
                isinstance(obj, bases)
                and (not name_filter or any(f in attr for f in name_filter))
                and (not kwargs_filter or any(f in _sc_param_names(obj) for f in kwargs_filter))
            ):
                functions[attr] = obj

    return classes, functions


##### SCANNER #####


class Scanner:
    """Agnostic module scanner — discovers classes and callable instances by type hierarchy."""

    __slots__ = ()

    async def discover(self, path: Path, pattern: str = "*.py") -> list[Path]:
        """Discover files matching *pattern* under *path*."""
        root = path.resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"Discover path is not a directory: {root}")
        return await asyncio.to_thread(_sc_discover, root, pattern)

    async def scan(
        self,
        path: Path,
        bases: tuple[type, ...],
        *,
        func_filter_name: list[str] | None = None,
        func_filter_kwargs: list[str] | None = None,
    ) -> ScanResult:
        """Scan directory for subclasses and instances of given base types."""
        root = path.resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"Scan path is not a directory: {root}")

        files = await asyncio.to_thread(_sc_discover, root)
        entries = sorted(
            (p for e in sys.path if (p := Path(e).resolve()).is_dir()),
            key=lambda p: len(str(p)),
            reverse=True,
        )
        module_names = [n for f in files if (n := _sc_resolve(f, entries))]
        scope = frozenset(module_names)
        classes: dict[str, type] = {}
        functions: dict[str, Any] = {}

        for mod_name in module_names:
            mod = _sc_import(mod_name)
            if mod is None:
                continue
            cls, fns = _sc_extract(mod, bases, scope, func_filter_name, func_filter_kwargs)
            classes.update(cls)
            functions.update(fns)
            await asyncio.sleep(0)

        return ScanResult(classes=classes, functions=functions)
