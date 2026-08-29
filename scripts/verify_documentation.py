#!/usr/bin/env python3
"""Fail CI when required production documentation or local Markdown links regress.

The checker reports only repository-relative paths and link targets. It never
prints file contents, environment values or deployment configuration.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_PATHS = (
    "README.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "docs/ARCHITECTURE.md",
    "docs/RELEASE_RUNBOOK.md",
    "docs/OPERATIONS_RUNBOOK.md",
    "docs/DATA_RETENTION.md",
    "docs/ROLE_MATRIX.md",
    "docs/CAPACITY_PLANNING.md",
    "docs/SUPPLY_CHAIN_SECURITY.md",
    ".github/CODEOWNERS.example",
    ".github/PULL_REQUEST_TEMPLATE.md",
)
README_REQUIRED_LINKS = (
    "docs/ARCHITECTURE.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "docs/RELEASE_RUNBOOK.md",
    "docs/OPERATIONS_RUNBOOK.md",
    "docs/DATA_RETENTION.md",
    "docs/ROLE_MATRIX.md",
)
SKIP_PARTS = {".git", ".venv", "node_modules", ".pytest_cache", ".ruff_cache", ".codex-tmp"}
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(\s*(?:<(?P<angle>[^>]+)>|(?P<plain>[^)\s]+))")
HEADING = re.compile(r"^#{1,6}\s+(?P<heading>.+?)\s*#*\s*$")
EXTERNAL_SCHEMES = {"http", "https", "mailto", "tel", "data"}


def markdown_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*.md")
        if not any(part in SKIP_PARTS for part in path.relative_to(ROOT).parts)
    )


def local_target(markdown_path: Path, raw_target: str) -> Path | None:
    target = unquote(raw_target.strip())
    parsed = urlsplit(target)
    if parsed.scheme.lower() in EXTERNAL_SCHEMES:
        return None
    path_text = parsed.path
    if not path_text:
        return markdown_path
    if path_text.startswith("/"):
        return ROOT / path_text.lstrip("/")
    return markdown_path.parent / path_text


def github_anchor(heading: str) -> str:
    """Approximate GitHub's Markdown heading slug for local link validation."""
    normalized = re.sub(r"[`*_~]", "", heading).strip().lower()
    normalized = re.sub(r"\s+", "-", normalized)
    return "".join(character for character in normalized if character.isalnum() or character == "-")


def anchors(markdown_path: Path) -> set[str]:
    result: set[str] = set()
    for line in markdown_path.read_text(encoding="utf-8").splitlines():
        match = HEADING.match(line)
        if match:
            result.add(github_anchor(match.group("heading")))
    return result


def main() -> int:
    errors: list[str] = []
    for relative in REQUIRED_PATHS:
        path = ROOT / relative
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            errors.append(f"required documentation is missing or empty: {relative}")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for link in README_REQUIRED_LINKS:
        if link not in readme:
            errors.append(f"README.md must link to: {link}")

    for markdown_path in markdown_files():
        relative = markdown_path.relative_to(ROOT).as_posix()
        for line_number, line in enumerate(markdown_path.read_text(encoding="utf-8").splitlines(), start=1):
            for match in LINK.finditer(line):
                raw_target = match.group("angle") or match.group("plain") or ""
                target = local_target(markdown_path, raw_target)
                if target is not None and not target.exists():
                    errors.append(f"{relative}:{line_number}: missing local Markdown link target: {raw_target}")
                    continue
                fragment = urlsplit(unquote(raw_target.strip())).fragment
                if target is not None and fragment and target.suffix.lower() == ".md":
                    if fragment not in anchors(target):
                        errors.append(f"{relative}:{line_number}: missing Markdown heading anchor: {raw_target}")

    if errors:
        print("Documentation policy failed:", file=sys.stderr)
        print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1
    print("Documentation policy passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
