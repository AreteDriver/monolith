#!/usr/bin/env python3
"""Convert aegis-whitepaper.md to styled PDF via weasyprint."""

from pathlib import Path

import markdown
from weasyprint import HTML

DOCS = Path(__file__).parent
MD_FILE = DOCS / "aegis-whitepaper.md"
PDF_FILE = DOCS / "aegis-whitepaper.pdf"

CSS = """
@page {
    size: letter;
    margin: 1in 1in 1in 1in;
    @bottom-center { content: counter(page); font-size: 9pt; color: #666; }
}
body {
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 11pt;
    line-height: 1.5;
    color: #1a1a1a;
}
h1 {
    font-size: 22pt;
    font-weight: 700;
    margin-top: 0;
    margin-bottom: 4pt;
    color: #0d1117;
}
h2 {
    font-size: 15pt;
    font-weight: 700;
    margin-top: 28pt;
    margin-bottom: 8pt;
    color: #0d1117;
    border-bottom: 1px solid #d0d7de;
    padding-bottom: 4pt;
}
h3 {
    font-size: 12pt;
    font-weight: 700;
    margin-top: 20pt;
    margin-bottom: 6pt;
    color: #1a1a1a;
}
p { margin: 6pt 0; }
table {
    border-collapse: collapse;
    width: 100%;
    margin: 10pt 0;
    font-size: 10pt;
}
th, td {
    border: 1px solid #d0d7de;
    padding: 6pt 8pt;
    text-align: left;
}
th {
    background: #f6f8fa;
    font-weight: 600;
}
tr:nth-child(even) { background: #fafbfc; }
code {
    font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
    font-size: 9.5pt;
    background: #f6f8fa;
    padding: 1pt 4pt;
    border-radius: 3pt;
}
pre {
    background: #f6f8fa;
    padding: 12pt;
    border-radius: 6pt;
    font-size: 9pt;
    line-height: 1.4;
    overflow-x: auto;
    border: 1px solid #d0d7de;
}
pre code { background: none; padding: 0; }
ul, ol { margin: 6pt 0; padding-left: 24pt; }
li { margin: 3pt 0; }
strong { color: #0d1117; }
hr {
    border: none;
    border-top: 1px solid #d0d7de;
    margin: 24pt 0;
}
em { color: #57606a; }
a { color: #0969da; text-decoration: none; }
"""

md_text = MD_FILE.read_text()
html_body = markdown.markdown(md_text, extensions=["tables", "fenced_code"])
html_doc = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>{CSS}</style></head>
<body>{html_body}</body></html>"""

HTML(string=html_doc).write_pdf(str(PDF_FILE))
print(f"PDF written to {PDF_FILE}")
