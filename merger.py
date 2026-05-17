"""
Merger: sinh phần [auto] từ ModuleContext, giữ nguyên phần [manual].
Đây là trái tim của "không overwrite viết tay".

V3: inject hash của [auto] content vào AUTO_START marker sau mỗi lần build.
    Đây là nền tảng để staleness detection hoạt động.
    Không thay đổi gì khác so với V2.
"""
from __future__ import annotations
from pathlib import Path
from schema import ModuleContext, AUTO_START, AUTO_END, MANUAL_SECTION
from staleness import compute_hash, inject_hash_into_marker


# ─── render auto section ─────────────────────────────────────────────────────

def _render_auto(ctx: ModuleContext) -> str:
    lines: list[str] = []
    lines.append(f"# Context: `{ctx.path}`")
    lines.append(f"")
    lines.append(f"> **[auto-generated — không sửa tay phần này]**  ")
    lines.append(f"> Language: `{ctx.language}`  ")
    lines.append(f"> Source files: {len(ctx.source_files)}")
    lines.append("")

    # IPC bridge (Tauri commands, WordPress hooks, v.v.)
    from schema import REGISTRY
    plugin = REGISTRY.get(ctx.language)
    ipc_label = plugin.ipc_label if plugin else "IPC / Hook Bridge"

    if ctx.tauri_commands:
        lines.append(f"## [auto] {ipc_label}")
        lines.append("")
        if ctx.language == "rust":
            lines.append("Các hàm được expose ra frontend qua `invoke()`:")
        elif ctx.language == "php":
            lines.append("Các hàm được hook vào WordPress qua `add_action()` / `add_filter()`:")
        else:
            lines.append("Các hàm được expose qua IPC bridge:")
        lines.append("")
        for cmd in ctx.tauri_commands:
            fn = next((f for f in ctx.public_functions if f.name == cmd), None)
            if fn:
                if fn.doc_comment:
                    lines.append(f"- **`{fn.name}`** — {fn.doc_comment}")
                else:
                    lines.append(f"- **`{fn.name}`**")
                lang_fence = ctx.language if ctx.language in ("rust", "typescript", "php") else "text"
                lines.append(f"  ```{lang_fence}")
                lines.append(f"  {fn.signature(ctx.language)}")
                lines.append(f"  ```")
            else:
                lines.append(f"- **`{cmd}`**")
        lines.append("")

    # Public API (non-IPC)
    non_cmd_fns = [f for f in ctx.public_functions
                   if f.name not in ctx.tauri_commands]
    if non_cmd_fns:
        lines.append("## [auto] Public Functions")
        lines.append("")
        lang_fence = ctx.language if ctx.language in ("rust", "typescript", "php") else "text"
        for fn in non_cmd_fns:
            doc_str = f" — {fn.doc_comment}" if fn.doc_comment else ""
            lines.append(f"### `{fn.name}` (line {fn.line}){doc_str}")
            lines.append(f"```{lang_fence}")
            lines.append(fn.signature(ctx.language))
            lines.append("```")
            lines.append("")

    # Types / Structs / Interfaces / Classes
    if ctx.structs:
        if ctx.language == "rust":
            label = "Structs"
        elif ctx.language == "typescript":
            label = "Types & Interfaces"
        elif ctx.language == "php":
            label = "Classes & Interfaces"
        else:
            label = "Types"
        lines.append(f"## [auto] {label}")
        lines.append("")
        for s in ctx.structs:
            doc_str = f" — {s.doc_comment}" if s.doc_comment else ""
            lines.append(f"### `{s.name}`{doc_str}")
            if s.derives:
                lines.append(f"_derives: {', '.join(s.derives)}_")
            if s.fields:
                lines.append("")
                lines.append("| Field | Type |")
                lines.append("|-------|------|")
                for field_str in s.fields[:10]:
                    parts = field_str.split(":", 1)
                    if len(parts) == 2:
                        fname = parts[0].strip().lstrip("pub").strip()
                        ftype = parts[1].strip()
                        lines.append(f"| `{fname}` | `{ftype}` |")
                    else:
                        lines.append(f"| `{field_str}` | |")
                if len(s.fields) > 10:
                    lines.append(f"| _(+{len(s.fields)-10} more)_ | |")
            lines.append("")

    # Dependencies
    if ctx.imports:
        lines.append("## [auto] Key Imports")
        lines.append("")
        lines.append("```")
        for imp in ctx.imports[:10]:
            lines.append(imp)
        if len(ctx.imports) > 10:
            lines.append(f"// ... +{len(ctx.imports)-10} more")
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


# ─── merge ───────────────────────────────────────────────────────────────────

def merge_context_file(ctx: ModuleContext, output_path: Path) -> str:
    """
    Nếu file đã tồn tại:
      - Tìm vùng AUTO_START...AUTO_END và thay thế
      - Giữ nguyên phần MANUAL
    Nếu file chưa tồn tại:
      - Tạo mới với cả auto lẫn template manual

    V3: sau khi build xong, inject hash của [auto] content vào AUTO_START marker.
    Hash này dùng bởi staleness.check_file() ở lần build sau.

    Returns nội dung cuối cùng đã được write.
    """
    auto_content = _render_auto(ctx)

    # Tính hash TRƯỚC khi assemble block — hash chỉ của content, không của marker
    new_hash = compute_hash(auto_content)

    # AUTO_START marker có hash nhúng vào
    auto_start_with_hash = inject_hash_into_marker(AUTO_START, new_hash)
    auto_block = f"{auto_start_with_hash}\n{auto_content}\n{AUTO_END}"

    if output_path.exists():
        existing = output_path.read_text(encoding="utf-8")

        # Tìm AUTO_START (có thể có hoặc không có hash cũ)
        import re
        auto_start_pattern = re.compile(r"<!--\s*AUTO_START[^>]*-->", re.IGNORECASE)
        start_m = auto_start_pattern.search(existing)
        end_idx = existing.find(AUTO_END)

        if start_m and end_idx != -1:
            before = existing[:start_m.start()]
            after = existing[end_idx + len(AUTO_END):]
            new_content = before + auto_block + after
        else:
            # Markers không tìm thấy → prepend, giữ nguyên phần còn lại
            new_content = auto_block + "\n\n" + existing
    else:
        new_content = auto_block + "\n\n" + MANUAL_SECTION

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(new_content, encoding="utf-8")
    return new_content
