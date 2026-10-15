# Configuration file for the Sphinx documentation builder.

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

sys.path.insert(0, str(SRC))

project = "zarrcurator"
author = "Kameswarrao Modali"
copyright = f"{date.today().year}, {author}"

extensions = [
    "myst_parser",
    "rst2pdf.pdfbuilder",
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

master_doc = "index"
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# Read the Docs look and feel for HTML output.
html_theme = "sphinx_rtd_theme"
html_title = "zarrcurator documentation"

# PDF output via rst2pdf.
pdf_documents = [
    ("index", "zarrcurator", "zarrcurator Documentation", author),
]

