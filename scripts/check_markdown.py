"""Check that public Markdown prose is not hard-wrapped inside paragraphs."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {".cache", ".venv", "node_modules"}


def is_special(line: str) -> bool:
    stripped = line.lstrip()
    if not stripped or line.startswith(("  ", "\t")):
        return True
    if stripped.startswith(("#", "|", ">", "```", "~~~", "---", "***", "___")):
        return True
    return bool(re.match(r"^(?:[-*+]\s+|\d+[.)]\s+)", stripped))


def find_hard_wraps(path: Path) -> list[int]:
    lines = path.read_text(encoding="utf-8").splitlines()
    findings: list[int] = []
    in_fence = False
    fence = ""
    for index, line in enumerate(lines[:-1]):
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if not in_fence:
                in_fence, fence = True, marker
            elif marker == fence:
                in_fence, fence = False, ""
            continue
        if in_fence or is_special(line) or is_special(lines[index + 1]):
            continue
        findings.append(index + 1)
    return findings


def main() -> int:
    failures: list[tuple[Path, list[int]]] = []
    for path in sorted(ROOT.rglob("*.md")):
        relative = path.relative_to(ROOT)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if relative.parts[:2] == ("sources", "snapshots"):
            continue
        findings = find_hard_wraps(path)
        if findings:
            failures.append((relative, findings))
    if failures:
        for path, lines in failures:
            print(f"{path}: hard-wrapped prose before lines {', '.join(map(str, lines))}")
        return 1
    print("MARKDOWN_OK: no hard-wrapped public prose paragraphs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
