<!-- AUTO_START -->
# Global Context

> **[auto-generated — không sửa tay phần này]**

## [auto] Tech Stack

- Python 3.12
- tree-sitter 0.25.2 + tree-sitter-rust + tree-sitter-typescript + tree-sitter-php
- Click (CLI framework)
- Rich (console output)

## [auto] Module Index

Load file context của module cụ thể khi làm việc với nó:

- [`schema.py`](.context/schema.md) — dataclasses, ParserPlugin, REGISTRY, markers
- [`merger.py`](.context/merger.md) — render [auto] section, bảo vệ [manual]
- [`cli.py`](.context/cli.md) — build, load, watch commands
- [`parsers/rust_parser.py`](.context/parsers_rust_parser.md) — Rust AST parser + plugin registration
- [`parsers/ts_parser.py`](.context/parsers_ts_parser.md) — TypeScript/TSX AST parser + plugin registration
- [`parsers/php_parser.py`](.context/parsers_php_parser.md) — PHP AST parser + WP hook detection + plugin registration
<!-- AUTO_END -->

<!-- MANUAL_START -->
## [manual] Mô tả dự án

context-gen sinh AST-based context map cho các dự án phần mềm. Mỗi module được đại diện bằng một file `.context/*.md` có hai vùng: `[auto]` (do tool generate từ AST, luôn sync với code) và `[manual]` (do người viết, không bao giờ bị tool xóa).

Mục đích: giảm token budget 80–90% khi load context vào LLM, đồng thời preserve intent — cái mà AST không thể capture.

## [manual] Architecture Decisions — Phase V1→V2

### Quyết định: Parser Registry thay vì if/elif hardcode

**Trước (V1):**
```python
if rs_files:
    ctx = parse_rust_directory(...)
elif ts_files:
    ctx = parse_ts_directory(...)
# PHP bị rơi vào return "", 0, 0
```

**Sau (V2):**
```python
for plugin in REGISTRY.values():
    files = [f for ext in plugin.extensions for f in dir_path.glob(f"*{ext}")]
    if files:
        ctx = plugin.parse_dir(dir_path, project_root)
        ...
```

**Tại sao**: khi PHP được đặt vấn đề, thêm `elif php_files` là giải pháp nhanh nhưng tạo technical debt — mỗi language mới lại sửa `cli.py`. Registry tách biệt hoàn toàn: `cli.py` không cần biết ngôn ngữ nào tồn tại. Thêm language mới = tạo một file parser, gọi `register_plugin()`, import vào `cli.py`. Xong.

**Trade-off chấp nhận**: REGISTRY là global mutable state. Chấp nhận vì tool này single-process, không có concurrency concern.

### Quyết định: `signature(language)` thay vì hardcode Rust syntax

**Trước (V1):** `FunctionInfo.signature()` luôn sinh `pub fn ... -> ReturnType` dù module là TypeScript hay PHP.

**Tại sao đổi**: bug thực sự — TypeScript module trong `[auto]` section hiển thị `pub fn useAuthState(userId: string) -> AuthState`. Sai cả syntax lẫn semantics. Người đọc (human hoặc agent) bị mislead.

**Quyết định**: `signature(language="rust")` — backward compatible, language-aware. Mỗi language có convention riêng:
- Rust: `pub async fn name(params) -> ReturnType`
- TypeScript: `export async function name(params): ReturnType`
- PHP: `public function name(params): ReturnType`

### Quyết định: `load` command dùng stderr cho noise, stdout sạch

**Trước (V1):** `_process_directory()` in ra console (stdout). Khi agent pipe `context-gen load ... | pbcopy` hoặc vào LLM prompt, có noise lẫn vào content.

**Tại sao quan trọng**: `load` là lệnh agent gọi nhiều nhất trong workflow (AGENTS.md step 2). Noise trong stdout = corrupt prompt. Không phải cosmetic bug — là functional bug trong agent workflow.

**Fix**: tách `Console(stderr=True)` cho errors. `_process_directory` nhận `quiet=True` ngầm định khi gọi từ `load`.

### Quyết định: `ipc_label` là property của ParserPlugin

"Tauri Commands (IPC Bridge)" là label đúng cho Rust/Tauri. Nhưng WordPress dùng `add_action` / `add_filter` — một bridge khác hoàn toàn. Nếu hardcode label, PHP module sẽ hiển thị "Tauri Commands" cho WordPress hooks — sai về mặt mental model.

`ipc_label` thuộc về plugin vì plugin là người biết ngữ nghĩa của IPC bridge trong ecosystem của nó.

## [manual] Local Environment Notes

- 2026-05-17: Checked `wsl -l -v` on the Windows host. WSL is available as a command, but no Linux distributions are installed, so there is no active WSL distro to use. Use the Windows/PowerShell environment for this workspace until a distro is installed.
- 2026-05-17 update: Running `wsl -l -v` outside the sandbox shows `Debian` installed and running on WSL 2. The default distro is currently `podman-machine-default`, not Debian. In this Codex session, sandboxed WSL commands still report no distro, while escalated `wsl -d Debian ...` commands time out; Debian may need a manual WSL restart/first-run initialization before agents can reliably use it.

## [manual] Invariants & Constraints — Phase: all

- `[manual]` section KHÔNG BAO GIỜ bị tool overwrite. Đây là invariant cốt lõi của toàn bộ project. Bất kỳ thay đổi nào trong `merger.py` phải verify lại invariant này.
- `load` command PHẢI có stdout sạch. Không được print bất cứ thứ gì ra stdout ngoài content của context file.
- `REGISTRY` chỉ được populate qua `register_plugin()`. Không được mutate trực tiếp từ `cli.py`.
- Parser mới KHÔNG được yêu cầu sửa `cli.py` hay `merger.py`. Nếu cần sửa — đó là signal thiết kế sai.
- `_process_directory()` phải language-agnostic. Không được có bất kỳ `if language == "rust"` nào trong function này.

## [manual] Behavior chưa implement — Phase: V3+

- **`global_context.py` chưa biết về PHP**: stack detection (`has_tauri`, `has_ts`...) chưa có `has_php`. GLOBAL.md sẽ không list "PHP" trong Tech Stack cho WP projects. Cần thêm sau.
- **PyPI packaging**: `pyproject.toml` chưa được viết. `context-gen` chưa installable qua pip.
- **Python parser**: chưa có. Cần cho Django/FastAPI projects.
- **Go parser**: chưa có. Cần cho backend microservices.
- **`[manual]` staleness detection**: chưa có cơ chế phát hiện khi `[manual]` outdated so với code. Open question từ session trước.
- **Multi-language directory**: một thư mục có cả `.rs` và `.ts` (ví dụ generated bindings) — behavior hiện tại lấy plugin đầu tiên match. Cần define rõ priority hoặc merge strategy.
<!-- MANUAL_END -->
