#!/usr/bin/env python3
"""Audit public API docstring coverage across younggeul packages.

Walks all public modules under core/src/ and apps/kr-seoul-apartment/src/,
enumerates public classes, functions, and methods, and reports coverage
statistics.  The output is Markdown suitable for docs/api-audit.md.

Usage:
    python scripts/audit_docstrings.py > docs/api-audit.md
"""

from __future__ import annotations

import ast
import datetime
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ROOTS: list[Path] = [
    Path("core/src/younggeul_core"),
    Path("apps/kr-seoul-apartment/src/younggeul_app_kr_seoul_apartment"),
]

SHORTEN_MAP: dict[str, str] = {
    "younggeul_core.": "core.",
    "younggeul_app_kr_seoul_apartment.": "app.",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_public(name: str) -> bool:
    return not name.startswith("_")


def _has_docstring(node: ast.AST) -> bool:
    body = getattr(node, "body", None)
    if not body or not isinstance(body[0], ast.Expr):
        return False
    return isinstance(body[0].value, (ast.Str, ast.Constant))


def _docstring_text(node: ast.AST) -> str:
    ds_node = node.body[0].value  # type: ignore[union-attr]
    return str(ds_node.value if isinstance(ds_node, ast.Constant) else ds_node.s).strip()  # type: ignore[union-attr]


def _classify(node: ast.AST) -> str:
    """Return 'full', 'partial', or 'missing'."""
    if not _has_docstring(node):
        return "missing"
    text = _docstring_text(node)
    if not text:
        return "missing"

    has_args = "Args:" in text or "Arguments:" in text
    has_returns = "Returns:" in text or "Return:" in text

    if isinstance(node, ast.ClassDef):
        return "full" if len(text) > 20 else "partial"

    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        args = [a.arg for a in node.args.args if a.arg not in ("self", "cls")]
        args += [a.arg for a in node.args.kwonlyargs]
        has_return_stmt = any(isinstance(n, ast.Return) and n.value is not None for n in ast.walk(node))
        if args and not has_args:
            return "partial"
        if has_return_stmt and not has_returns:
            return "partial"
        return "full"

    return "full" if len(text) > 10 else "partial"


def _shorten(name: str) -> str:
    for long, short in SHORTEN_MAP.items():
        name = name.replace(long, short)
    return name


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def audit_file(filepath: Path, root: Path) -> list[dict[str, str | int]]:
    """Audit one Python source file and return symbol records."""
    rel = filepath.relative_to(root.parent.parent)
    module = str(rel).replace("/", ".").replace(".py", "").replace(".__init__", "")

    try:
        tree = ast.parse(filepath.read_text())
    except Exception:
        return [
            {
                "module": module,
                "file": str(rel),
                "symbol": "<parse error>",
                "kind": "error",
                "status": "error",
                "line": 0,
            }
        ]

    symbols: list[dict[str, str | int]] = []

    mod_status = _classify(tree) if tree.body else "missing"
    symbols.append(
        {
            "module": module,
            "file": str(rel),
            "symbol": "(module)",
            "kind": "module",
            "status": mod_status,
            "line": 1,
        }
    )

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if _is_public(node.name):
                symbols.append(
                    {
                        "module": module,
                        "file": str(rel),
                        "symbol": node.name,
                        "kind": "function",
                        "status": _classify(node),
                        "line": node.lineno,
                    }
                )
        elif isinstance(node, ast.ClassDef):
            if _is_public(node.name):
                symbols.append(
                    {
                        "module": module,
                        "file": str(rel),
                        "symbol": node.name,
                        "kind": "class",
                        "status": _classify(node),
                        "line": node.lineno,
                    }
                )
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if _is_public(item.name):
                            symbols.append(
                                {
                                    "module": module,
                                    "file": str(rel),
                                    "symbol": f"{node.name}.{item.name}",
                                    "kind": "method",
                                    "status": _classify(item),
                                    "line": item.lineno,
                                }
                            )

    return symbols


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def main() -> None:
    all_symbols: list[dict[str, str | int]] = []
    for root in ROOTS:
        for filepath in sorted(root.rglob("*.py")):
            all_symbols.extend(audit_file(filepath, root))

    total = len(all_symbols)
    full = sum(1 for s in all_symbols if s["status"] == "full")
    partial = sum(1 for s in all_symbols if s["status"] == "partial")
    missing = sum(1 for s in all_symbols if s["status"] == "missing")
    pct_full = (full / total * 100) if total else 0
    pct_any = ((full + partial) / total * 100) if total else 0

    print("# Docstring Coverage Audit Report")
    print()
    print(f"**Generated**: {datetime.datetime.now(tz=datetime.timezone.utc).strftime('%Y-%m-%d')}")
    print(f"**Total files scanned**: {len(set(str(s['file']) for s in all_symbols))}")
    print(f"**Total public symbols**: {total}")
    print()
    print("## Summary")
    print()
    print("| Metric | Count |")
    print("|--------|-------|")
    print(f"| ✅ Full docstring | {full} |")
    print(f"| ⚠️ Partial docstring | {partial} |")
    print(f"| ❌ Missing docstring | {missing} |")
    print(f"| **Total** | **{total}** |")
    print(f"| **Coverage (full)** | **{pct_full:.1f}%** |")
    print(f"| **Coverage (full+partial)** | **{pct_any:.1f}%** |")
    print()

    # Per-module breakdown
    modules: dict[str, list[dict[str, str | int]]] = defaultdict(list)
    for s in all_symbols:
        modules[str(s["module"])].append(s)

    core_modules = {k: v for k, v in modules.items() if "younggeul_core" in k}
    app_modules = {k: v for k, v in modules.items() if "younggeul_app" in k}

    print("## Per-Module Breakdown")
    print()
    for section, section_modules in [
        ("Core (`younggeul_core`)", core_modules),
        ("App (`younggeul_app_kr_seoul_apartment`)", app_modules),
    ]:
        print(f"### {section}")
        print()
        print("| Module | Total | ✅ Full | ⚠️ Partial | ❌ Missing | Coverage |")
        print("|--------|-------|---------|------------|------------|----------|")
        for mod_name in sorted(section_modules.keys()):
            syms = section_modules[mod_name]
            f = sum(1 for s in syms if s["status"] == "full")
            p = sum(1 for s in syms if s["status"] == "partial")
            m = sum(1 for s in syms if s["status"] == "missing")
            t = len(syms)
            cov = f"{(f / t * 100):.0f}%" if t else "N/A"
            short = _shorten(mod_name).replace("src.", "")
            print(f"| `{short}` | {t} | {f} | {p} | {m} | {cov} |")
        print()

    # Gap list
    print("## Gap List (Missing & Partial Docstrings)")
    print()
    print("### Priority: Missing Docstrings")
    print()
    print("| File | Symbol | Kind | Line |")
    print("|------|--------|------|------|")
    for s in all_symbols:
        if s["status"] == "missing":
            short_file = _shorten(str(s["file"]))
            print(f"| `{short_file}` | `{s['symbol']}` | {s['kind']} | L{s['line']} |")

    print()
    print("### Lower Priority: Partial Docstrings (missing Args/Returns sections)")
    print()
    print("| File | Symbol | Kind | Line |")
    print("|------|--------|------|------|")
    for s in all_symbols:
        if s["status"] == "partial":
            short_file = _shorten(str(s["file"]))
            print(f"| `{short_file}` | `{s['symbol']}` | {s['kind']} | L{s['line']} |")


if __name__ == "__main__":
    main()
