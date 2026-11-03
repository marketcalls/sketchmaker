"""Every app import resolves to a real module and name, including those inside functions.

Lazy imports of deleted modules pass startup and py_compile and only fail when the code
path runs, so this is a permanent guard. Static (ast): nothing is executed. It also
checks every ``settings.X`` read against what app.config defines.
"""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
APP = BACKEND / "app"


def _module_file(dotted: str) -> Path | None:
    base = BACKEND.joinpath(*dotted.split("."))
    if base.with_suffix(".py").is_file():
        return base.with_suffix(".py")
    if (base / "__init__.py").is_file():
        return base / "__init__.py"
    return None


def _assigned_names(target) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        return {name for item in target.elts for name in _assigned_names(item)}
    return set()


def _top_level_names(tree: ast.Module) -> tuple[set[str], list[str]]:
    """Names a module binds at top level (including under if and try), and star imports."""
    names: set[str] = set()
    stars: list[str] = []

    def visit(body) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    names.update(_assigned_names(target))
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                names.update(_assigned_names(node.target))
            elif isinstance(node, ast.Import):
                names.update((a.asname or a.name).split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "*":
                        stars.append(node.module or "")
                    else:
                        names.add(alias.asname or alias.name)
            elif isinstance(node, (ast.If, ast.For, ast.While, ast.With)):
                visit(node.body)
                visit(getattr(node, "orelse", []))
            elif isinstance(node, ast.Try):
                visit(node.body)
                for handler in node.handlers:
                    visit(handler.body)
                visit(node.orelse)
                visit(node.finalbody)

    visit(tree.body)
    return names, stars


def _module_names(dotted: str, seen: set[str] | None = None) -> set[str]:
    seen = seen or set()
    if dotted in seen:
        return set()
    seen.add(dotted)
    path = _module_file(dotted)
    if path is None:
        return set()
    names, stars = _top_level_names(ast.parse(path.read_text(encoding="utf-8")))
    for star in stars:
        names |= _module_names(star, seen)
    return names


def _absolute(module_file: Path, node: ast.ImportFrom) -> str | None:
    """The dotted module of an ImportFrom, with relative imports resolved."""
    if node.level == 0:
        return node.module
    package = list(module_file.relative_to(BACKEND).parent.parts)
    package = package[: len(package) - (node.level - 1)]
    return ".".join(package + ([node.module] if node.module else []))


def _python_files() -> list[Path]:
    return sorted(APP.rglob("*.py"))


def find_broken_imports() -> list[str]:
    problems = []
    for path in _python_files():
        rel = path.relative_to(BACKEND)
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if (alias.name == "app" or alias.name.startswith("app.")) and _module_file(alias.name) is None:
                        problems.append(f"{rel}:{node.lineno}: import {alias.name} (no such module)")
            elif isinstance(node, ast.ImportFrom):
                module = _absolute(path, node)
                if not module or not (module == "app" or module.startswith("app.")):
                    continue
                if _module_file(module) is None:
                    problems.append(f"{rel}:{node.lineno}: from {module} import ... (no such module)")
                    continue
                available = _module_names(module)
                for alias in node.names:
                    if alias.name == "*" or alias.name in available or _module_file(f"{module}.{alias.name}"):
                        continue
                    problems.append(f"{rel}:{node.lineno}: from {module} import {alias.name} (no such name)")
    return problems


def find_unknown_settings() -> list[str]:
    """``settings.X`` in any module that imported settings from app.config."""
    config_tree = ast.parse((APP / "config.py").read_text(encoding="utf-8"))
    known: set[str] = set()
    for node in ast.walk(config_tree):
        if isinstance(node, ast.ClassDef) and node.name == "Settings":
            for item in node.body:
                if isinstance(item, ast.AnnAssign):
                    known.update(_assigned_names(item.target))
                elif isinstance(item, ast.FunctionDef):
                    known.add(item.name)
    problems = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        aliases = {
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module == "app.config"
            for alias in node.names
            if alias.name == "settings"
        }
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                    and node.value.id in aliases and node.attr not in known):
                problems.append(f"{path.relative_to(BACKEND)}:{node.lineno}: {node.value.id}.{node.attr} is not defined")
    return problems


def test_every_app_import_resolves():
    problems = find_broken_imports()
    assert not problems, f"{len(problems)} broken import(s):\n" + "\n".join(problems)


def test_every_settings_attribute_exists():
    problems = find_unknown_settings()
    assert not problems, f"{len(problems)} unknown setting(s):\n" + "\n".join(problems)
