import os
import re
import sys

ROOT = os.getcwd()

# -----------------------------
# Config
# -----------------------------
PROTECTED_PATHS = [
    "_config.yml",
    "_data",
    "_layouts",
    "scripts",
    "README.md",
    "CODEOWNERS",
]

# Course data files, one per language (_data/en.yml, _data/pt.yml, ...)
METADATA_FILE_PATTERN = re.compile(r"^_data/[a-z]{2}\.yml$")


def is_metadata_file(file):
    return bool(METADATA_FILE_PATTERN.match(file))

ALLOWED_EXTENSIONS = {".md", ".jpg", ".jpeg", ".png"}

errors = []
warnings = []

# -----------------------------
# Input layer (DO NOT FILTER HERE)
# -----------------------------
def read_changed_files():
    try:
        with open("changed_files.txt", "r", encoding="utf-8") as f:
            files = []
            for line in f:
                parts = line.strip().split("\t")

                if not parts:
                    continue

                status = parts[0]

                # For normal files (M, A, etc.)
                if len(parts) == 2:
                    files.append(parts[1])

                # For renames (Rxxx old new)
                elif status.startswith("R") and len(parts) == 3:
                    files.append(parts[2])  # use new path

            return files

    except FileNotFoundError:
        return []


# -----------------------------
# Validation helpers
# -----------------------------
def check_file_name(file_path):
    name = os.path.basename(file_path)

    if name == "index.md":
        return

    base = os.path.splitext(name)[0]

    if not (
        re.match(r"^\d{3}-[a-z0-9-]+$", base)
        or re.match(r"^\d+\.[a-z0-9-]+$", base)
    ):
        errors.append(f"❌ Invalid file name: {file_path}")

def check_renames():
    try:
        with open("changed_files.txt", "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]

        for line in lines:
            parts = line.split("\t")

            status = parts[0]

            # -----------------------------
            # Detect rename (Rxxx)
            # -----------------------------
            if status.startswith("R"):
                old_path = parts[1]
                new_path = parts[2]

                errors.append(
                    f"❌ File/folder rename not allowed: {old_path} → {new_path}"
                )

    except FileNotFoundError:
        warnings.append("⚠️ Could not verify renames")


def check_fontmatter(file_path, content):
    name = os.path.basename(file_path)

    if name == "README.md":
        return

    if not content.startswith("---"):
        errors.append(f"❌ Missing fontmatter in {file_path}")
        return

    parts = content.split("---")

    if len(parts) < 3:
        errors.append(f"❌ Invalid fontmatter format in {file_path}")
        return

    fontmatter = parts[1]

    if "layout: default" not in fontmatter:
        errors.append(f'❌ Missing "layout: default" in {file_path}')

    title_match = re.search(r"title:\s*(.+)", fontmatter)

    if not title_match:
        errors.append(f'❌ Missing "title" in {file_path}')
    elif not title_match.group(1).strip():
        errors.append(f'❌ Empty "title" in {file_path}')


def check_links_and_images(file_path, content):
    dir_path = os.path.dirname(file_path)

    # Links
    for match in re.finditer(r"\[.*?\]\((.*?)\)", content):
        link = match.group(1)

        if link.startswith("./") or link.startswith("../"):
            target = os.path.abspath(os.path.join(dir_path, link))
            if not os.path.exists(target):
                errors.append(f"❌ Broken link in {file_path} → {link}")

    # Images
    for match in re.finditer(r"!\[.*?\]\((.*?)\)", content):
        img = match.group(1)

        # Skip external images
        if img.startswith("http"):
            continue

        # if not img.startswith("http"):
        #     img_path = os.path.abspath(os.path.join(dir_path, img))
        #     if not os.path.exists(img_path):
        #         errors.append(f"❌ Missing image in {file_path} → {img}")

        # -----------------------------
        # Handle root-relative paths
        # -----------------------------
        if img.startswith("/"):
            img_path = os.path.join(ROOT, img.lstrip("/"))
            # -----------------------------
        # Handle relative paths
        # -----------------------------
        else:
            img_path = os.path.abspath(os.path.join(dir_path, img))

        if not os.path.exists(img_path):
            errors.append(f"❌ Missing image in {file_path} → {img}")


def check_protected_files():
    try:
        with open("changed_files.txt", "r", encoding="utf-8") as f:
            changed = [line.strip() for line in f if line.strip()]

        for file in changed:
            # Allow explicitly permitted files
            if is_metadata_file(file):
                continue

            for protected in PROTECTED_PATHS:
                if file.startswith(protected):
                    errors.append(f"❌ Protected file modified: {file}")

    except FileNotFoundError:
        warnings.append("⚠️ Could not verify protected files")


def run_checks(file_path, content):
    check_file_name(file_path)
    check_fontmatter(file_path, content)
    check_links_and_images(file_path, content)


# -----------------------------
# Report
# -----------------------------
def build_report():
    lines = []
    lines.append("## 🤖 Lint Report\n")

    if errors:
        lines.append("### ❌ Errors")
        lines.extend(errors)

    if warnings:
        lines.append("\n### ⚠️ Warnings")
        lines.extend(warnings)

    if not errors and not warnings:
        lines.append("✅ All checks passed!")

    return "\n".join(lines)


def write_outputs(report):
    # Write file
    with open("report.txt", "w", encoding="utf-8") as f:
        f.write(report)

    # Export to GitHub Actions env
    github_env = os.environ.get("GITHUB_ENV")
    if github_env:
        with open(github_env, "a", encoding="utf-8") as f:
            f.write(f"LINT_REPORT<<EOF\n{report}\nEOF\n")


# -----------------------------
# Main
# -----------------------------
def main():
    changed_files = read_changed_files()

    if not changed_files:
        print("❌ No changed files detected.")
        return 1

    for file in changed_files:
        full_path = os.path.join(ROOT, file)
        ext = os.path.splitext(file)[1].lower()

        # -----------------------------------
        # 1. Bypass metadata file i.e. en.yml
        # -----------------------------------
        if is_metadata_file(file):
            continue

        # -----------------------------
        # 2. Validate extension
        # -----------------------------
        if ext not in ALLOWED_EXTENSIONS:
            errors.append(f"❌ Invalid file type: {file}")
            continue

        # -----------------------------
        # 2. Markdown validation
        # -----------------------------
        if ext == ".md":
            if os.path.exists(full_path):
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()

                run_checks(full_path, content)
            else:
                errors.append(f"❌ Missing markdown file: {file}")

        # -----------------------------
        # 3. Image validation (placeholder)
        # -----------------------------
        elif ext in {".jpg", ".jpeg", ".png"}:
            if not os.path.exists(full_path):
                errors.append(f"❌ Missing image file: {file}")

    check_protected_files()
    check_renames()

    report = build_report()

    print(report)
    write_outputs(report)

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
