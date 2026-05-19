"""
consistency.py — Helpers cho context-gen check-consistency command.

Public API:
    check_consistency(root)           → (errors, warnings)
    parse_tension_entries(filepath)   → list[dict]
    format_tensions_file(header, entries) → str
"""
from __future__ import annotations
import re
from pathlib import Path


# ── Milestone extraction ──────────────────────────────────────────────────────

def _extract_current_milestone(filepath: Path) -> str:
    """
    Đọc current milestone từ AGENTS.md hoặc MILESTONES.md.

    Match các format:
        Current: **V1 / 0.1.0 — ...**
        Current milestone: V1
        Current:  V1 / 0.1.0
    """
    if not filepath.exists():
        return ""
    for line in filepath.read_text(encoding="utf-8").splitlines():
        line_stripped = line.strip()
        if line_stripped.lower().startswith("current milestone:") or \
                line_stripped.startswith("Current:"):
            value = line_stripped.split(":", 1)[1].strip().strip("*").strip()
            if value:
                return value
    return ""


# ── Entry status scanning ─────────────────────────────────────────────────────

def _find_entries_with_status(filepath: Path, status: str) -> list[str]:
    """
    Return list entry titles (## heading) có Status: <status>.
    Chỉ match field rõ ràng — không parse free text.
    """
    if not filepath.exists():
        return []
    content = filepath.read_text(encoding="utf-8")
    results: list[str] = []
    current_title = ""
    for line in content.splitlines():
        if line.startswith("## "):
            current_title = line[3:].strip()
        if re.match(rf"^Status:\s+{re.escape(status)}\s*$", line.strip()):
            if current_title:
                results.append(current_title)
    return results


def _find_entries_wrong_milestone(filepath: Path, expected: str) -> list[str]:
    """
    Return list entry titles có Milestone: field khác expected.
    Skip entries không có Milestone field — không flag as error.
    """
    if not filepath.exists():
        return []
    content = filepath.read_text(encoding="utf-8")
    results: list[str] = []
    current_title = ""
    for line in content.splitlines():
        if line.startswith("## "):
            current_title = line[3:].strip()
        m = re.match(r"^Milestone:\s+(.+)$", line.strip())
        if m:
            milestone_val = m.group(1).strip()
            if milestone_val != expected and current_title:
                results.append(f"{current_title}  [Milestone: {milestone_val}]")
    return results


# ── Migration helpers ─────────────────────────────────────────────────────────

def parse_tension_entries(filepath: Path) -> list[dict]:
    """
    Parse TENSIONS.md (format cũ hoặc mới) thành list of dicts.

    Mỗi dict có:
        title  : str  — heading text (sau ##)
        raw    : str  — toàn bộ nội dung entry kể cả heading
        status : str  — OPEN | RESOLVED_ACTIVE | ARCHIVED

    Dùng cho migrate-tensions command.
    """
    if not filepath.exists():
        return []

    content = filepath.read_text(encoding="utf-8")
    entries: list[dict] = []
    current: dict | None = None

    for line in content.splitlines(keepends=True):
        line_stripped = line.strip()

        if line_stripped.startswith("## "):
            if current is not None:
                entries.append(current)
            current = {
                "title": line_stripped[3:].strip(),
                "raw": line,
                "status": "OPEN",
            }
            continue

        if current is None:
            continue

        current["raw"] += line

        # Detect status — support cả format cũ (bold) lẫn format mới (field)
        if re.match(r"^\*\*Status\*\*:\s*RESOLVED", line_stripped) or \
                re.match(r"^Status:\s+RESOLVED_ACTIVE", line_stripped) or \
                re.match(r"^Status:\s+RESOLVED\b", line_stripped):
            current["status"] = "RESOLVED_ACTIVE"
        elif re.match(r"^Status:\s+ARCHIVED", line_stripped):
            current["status"] = "ARCHIVED"
        elif re.match(r"^Status:\s+OPEN", line_stripped):
            current["status"] = "OPEN"

    if current is not None:
        entries.append(current)

    return entries


def format_tensions_file(header: str, entries: list[dict]) -> str:
    """Combine header + entries thành nội dung file hoàn chỉnh."""
    if not entries:
        return header
    parts = [e["raw"].strip() for e in entries]
    return header + "\n\n".join(parts) + "\n"


# ── Main check logic ──────────────────────────────────────────────────────────

def run_consistency_checks(root: Path) -> tuple[list[str], list[str]]:
    """
    Chạy tất cả consistency checks.

    Returns:
        (errors, warnings)
        errors   → exit code 1
        warnings → exit code 0 nhưng in ra stderr
    """
    context_dir = root / ".context"
    errors: list[str] = []
    warnings: list[str] = []

    # ── Check 1: AGENTS.md vs MILESTONES.md current milestone ────────────────
    agents_milestone = _extract_current_milestone(root / "AGENTS.md")
    milestones_current = _extract_current_milestone(context_dir / "MILESTONES.md")

    if not milestones_current:
        warnings.append(
            ".context/MILESTONES.md không tìm thấy hoặc không có 'Current:' line.\n"
            "  → Milestone checks bị skip."
        )
    elif agents_milestone and agents_milestone != milestones_current:
        errors.append(
            "Current milestone mismatch:\n"
            f"  AGENTS.md:               '{agents_milestone}'\n"
            f"  .context/MILESTONES.md:  '{milestones_current}'"
        )

    # ── Check 2: OPEN entries không được nằm trong TENSIONS_ACTIVE ───────────
    open_in_active = _find_entries_with_status(
        context_dir / "TENSIONS_ACTIVE.md", "OPEN"
    )
    if open_in_active:
        errors.append(
            "OPEN entries trong TENSIONS_ACTIVE.md (phải ở TENSIONS_OPEN.md):\n"
            + "\n".join(f"  - {e}" for e in open_in_active)
        )

    # ── Check 3: RESOLVED_ACTIVE không được nằm trong TENSIONS_OPEN ──────────
    resolved_in_open = _find_entries_with_status(
        context_dir / "TENSIONS_OPEN.md", "RESOLVED_ACTIVE"
    )
    if resolved_in_open:
        errors.append(
            "RESOLVED_ACTIVE entries trong TENSIONS_OPEN.md (phải ở TENSIONS_ACTIVE.md):\n"
            + "\n".join(f"  - {e}" for e in resolved_in_open)
        )

    # ── Check 4: ARCHIVED entries không được nằm trong TENSIONS_ACTIVE ───────
    archived_in_active = _find_entries_with_status(
        context_dir / "TENSIONS_ACTIVE.md", "ARCHIVED"
    )
    if archived_in_active:
        errors.append(
            "ARCHIVED entries trong TENSIONS_ACTIVE.md (phải ở TENSIONS_HISTORY.md):\n"
            + "\n".join(f"  - {e}" for e in archived_in_active)
        )

    # ── Check 5: entries trong TENSIONS_ACTIVE với milestone khác current ─────
    if milestones_current:
        wrong = _find_entries_wrong_milestone(
            context_dir / "TENSIONS_ACTIVE.md", milestones_current
        )
        if wrong:
            warnings.append(
                f"Entries trong TENSIONS_ACTIVE.md với Milestone khác '{milestones_current}':\n"
                + "\n".join(f"  - {e}" for e in wrong)
                + "\n  → Candidates for archive nếu milestone đã transition."
            )

    # ── Check 6: TENSIONS.md format cũ chưa migrate ──────────────────────────
    old_tensions = context_dir / "TENSIONS.md"
    new_tensions = context_dir / "TENSIONS_OPEN.md"
    if old_tensions.exists() and not new_tensions.exists():
        warnings.append(
            "TENSIONS.md format cũ detected, chưa migrate.\n"
            "  → Chạy: context-gen migrate-tensions ."
        )

    return errors, warnings
