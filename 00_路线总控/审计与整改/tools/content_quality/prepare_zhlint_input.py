from __future__ import annotations

import argparse
import re
from pathlib import Path


EXCLUDED_PARTS = {
    ".git",
    ".tools",
    ".venv",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
}


def sanitize_markdown(text: str) -> str:
    output: list[str] = []
    in_fence = False
    in_front_matter = False

    for line_number, line in enumerate(text.splitlines(keepends=True), start=1):
        stripped = line.strip()
        newline = "\n" if line.endswith("\n") else ""
        if line_number == 1 and stripped == "---":
            in_front_matter = True
            output.append(newline)
            continue
        if in_front_matter:
            if stripped == "---":
                in_front_matter = False
            output.append(newline)
            continue
        if re.match(r"^\s*(```|~~~)", line):
            in_fence = not in_fence
            output.append(newline)
            continue
        if in_fence:
            output.append(newline)
            continue

        cleaned = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", line)
        cleaned = re.sub(r"\[\[([^\]]+)\]\]", "", cleaned)
        cleaned = re.sub(r"\[([^\]]+)\]\((?:[^()]|\([^)]*\))*\)", r"\1", cleaned)
        cleaned = re.sub(r"`[^`]*`", "", cleaned)
        cleaned = re.sub(r"https?://[^\s)>]+", "", cleaned)
        cleaned = re.sub(r"<[^>]+>", "", cleaned)
        output.append(cleaned.rstrip("\r\n") + newline)

    return "".join(output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repository_root", type=Path)
    parser.add_argument("output_root", type=Path)
    args = parser.parse_args()
    root = args.repository_root.resolve()
    output_root = args.output_root.resolve()

    count = 0
    for source in root.rglob("*.md"):
        relative = source.relative_to(root)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        target = output_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        text = source.read_text(encoding="utf-8-sig")
        target.write_text(sanitize_markdown(text), encoding="utf-8", newline="\n")
        count += 1

    print(f"sanitized_markdown_files={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
