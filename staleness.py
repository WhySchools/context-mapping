"""
staleness.py — Detect khi [auto] section thay đổi nhưng [manual] chưa được review.

Logic:
- Mỗi lần build, merger inject hash của [auto] content vào AUTO_START marker.
- Lần build sau, đọc hash cũ từ marker, tính hash mới, so sánh.
- Nếu khác → stale, caller ghi vào TENSIONS.md.

Không block workflow. Chỉ detect và report.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


# ── Regex ─────────────────────────────────────────────────────────────────────

# Match cả 2 dạng:
#   <!-- AUTO_START -->
#   <!-- AUTO_START | hash: abc12345 | built: 2026-05-17T10:23 -->
_AUTO_START_RE = re.compile(
    r"<!--\s*AUTO_START"
    r"(?:\s*\|\s*hash:\s*(?P<hash>[a-zA-Z0-9]+))?"
    r"(?:\s*\|\s*built:\s*(?P<built>[^\s|>]+))?"
    r"\s*-->",
    re.IGNORECASE,
)

_AUTO_END = "<!-- AUTO_END -->"


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class StalenessResult:
    context_file: Path    # path đến .context/<module>.md
    old_hash: str         # hash lưu trong file
    new_hash: str         # hash vừa tính từ [auto] content mới
    built_at: str         # timestamp của lần build cũ
    is_stale: bool

    @property
    def module_name(self) -> str:
        return self.context_file.stem


@dataclass
class StalenessReport:
    stale: list[StalenessResult] = field(default_factory=list)
    clean: list[StalenessResult] = field(default_factory=list)
    new_files: list[Path] = field(default_factory=list)   # file chưa có hash

    @property
    def has_stale(self) -> bool:
        return bool(self.stale)


# ── Hash ──────────────────────────────────────────────────────────────────────

def compute_hash(content: str) -> str:
    """8-char hex hash, đủ để detect thay đổi."""
    return hashlib.sha256(content.encode()).hexdigest()[:8]


# ── Marker helpers ────────────────────────────────────────────────────────────

def extract_old_hash(file_text: str) -> tuple[str | None, str | None]:
    """
    Đọc hash và built timestamp từ AUTO_START marker trong file.
    Returns (hash, built) — cả hai None nếu không có.
    """
    m = _AUTO_START_RE.search(file_text)
    if not m:
        return None, None
    return m.group("hash"), m.group("built")


def inject_hash_into_marker(text: str, new_hash: str) -> str:
    """
    Rewrite AUTO_START marker để nhúng hash và timestamp mới.

      <!-- AUTO_START -->
      → <!-- AUTO_START | hash: a3f2c1d8 | built: 2026-05-17T10:23 -->

      <!-- AUTO_START | hash: old | built: ... -->
      → <!-- AUTO_START | hash: new | built: 2026-05-17T10:23 -->
    """
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    new_marker = f"<!-- AUTO_START | hash: {new_hash} | built: {now} -->"
    return _AUTO_START_RE.sub(new_marker, text, count=1)


def extract_auto_content(file_text: str) -> str | None:
    """
    Trích nội dung giữa AUTO_START và AUTO_END.
    Returns None nếu không tìm thấy markers.
    """
    start_m = _AUTO_START_RE.search(file_text)
    if not start_m:
        return None
    end_idx = file_text.find(_AUTO_END, start_m.end())
    if end_idx == -1:
        return None
    return file_text[start_m.end():end_idx].strip()


# ── Core check ────────────────────────────────────────────────────────────────

def check_file(context_file: Path, new_auto_content: str) -> StalenessResult | None:
    """
    So sánh hash của [auto] content mới với hash đã lưu trong file.

    Args:
        context_file:     path đến .context/<module>.md
        new_auto_content: nội dung [auto] vừa được render bởi merger (chưa write)

    Returns:
        StalenessResult nếu file đã có hash để so sánh.
        None nếu file chưa tồn tại hoặc chưa có hash (lần đầu chạy).
    """
    if not context_file.exists():
        return None

    existing = context_file.read_text(encoding="utf-8")
    old_hash, built_at = extract_old_hash(existing)

    if old_hash is None:
        # File cũ format chưa có hash → không stale, chỉ là lần đầu
        return None

    new_hash = compute_hash(new_auto_content)
    return StalenessResult(
        context_file=context_file,
        old_hash=old_hash,
        new_hash=new_hash,
        built_at=built_at or "unknown",
        is_stale=(old_hash != new_hash),
    )
