"""
tensions_writer.py — Ghi staleness entries vào .context/TENSIONS.md.

Rules:
- Chỉ append, không overwrite entries cũ.
- Idempotent: nếu entry cho (module, old_hash) đã tồn tại thì skip.
- Tạo file mới với header nếu chưa có TENSIONS.md.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from staleness import StalenessResult, StalenessReport


# ── Templates ─────────────────────────────────────────────────────────────────

_TENSIONS_HEADER = """\
# Tensions Register

> Ghi lại các conflict giữa task reasoning và [manual] constraint,
> và các staleness warning khi [auto] thay đổi mà [manual] chưa review.
> Không xóa entries — chỉ update Decision khi resolve.

---

"""

_ENTRY_TEMPLATE = """\
## {timestamp} | context-staleness | {module_name}

### Tension
`[auto]` section thay đổi kể từ lần build trước nhưng `[manual]` chưa được review.

### Context
`context-gen build` phát hiện hash mismatch trong `.context/{module_name}.md`:
- Hash cũ: `{old_hash}` (built: {built_at})
- Hash mới: `{new_hash}`

### Proposal
Review `[manual]` Design Decisions và Invariants của module `{module_name}`.
Xác nhận còn đúng hoặc update nếu cần.
Chạy `context-gen build` lại để clear warning này.

### Constraint
`[manual]` có thể outdated so với code thực tế.

### Severity
low

### Decision
Pending

---
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_or_init(tensions_file: Path) -> str:
    if tensions_file.exists():
        return tensions_file.read_text(encoding="utf-8")
    return _TENSIONS_HEADER


def _entry_exists(text: str, result: StalenessResult) -> bool:
    """
    Tránh duplicate: check cả module name lẫn old_hash.
    Hai điều kiện cùng nhau mới tính là duplicate — tránh false positive
    khi hai module tình cờ có cùng hash.
    """
    return (
        f"Hash cũ: `{result.old_hash}`" in text
        and f"| {result.module_name}" in text
    )


def _format_entry(result: StalenessResult) -> str:
    return _ENTRY_TEMPLATE.format(
        timestamp=datetime.now().strftime("%Y-%m-%dT%H:%M"),
        module_name=result.module_name,
        old_hash=result.old_hash,
        new_hash=result.new_hash,
        built_at=result.built_at,
    )


# ── Public API ────────────────────────────────────────────────────────────────

def write_staleness_tensions(
    context_dir: Path,
    report: StalenessReport,
) -> list[StalenessResult]:
    """
    Ghi staleness entries cho các module stale vào TENSIONS.md.
    Skip duplicates.

    Returns:
        List các StalenessResult đã thực sự được ghi.
    """
    if not report.has_stale:
        return []

    tensions_file = context_dir / "TENSIONS.md"
    existing_text = _load_or_init(tensions_file)

    new_entries: list[str] = []
    written: list[StalenessResult] = []

    for result in report.stale:
        if _entry_exists(existing_text, result):
            continue
        new_entries.append(_format_entry(result))
        written.append(result)

    if not new_entries:
        return []

    updated = existing_text.rstrip("\n") + "\n\n" + "\n".join(new_entries)
    tensions_file.write_text(updated, encoding="utf-8")

    return written


def write_single_staleness(context_dir: Path, result: StalenessResult) -> bool:
    """
    Ghi một staleness entry đơn lẻ (dùng trong load command).
    Returns True nếu đã ghi, False nếu duplicate.
    """
    report = StalenessReport(stale=[result])
    written = write_staleness_tensions(context_dir, report)
    return bool(written)
