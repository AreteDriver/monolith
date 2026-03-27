#!/usr/bin/env python3
"""Convert aegis-whitepaper.md to PDF via markdown→HTML→weasyprint.

Run with: pipx run --spec weasyprint python md2pdf.py
Or after: pipx inject weasyprint markdown
"""

from pathlib import Path

import markdown

MD_PATH = Path(__file__).parent / "aegis-whitepaper.md"
PDF_PATH = Path(__file__).parent / "aegis-whitepaper.pdf"

CSS = """
@page {
    size: letter;
    margin: 1in 1in 1in 1in;
    @bottom-center {
        content: counter(page);
        font-size: 9pt;
        color: #666;
    }
}

body {
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 11pt;
    line-height: 1.55;
    color: #1a1a1a;
    max-width: 100%;
}

h1 {
    font-size: 22pt;
    font-weight: 700;
    margin-top: 0;
    margin-bottom: 4pt;
    color: #111;
}

h2 {
    font-size: 15pt;
    font-weight: 700;
    margin-top: 28pt;
    margin-bottom: 8pt;
    color: #111;
    border-bottom: 1px solid #ddd;
    padding-bottom: 4pt;
    page-break-after: avoid;
}

h3 {
    font-size: 12pt;
    font-weight: 700;
    margin-top: 18pt;
    margin-bottom: 6pt;
    color: #222;
    page-break-after: avoid;
}

p {
    margin-bottom: 8pt;
    text-align: justify;
    orphans: 3;
    widows: 3;
}

strong {
    font-weight: 700;
}

em {
    font-style: italic;
    color: #444;
}

hr {
    border: none;
    border-top: 1px solid #ccc;
    margin: 20pt 0;
}

table {
    width: 100%;
    border-collapse: collapse;
    margin: 10pt 0 14pt 0;
    font-size: 10pt;
    page-break-inside: avoid;
}

th {
    background-color: #f5f5f5;
    border: 1px solid #ccc;
    padding: 6pt 8pt;
    text-align: left;
    font-weight: 700;
}

td {
    border: 1px solid #ccc;
    padding: 5pt 8pt;
    vertical-align: top;
}

tr:nth-child(even) td {
    background-color: #fafafa;
}

pre {
    background-color: #f6f6f6;
    border: 1px solid #ddd;
    border-radius: 3pt;
    padding: 10pt 12pt;
    font-size: 8.5pt;
    line-height: 1.4;
    overflow-x: auto;
    white-space: pre;
    font-family: 'Courier New', Courier, monospace;
    page-break-inside: avoid;
    margin: 8pt 0 12pt 0;
}

code {
    font-family: 'Courier New', Courier, monospace;
    font-size: 9.5pt;
    background-color: #f0f0f0;
    padding: 1pt 3pt;
    border-radius: 2pt;
}

pre code {
    background-color: transparent;
    padding: 0;
    font-size: 8.5pt;
}

ul, ol {
    margin: 6pt 0 10pt 0;
    padding-left: 22pt;
}

li {
    margin-bottom: 3pt;
}

a {
    color: #1a5f9e;
    text-decoration: none;
}
"""


def main():
    md_text = MD_PATH.read_text()

    # Python markdown library requires blank line before list starts (unlike CommonMark).
    # Insert blank lines before lines starting with "- " that follow non-blank, non-list lines.
    import re

    md_text = re.sub(r"(\n)([^\n-][^\n]*\n)(- )", r"\1\2\n\3", md_text)

    html_body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "codehilite", "smarty", "sane_lists"],
        extension_configs={"codehilite": {"guess_lang": False, "css_class": "highlight"}},
    )

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>{CSS}</style>
</head>
<body>
{html_body}
</body>
</html>"""

    from weasyprint import HTML

    HTML(string=full_html).write_pdf(str(PDF_PATH))
    print(f"PDF written to {PDF_PATH} ({PDF_PATH.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
