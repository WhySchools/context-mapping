"""
tensions_writer.py — Ghi staleness entries vào .context/TENSIONS_OPEN.md.

V3 changes:
- Target file: TENSIONS_OPEN.md (không phải TENSIONS.md)
- Entry format: structured fields (Status, Tags, Milestone)
- Milestone param: đọc từ .context/MILESTONES.md

Rules:
- Chỉ append, không overwrite entries cũ.
- Idempotent: nếu entry cho (module, old_hash) đã tồn tại thì skip.
- Tạo file mới với header nếu chưa có TENSIONS_OPEN.md.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from staleness import StalenessResult, StalenessReport


# ── Headers ───────────────────────────────────────────────────────────────────

_TENSIONS_OPEN_HEADER = """\
# Tensions — OPEN

> Chỉ chứa Status: OPEN entries.
> Agent luôn đọc toàn bộ file này trước mỗi task.
> Khi human resolve → move sang TENSIONS_ACTIVE.md, đổi Status: RESOLVED_ACTIVE.
> Không xóa entries — chỉ move khi resolve.

---

"""


# ── Entry template ─────────────────────────────────────────────────────────────

_ENTRY_TEMPLATE = """\
## {timestamp} | staleness | {module_name}
Status:     OPEN
Tension:    `[auto]` thay đổi nhưng `[manual]` chưa review
Context:    Hash mismatch trong `.context/{module_name}.md` — `{old_hash}` → `{new_hash}` (built: {built_at})
Proposal:   Review `[manual]` Design Decisions và Invariants của module `{module_name}`, confirm hoặc update nếu cần, rebuild để clear warning
Constraint: `[manual]` có thể outdated so với code thực tế
Severity:   low
Tags:       staleness, {module_name}
Milestone:  {milestone}
Decision:   [human fill in]

---
"""


# ── Milestone reader ──────────────────────────────────────────────────────────

def _read_current_milestone(context_dir: Path) -> str:
    """
    Đọc current milestone từ .context/MILESTONES.md.

    Match:
        Current: **V1 / 0.1.0 — ...**
        Current milestone: V1
        Current:  V1

    Returns "unknown" nếu file không tồn tại hoặc không tìm thấy line.
    """
    milestones_file = context_dir / "MILESTONES.md"
    if not milestones_file.exists():
        return "unknown"
    for line in milestones_file.read_text(encoding="utf-8").splitlines():
        line_stripped = line.strip()
        if line_stripped.lower().startswith("current milestone:") or \
                line_stripped.startswith("Current:"):
            value = line_stripped.split(":", 1)[1].strip().strip("*").strip()
            if value:
                return value
    return "unknown"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_or_init(tensions_file: Path) -> str:
    if tensions_file.exists():
        return tensions_file.read_text(encoding="utf-8")
    return _TENSIONS_OPEN_HEADER


def _entry_exists(text: str, result: StalenessResult) -> bool:
    """
    Tránh duplicate: check cả module name lẫn old_hash.
    Cả hai phải match — tránh false positive khi hai module có cùng hash.
    """
    return (
        f"`{result.old_hash}`" in text
        and f"| {result.module_name}" in text
    )


def _format_entry(result: StalenessResult, milestone: str = "unknown") -> str:
    return _ENTRY_TEMPLATE.format(
        timestamp=datetime.now().strftime("%Y-%m-%dT%H:%M"),
        module_name=result.module_name,
        old_hash=result.old_hash,
        new_hash=result.new_hash,
        built_at=result.built_at,
        milestone=milestone,
    )


# ── Public API ────────────────────────────────────────────────────────────────

def write_staleness_tensions(
    context_dir: Path,
    report: StalenessReport,
    milestone: str | None = None,
) -> list[StalenessResult]:
    """
    Ghi staleness entries cho các module stale vào TENSIONS_OPEN.md.
    Skip duplicates.

    Args:
        context_dir: path đến .context/
        report:      StalenessReport từ staleness.py
        milestone:   current milestone string. Nếu None, đọc từ MILESTONES.md.

    Returns:
        List các StalenessResult đã thực sự được ghi.
    """
    if not report.has_stale:
        return []

    if milestone is None:
        milestone = _read_current_milestone(context_dir)

    tensions_file = context_dir / "TENSIONS_OPEN.md"
    existing_text = _load_or_init(tensions_file)

    new_entries: list[str] = []
    written: list[StalenessResult] = []

    for result in report.stale:
        if _entry_exists(existing_text, result):
            continue
        new_entries.append(_format_entry(result, milestone))
        written.append(result)

    if not new_entries:
        return []

    updated = existing_text.rstrip("\n") + "\n\n" + "\n".join(new_entries)
    tensions_file.write_text(updated, encoding="utf-8")

    return written


def write_single_staleness(
    context_dir: Path,
    result: StalenessResult,
    milestone: str | None = None,
) -> bool:
    """
    Ghi một staleness entry đơn lẻ (dùng trong load command).
    Returns True nếu đã ghi, False nếu duplicate.
    """
    report = StalenessReport(stale=[result])
    written = write_staleness_tensions(context_dir, report, milestone=milestone)
    return bool(written)
