#!/usr/bin/env python3
"""
Export WordPress pages into a nested folder structure using sibling-position numbering.

Features:
- Fetches pages from WP REST API (handles pagination)
- Builds parent->children map
- Sorts siblings by (menu_order, title)
- Assigns each sibling an index in steps of 10 (010, 020, ...) and zero-pads (min width 3)
- Creates directories for pages that have children; parent content goes to index.md
- Child pages (leaf pages) are saved as prefixed files: 010-slug.md
- Converts HTML -> Markdown using markdownify; figures, boxes and Mol* 3D viewers stay as HTML
- Adds Jekyll front matter (layout + title) to every page
- Local-only: writes to the current directory (run it from the course repo root)

Usage:
  python sync_wp_pages.py https://www.ebi.ac.uk/training/online/courses/<course>/
"""

import html
import re
import requests
import shutil
import sys
import unicodedata
from urllib.parse import unquote
from pathlib import Path
import markdownify
import os

OUTPUT_DIR = os.getcwd()  # Write to the course repo root


# Markdown cannot express everything the WordPress pages use. These blocks are
# kept as HTML so they render exactly as on WordPress; the rest becomes Markdown.

# Mol* 3D viewers, pasted in WordPress as whole HTML documents.
MOLSTAR_BLOCK = re.compile(r"<!DOCTYPE html>(?:(?!</html>).)*?molstar\.js.*?</html>", re.S | re.I)
MOLSTAR_WRAPPER = re.compile(r"<!DOCTYPE[^>]*>|</?(?:html|head|body)[^>]*>|<meta[^>]*>|<title>.*?</title>"
                             r"|<link[^>]*rel=\"icon\"[^>]*>|<!-- __MOLSTAR_ANALYTICS__ -->", re.S | re.I)
# Figures: an image in a styled <div> (size, centring), optionally followed by its caption.
FIGURE_BLOCK = re.compile(r"<div style=\"[^\"]*\">\s*<img[^>]*>\s*</div>(?:\s*<figcaption.*?</figcaption>)?", re.S | re.I)
# Boxes: WordPress tables with a single cell, used to frame a block of text.
BOX_BLOCK = re.compile(r"<figure class=\"wp-block-table\">\s*<table[^>]*>\s*<tbody>\s*<tr>\s*<td>"
                       r"((?:(?!</td>).)*)</td>\s*</tr>\s*</tbody>\s*</table>\s*</figure>", re.S | re.I)


def keep_molstar(match):
    block = MOLSTAR_WRAPPER.sub("", match.group(0))
    return f'<div class="molstar-viewer">\n{block}\n</div>'


def keep_box(match):
    return f'<div class="vf-box vf-box--outline">\n<p>{match.group(1).strip()}</p>\n</div>'


def to_markdown(html_content):
    """Convert page HTML to Markdown, keeping what Markdown cannot express as HTML."""
    kept = []

    def keep(transform):
        def replace(match):
            block = transform(match)
            block = "\n".join(line for line in block.splitlines() if line.strip())
            if "{{" in block or "{%" in block:
                block = f"{{% raw %}}\n{block}\n{{% endraw %}}"
            kept.append(block)
            return f"<p>KEPTHTMLBLOCK{len(kept) - 1}</p>"
        return replace

    html_content = MOLSTAR_BLOCK.sub(keep(keep_molstar), html_content)
    html_content = FIGURE_BLOCK.sub(keep(lambda m: m.group(0)), html_content)
    html_content = BOX_BLOCK.sub(keep(keep_box), html_content)

    md = markdownify.markdownify(html_content, heading_style="ATX", sub_symbol="<sub>", sup_symbol="<sup>")
    for i, block in enumerate(kept):
        md = md.replace(f"KEPTHTMLBLOCK{i}", block, 1)
    return md


def pages_api_url(course_url):
    """Build the WP REST pages endpoint from the course URL."""
    return course_url.rstrip("/") + "/wp-json/wp/v2/pages"


def fetch_pages(api_url):
    pages = []
    page_num = 1
    while True:
        print(f"Fetching page {page_num}...")
        resp = requests.get(api_url, params={"per_page": 100, "page": page_num})
        if resp.status_code != 200:
            print(f"Stopped fetching (status {resp.status_code}).")
            break
        data = resp.json()
        if not data:
            break
        pages.extend(data)
        page_num += 1
    return pages


def build_by_parent(pages):
    by_parent = {}
    for p in pages:
        parent_id = p.get("parent", 0)
        by_parent.setdefault(parent_id, []).append(p)
    return by_parent


# Greek letters are common in protein structure titles (α-helix, β-sheet)
GREEK_LETTERS = {
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta",
    "ε": "epsilon", "κ": "kappa", "λ": "lambda", "π": "pi",
}


def sanitize_filename(name):
    # WP slugs are URL-encoded (e.g. %ce%b1 for α); decode and transliterate first
    name = unquote(name)
    for letter, spelled in GREEK_LETTERS.items():
        name = name.replace(letter, spelled)
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    # keep alnum, space, -, _
    cleaned = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip()
    return cleaned.replace(" ", "-")


def front_matter(title):
    """Return Jekyll front matter with a YAML-safe single-quoted title."""
    quoted = title.replace("'", "''")
    return f"---\nlayout: default\ntitle: '{quoted}'\n---\n\n"


def build_index_maps(by_parent):
    """
    For each parent group, sort children and assign indices in steps of 10
    (10, 20, 30, ...) so pages can be inserted later without renumbering.
    Returns:
      index_map: { page_id: index_int }
      padding_map: { page_id: width_int }  (width used for zero-padding)
    """
    index_map = {}
    padding_map = {}

    for parent_id, children in by_parent.items():
        # sort children by (menu_order, title)
        sorted_children = sorted(
            children,
            key=lambda x: (x.get("menu_order", 0), x.get("title", {}).get("rendered", "").lower())
        )
        n = len(sorted_children)
        width = max(3, len(str(n * 10)))  # min width 3 (e.g., 010-)
        for pos, child in enumerate(sorted_children, start=1):
            pid = child["id"]
            index_map[pid] = pos * 10
            padding_map[pid] = width

    return index_map, padding_map


def prefix_for(page_id, index_map, padding_map):
    """Return prefix like '010-' or '' if not in map."""
    if page_id in index_map:
        width = padding_map.get(page_id, 3)
        return f"{index_map[page_id]:0{width}d}-"
    return ""


def write_page(page, by_parent, index_map, padding_map, base_dir):
    """
    Recursively write page and its children under base_dir.
    If page has children -> create directory named <prefix><slug>/ and write parent content to index.md
    If no children -> write <prefix><slug>.md under base_dir
    """
    pid = page["id"]
    slug = page.get("slug", f"page-{pid}")
    title = html.unescape(page.get("title", {}).get("rendered", "")).strip()
    html_content = page.get("content", {}).get("rendered", "")
    md_content = to_markdown(html_content)

    children = sorted(
        by_parent.get(pid, []),
        key=lambda x: (x.get("menu_order", 0), x.get("title", {}).get("rendered", "").lower())
    )

    prefix = prefix_for(pid, index_map, padding_map)
    safe_slug = sanitize_filename(slug)

    if children:
        # create directory with prefix, write parent content to index.md
        page_dir = base_dir / f"{prefix}{safe_slug}"
        page_dir.mkdir(parents=True, exist_ok=True)
        filepath = page_dir / "index.md"
    else:
        # leaf page: write prefixed markdown file in base_dir
        page_dir = base_dir
        page_dir.mkdir(parents=True, exist_ok=True)
        filepath = page_dir / f"{prefix}{safe_slug}.md"

    # Write the markdown file (parent content or leaf content)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"{front_matter(title)}# {title}\n\n{md_content}")

    print(f"✅ Created: {filepath}")

    # Process children recursively
    for child in children:
        write_page(child, by_parent, index_map, padding_map, page_dir)


def main():
    if len(sys.argv) != 2:
        sys.exit("Usage: python sync_wp_pages.py <course URL>")
    pages = fetch_pages(pages_api_url(sys.argv[1]))
    if not pages:
        print("No pages fetched. Exiting.")
        return

    by_parent = build_by_parent(pages)
    index_map, padding_map = build_index_maps(by_parent)

    # Top-level pages are those with parent == 0
    top_pages = sorted(
        by_parent.get(0, []),
        key=lambda x: (x.get("menu_order", 0), x.get("title", {}).get("rendered", "").lower())
    )

    base_dir = Path(OUTPUT_DIR)
    if base_dir.exists():
        # shutil.rmtree(base_dir)
        print(f"Output directory '{base_dir}' already exists. Contents may be overwritten.")
    base_dir.mkdir(parents=True, exist_ok=True)

    for page in top_pages:
        write_page(page, by_parent, index_map, padding_map, base_dir)

    print(f"\n🎉 Export complete. Pages written to '{base_dir}'.")


if __name__ == "__main__":
    main()