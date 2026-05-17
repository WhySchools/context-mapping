"""
tests/test_staleness.py — Unit tests cho staleness detection và tensions writer.

Chạy: pytest tests/test_staleness.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from staleness import (
    compute_hash,
    extract_old_hash,
    inject_hash_into_marker,
    extract_auto_content,
    check_file,
    StalenessResult,
    StalenessReport,
)
from tensions_writer import (
    write_staleness_tensions,
    write_single_staleness,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

SAMPLE_AUTO = """\
# Context: `wp-content/plugins/skvn-marine-blocks/includes`

> **[auto-generated — không sửa tay phần này]**
> Language: `php`
> Source files: 3

## [auto] WordPress Hooks (add_action / add_filter)

Các hàm được hook vào WordPress qua `add_action()` / `add_filter()`:

- **`register_blocks`**
- **`enqueue_assets`**
"""

SAMPLE_MANUAL = """\
<!-- MANUAL_START -->
## [manual] Design Decisions
Slider là container block, slide là inner block.

## [manual] Invariants & Constraints
- Editor không autoplay.
- Reduced motion phải được respect.
<!-- MANUAL_END -->"""


def _make_context_file(tmp_path: Path, auto_content: str, with_hash: bool = True) -> Path:
    """Tạo .context file với cấu trúc đúng."""
    f = tmp_path / "skvn-marine-blocks_includes.md"
    if with_hash:
        h = compute_hash(auto_content)
        now = datetime.now().strftime("%Y-%m-%dT%H:%M")
        start_marker = f"<!-- AUTO_START | hash: {h} | built: {now} -->"
    else:
        start_marker = "<!-- AUTO_START -->"

    text = f"{start_marker}\n{auto_content}\n<!-- AUTO_END -->\n\n{SAMPLE_MANUAL}"
    f.write_text(text, encoding="utf-8")
    return f


def _make_stale_result(tmp_path: Path) -> StalenessResult:
    f = _make_context_file(tmp_path, SAMPLE_AUTO)
    return StalenessResult(
        context_file=f,
        old_hash="aabbccdd",
        new_hash="11223344",
        built_at="2026-05-17T09:00",
        is_stale=True,
    )


# ── compute_hash ──────────────────────────────────────────────────────────────

class TestComputeHash:
    def test_deterministic(self):
        assert compute_hash("hello") == compute_hash("hello")

    def test_different_content_different_hash(self):
        assert compute_hash("hello") != compute_hash("world")

    def test_returns_8_chars(self):
        assert len(compute_hash("test content")) == 8

    def test_returns_hex(self):
        h = compute_hash("test")
        int(h, 16)  # raises ValueError jika bukan hex


# ── extract_old_hash ──────────────────────────────────────────────────────────

class TestExtractOldHash:
    def test_extracts_hash_from_marker_with_hash(self):
        text = "<!-- AUTO_START | hash: a1b2c3d4 | built: 2026-05-17T10:00 -->"
        h, built = extract_old_hash(text)
        assert h == "a1b2c3d4"
        assert built == "2026-05-17T10:00"

    def test_returns_none_for_plain_marker(self):
        text = "<!-- AUTO_START -->"
        h, built = extract_old_hash(text)
        assert h is None
        assert built is None

    def test_returns_none_when_no_marker(self):
        h, built = extract_old_hash("no marker here")
        assert h is None
        assert built is None

    def test_works_with_full_file(self):
        f_content = (
            "<!-- AUTO_START | hash: deadbeef | built: 2026-01-01T00:00 -->\n"
            "content\n"
            "<!-- AUTO_END -->\n"
            "<!-- MANUAL_START -->\nmanual\n<!-- MANUAL_END -->"
        )
        h, built = extract_old_hash(f_content)
        assert h == "deadbeef"


# ── inject_hash_into_marker ───────────────────────────────────────────────────

class TestInjectHashIntoMarker:
    def test_plain_marker_gets_hash(self):
        text = "before\n<!-- AUTO_START -->\ncontent"
        result = inject_hash_into_marker(text, "newhash1")
        assert "hash: newhash1" in result
        assert "built:" in result
        assert "<!-- AUTO_START -->" not in result

    def test_old_hash_is_replaced(self):
        text = "<!-- AUTO_START | hash: oldhash1 | built: 2026-01-01T00:00 -->"
        result = inject_hash_into_marker(text, "newhash2")
        assert "newhash2" in result
        assert "oldhash1" not in result

    def test_content_after_marker_preserved(self):
        text = "<!-- AUTO_START -->\nmy content\n<!-- AUTO_END -->"
        result = inject_hash_into_marker(text, "abc12345")
        assert "my content" in result
        assert "<!-- AUTO_END -->" in result

    def test_only_first_marker_replaced(self):
        # Không nên có 2 AUTO_START nhưng test phòng thủ
        text = "<!-- AUTO_START -->\ncontent\n<!-- AUTO_END -->"
        result = inject_hash_into_marker(text, "abc12345")
        assert result.count("AUTO_START") == 1


# ── extract_auto_content ──────────────────────────────────────────────────────

class TestExtractAutoContent:
    def test_extracts_between_markers(self):
        text = "<!-- AUTO_START -->\nhello world\n<!-- AUTO_END -->"
        result = extract_auto_content(text)
        assert result == "hello world"

    def test_extracts_with_hash_in_marker(self):
        text = (
            "<!-- AUTO_START | hash: abc | built: 2026-01-01 -->\n"
            "content here\n"
            "<!-- AUTO_END -->"
        )
        result = extract_auto_content(text)
        assert result == "content here"

    def test_returns_none_without_start(self):
        assert extract_auto_content("no markers") is None

    def test_returns_none_without_end(self):
        assert extract_auto_content("<!-- AUTO_START -->\ncontent") is None

    def test_manual_section_not_included(self):
        text = (
            "<!-- AUTO_START -->\nauto stuff\n<!-- AUTO_END -->\n"
            "<!-- MANUAL_START -->\nmanual stuff\n<!-- MANUAL_END -->"
        )
        result = extract_auto_content(text)
        assert "manual stuff" not in result
        assert "auto stuff" in result


# ── check_file ────────────────────────────────────────────────────────────────

class TestCheckFile:
    def test_returns_none_if_file_not_exists(self, tmp_path):
        f = tmp_path / "nonexistent.md"
        result = check_file(f, "some content")
        assert result is None

    def test_returns_none_if_no_hash_in_file(self, tmp_path):
        # File format cũ chưa có hash → không phải stale, skip
        f = _make_context_file(tmp_path, SAMPLE_AUTO, with_hash=False)
        result = check_file(f, SAMPLE_AUTO)
        assert result is None

    def test_not_stale_when_content_unchanged(self, tmp_path):
        f = _make_context_file(tmp_path, SAMPLE_AUTO, with_hash=True)
        result = check_file(f, SAMPLE_AUTO)
        assert result is not None
        assert result.is_stale is False

    def test_stale_when_content_changed(self, tmp_path):
        f = _make_context_file(tmp_path, SAMPLE_AUTO, with_hash=True)
        new_content = SAMPLE_AUTO + "\n- **`new_hook`**"
        result = check_file(f, new_content)
        assert result is not None
        assert result.is_stale is True

    def test_stale_result_hashes_correct(self, tmp_path):
        f = _make_context_file(tmp_path, SAMPLE_AUTO, with_hash=True)
        new_content = "completely different"
        result = check_file(f, new_content)
        assert result.old_hash == compute_hash(SAMPLE_AUTO)
        assert result.new_hash == compute_hash(new_content)

    def test_module_name_from_file_stem(self, tmp_path):
        f = _make_context_file(tmp_path, SAMPLE_AUTO, with_hash=True)
        result = check_file(f, "different")
        assert result.module_name == "skvn-marine-blocks_includes"

    def test_built_at_preserved(self, tmp_path):
        f = _make_context_file(tmp_path, SAMPLE_AUTO, with_hash=True)
        result = check_file(f, "different content")
        # built_at phải là string non-empty
        assert result.built_at
        assert result.built_at != "unknown"


# ── write_staleness_tensions ──────────────────────────────────────────────────

class TestWriteStalenssTensions:
    def test_creates_tensions_file_if_not_exists(self, tmp_path):
        context_dir = tmp_path / ".context"
        context_dir.mkdir()
        result = _make_stale_result(tmp_path)
        report = StalenessReport(stale=[result])

        write_staleness_tensions(context_dir, report)

        assert (context_dir / "TENSIONS.md").exists()

    def test_entry_contains_required_fields(self, tmp_path):
        context_dir = tmp_path / ".context"
        context_dir.mkdir()
        result = _make_stale_result(tmp_path)
        report = StalenessReport(stale=[result])

        write_staleness_tensions(context_dir, report)

        text = (context_dir / "TENSIONS.md").read_text()
        assert result.module_name in text
        assert result.old_hash in text
        assert result.new_hash in text
        assert "Pending" in text
        assert "low" in text

    def test_does_not_write_duplicate(self, tmp_path):
        context_dir = tmp_path / ".context"
        context_dir.mkdir()
        result = _make_stale_result(tmp_path)
        report = StalenessReport(stale=[result])

        written1 = write_staleness_tensions(context_dir, report)
        assert len(written1) == 1

        written2 = write_staleness_tensions(context_dir, report)
        assert len(written2) == 0

        # File chỉ có một entry
        text = (context_dir / "TENSIONS.md").read_text()
        assert text.count(result.old_hash) == 1

    def test_appends_to_existing_content(self, tmp_path):
        context_dir = tmp_path / ".context"
        context_dir.mkdir()
        tensions_file = context_dir / "TENSIONS.md"
        tensions_file.write_text("# Tensions Register\n\n## Existing entry\n\n---\n")

        result = _make_stale_result(tmp_path)
        report = StalenessReport(stale=[result])
        write_staleness_tensions(context_dir, report)

        text = tensions_file.read_text()
        assert "Existing entry" in text   # cũ còn nguyên
        assert result.module_name in text  # mới được append

    def test_returns_empty_if_no_stale(self, tmp_path):
        context_dir = tmp_path / ".context"
        context_dir.mkdir()
        report = StalenessReport(stale=[])
        written = write_staleness_tensions(context_dir, report)
        assert written == []
        assert not (context_dir / "TENSIONS.md").exists()

    def test_multiple_stale_modules(self, tmp_path):
        context_dir = tmp_path / ".context"
        context_dir.mkdir()

        r1 = StalenessResult(
            context_file=tmp_path / "mod_a.md",
            old_hash="aaaaaaaa", new_hash="bbbbbbbb",
            built_at="2026-05-17T09:00", is_stale=True,
        )
        r2 = StalenessResult(
            context_file=tmp_path / "mod_b.md",
            old_hash="cccccccc", new_hash="dddddddd",
            built_at="2026-05-17T09:00", is_stale=True,
        )
        report = StalenessReport(stale=[r1, r2])
        written = write_staleness_tensions(context_dir, report)

        assert len(written) == 2
        text = (context_dir / "TENSIONS.md").read_text()
        assert "mod_a" in text
        assert "mod_b" in text


# ── write_single_staleness ────────────────────────────────────────────────────

class TestWriteSingleStaleness:
    def test_returns_true_when_written(self, tmp_path):
        context_dir = tmp_path / ".context"
        context_dir.mkdir()
        result = _make_stale_result(tmp_path)
        assert write_single_staleness(context_dir, result) is True

    def test_returns_false_on_duplicate(self, tmp_path):
        context_dir = tmp_path / ".context"
        context_dir.mkdir()
        result = _make_stale_result(tmp_path)
        write_single_staleness(context_dir, result)
        assert write_single_staleness(context_dir, result) is False


# ── integration: check_file → write ──────────────────────────────────────────

class TestIntegration:
    def test_full_flow_stale_detection_and_write(self, tmp_path):
        """
        Simulate một build cycle đầy đủ:
        1. Tạo context file với hash A
        2. "Code thay đổi" → auto content mới
        3. check_file phát hiện stale
        4. write_staleness_tensions ghi vào TENSIONS.md
        """
        context_dir = tmp_path / ".context"
        context_dir.mkdir()

        # Lần build 1: tạo file với content ban đầu
        context_file = context_dir / "commands.md"
        original_content = "## [auto] Public Functions\n- register_blocks\n"
        h = compute_hash(original_content)
        now = datetime.now().strftime("%Y-%m-%dT%H:%M")
        context_file.write_text(
            f"<!-- AUTO_START | hash: {h} | built: {now} -->\n"
            f"{original_content}\n"
            f"<!-- AUTO_END -->\n\n"
            f"<!-- MANUAL_START -->\n[manual] chưa điền\n<!-- MANUAL_END -->"
        )

        # Lần build 2: content thay đổi (thêm function mới)
        new_content = original_content + "- enqueue_assets\n"
        result = check_file(context_file, new_content)

        assert result is not None
        assert result.is_stale is True
        assert result.old_hash == h
        assert result.new_hash == compute_hash(new_content)

        # Ghi vào TENSIONS.md
        report = StalenessReport(stale=[result])
        written = write_staleness_tensions(context_dir, report)
        assert len(written) == 1

        tensions_text = (context_dir / "TENSIONS.md").read_text()
        assert "commands" in tensions_text
        assert "Pending" in tensions_text

    def test_no_false_positive_on_second_build_same_content(self, tmp_path):
        """
        Build 2 lần với cùng content → không phải stale.
        """
        context_dir = tmp_path / ".context"
        context_dir.mkdir()

        context_file = _make_context_file(tmp_path, SAMPLE_AUTO, with_hash=True)
        # Copy vào context_dir để test
        import shutil
        dest = context_dir / context_file.name
        shutil.copy(context_file, dest)

        result = check_file(dest, SAMPLE_AUTO)
        assert result is not None
        assert result.is_stale is False
