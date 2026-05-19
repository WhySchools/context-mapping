"""
Global context: sinh file .context/GLOBAL.md mô tả toàn bộ dự án.
Dùng để load đầu tiên vào context window cho bất kỳ task nào.
"""
from __future__ import annotations
from pathlib import Path
from schema import AUTO_START, AUTO_END, MANUAL_SECTION


GLOBAL_MANUAL_TEMPLATE = """<!-- MANUAL_START -->
## [manual] Mô tả dự án
> Dự án làm gì? Giải quyết bài toán gì?

_Chưa có mô tả._

## [manual] Architecture Decisions
> Tại sao chọn Tauri? Tại sao tách core và commands? Trade-off quan trọng nhất?

_Chưa có ghi chú._

## [manual] TDD Convention
> Quy ước test của dự án: tên test, cấu trúc, mock strategy?

_Chưa có ghi chú._

## [manual] Coding Conventions
> Naming, error handling, logging, performance constraints?

_Chưa có ghi chú._

## [manual] Onboarding cho LLM
> Khi bắt đầu một task mới, LLM cần biết gì trước? Có "cạm bẫy" nào trong codebase không?

_Chưa có ghi chú._
<!-- MANUAL_END -->"""


def _has_source_file(project_root: Path, pattern: str, skip_dirs: set[str]) -> bool:
    for path in project_root.rglob(pattern):
        rel_parts = path.relative_to(project_root).parts
        if not any(part in skip_dirs for part in rel_parts):
            return True
    return False


def _context_file_for_module_path(module_path: str) -> str:
    stem = module_path.replace("/", "_").replace("\\", "_")
    return f".context/{stem}.md"


def generate_global_context(project_root: Path, module_paths: list[str], quiet: bool = False) -> None:
    """Sinh .context/GLOBAL.md với danh sách modules được index."""
    output = project_root / ".context" / "GLOBAL.md"

    # Detect tech stack từ file system
    skip_dirs = {"vendor", "node_modules", ".git", "cache", "tmp", "dist", "target"}
    has_tauri  = (project_root / "src-tauri").exists()
    has_rust   = has_tauri or _has_source_file(project_root, "*.rs", skip_dirs)
    has_ts     = any(project_root.glob("src/**/*.ts"))
    has_tsx    = any(project_root.glob("src/**/*.tsx"))
    has_vue    = any(project_root.glob("src/**/*.vue"))
    has_svelte = any(project_root.glob("src/**/*.svelte"))
    has_php    = _has_source_file(project_root, "*.php", skip_dirs)
    cargo_toml = project_root / "src-tauri" / "Cargo.toml"

    stack_parts = []
    if has_tauri:
        stack_parts.append("Tauri v2")
    if has_rust:
        stack_parts.append("Rust (backend)")
    if has_tsx:
        stack_parts.append("React + TypeScript (frontend)")
    elif has_vue:
        stack_parts.append("Vue + TypeScript (frontend)")
    elif has_svelte:
        stack_parts.append("Svelte + TypeScript (frontend)")
    elif has_ts:
        stack_parts.append("TypeScript (frontend)")
    if has_php:
        stack_parts.append("PHP / WordPress")

    # Extract Rust dependencies từ Cargo.toml nếu có
    rust_deps: list[str] = []
    if cargo_toml.exists():
        in_deps = False
        for line in cargo_toml.read_text().splitlines():
            stripped = line.strip()
            if stripped == "[dependencies]":
                in_deps = True
                continue
            if in_deps and stripped.startswith("["):
                in_deps = False
            if in_deps and "=" in stripped and not stripped.startswith("#"):
                dep_name = stripped.split("=")[0].strip()
                rust_deps.append(dep_name)

    lines: list[str] = [
        "# Global Context",
        "",
        "> **[auto-generated — không sửa tay phần này]**",
        "",
        "## [auto] Tech Stack",
        "",
    ]
    for part in stack_parts:
        lines.append(f"- {part}")
    lines.append("")

    lines.append("## [auto] Module Index")
    lines.append("")
    lines.append("Load file context của module cụ thể khi làm việc với nó:")
    lines.append("")
    for mp in sorted(module_paths):
        context_file = _context_file_for_module_path(mp)
        lines.append(f"- [`{mp}`]({context_file})")
    lines.append("")

    if rust_deps:
        lines.append("## [auto] Rust Dependencies (Cargo.toml)")
        lines.append("")
        lines.append("```")
        for dep in rust_deps[:20]:
            lines.append(dep)
        if len(rust_deps) > 20:
            lines.append(f"# ... +{len(rust_deps)-20} more")
        lines.append("```")
        lines.append("")

    auto_content = "\n".join(lines)
    auto_block = f"{AUTO_START}\n{auto_content}\n{AUTO_END}"

    if output.exists():
        existing = output.read_text(encoding="utf-8")
        if AUTO_START in existing and AUTO_END in existing:
            start = existing.index(AUTO_START)
            end   = existing.index(AUTO_END) + len(AUTO_END)
            new_content = existing[:start] + auto_block + existing[end:]
        else:
            new_content = auto_block + "\n\n" + existing
    else:
        new_content = auto_block + "\n\n" + GLOBAL_MANUAL_TEMPLATE

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(new_content, encoding="utf-8")
    if not quiet:
        print(f"  ✓ .context/GLOBAL.md")
