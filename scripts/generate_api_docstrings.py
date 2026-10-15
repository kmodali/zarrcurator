"""Generate API markdown from source docstrings.

Usage:
    python scripts/generate_api_docstrings.py
"""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src" / "zarrcurator"
OUT_FILE = REPO_ROOT / "docs" / "API_DOCSTRINGS.md"


def clean_docstring(doc: str | None) -> str:
    if not doc:
        return "No docstring provided."
    return doc.strip()


def generate() -> None:
    module_files = sorted(
        p for p in SRC_DIR.glob("*.py") if p.name != "__init__.py_default"
    )

    lines: list[str] = []
    lines.append("# zarrcurator API Documentation")
    lines.append("")
    lines.append("Generated from source docstrings.")
    lines.append("")
    lines.append(f"Generated on: {date.today().isoformat()}")
    lines.append("")

    for module_path in module_files:
        src = module_path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        module_name = module_path.stem
        rel = module_path.relative_to(REPO_ROOT).as_posix()

        lines.append(f"## Module: {module_name}")
        lines.append("")
        lines.append(f"Source: {rel}")
        lines.append("")
        lines.append(clean_docstring(ast.get_docstring(tree)))
        lines.append("")

        public_functions = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
        ]
        classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]

        if public_functions:
            lines.append("### Functions")
            lines.append("")
            for fn in public_functions:
                lines.append(f"#### {fn.name}()")
                lines.append("")
                lines.append(clean_docstring(ast.get_docstring(fn)))
                lines.append("")

        if classes:
            lines.append("### Classes")
            lines.append("")
            for cls in classes:
                lines.append(f"#### {cls.name}")
                lines.append("")
                lines.append(clean_docstring(ast.get_docstring(cls)))
                lines.append("")

                methods = [
                    node
                    for node in cls.body
                    if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
                ]
                if methods:
                    lines.append(f"##### Methods of {cls.name}")
                    lines.append("")
                    for method in methods:
                        method_doc = clean_docstring(ast.get_docstring(method)).replace("\n", " ")
                        lines.append(f"- {method.name}(): {method_doc}")
                    lines.append("")

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_FILE}")


if __name__ == "__main__":
    generate()
