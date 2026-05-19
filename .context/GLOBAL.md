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
- [`merger.py`](.context/merger.md) — render [auto] section, bảo vệ [manual], hash injection
- [`cli.py`](.context/cli.md) — build, load, watch commands
- [`staleness.py`](.context/staleness.md) — hash compute, extract, check_file, StalenessResult
- [`tensions_writer.py`](.context/tensions_writer.md) — ghi staleness entries vào TENSIONS.md
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

### Quyết định: Staleness detection qua hash injection vào AUTO_START marker — Phase V3

**Vấn đề**: không có cơ chế nào báo khi `[manual]` outdated sau khi `[auto]` thay đổi. Agent đọc stale context mà không biết.

**Cơ chế**: sau mỗi lần `merge_context_file()`, inject hash 8-char của `[auto]` content vào AUTO_START marker:
```
<!-- AUTO_START | hash: a3f2c1d8 | built: 2026-05-17T10:23 -->
```
Lần build sau, `staleness.check_file()` đọc hash cũ, tính hash mới. Nếu khác → `[auto]` đã thay đổi → ghi tension vào `TENSIONS.md` tự động (severity: low, Decision: Pending).

**Không block workflow**: chỉ warn, không dừng. Agent vẫn tiếp tục, human review TENSIONS.md sau.

**Files mới**: `staleness.py` (hash logic), `tensions_writer.py` (ghi TENSIONS.md idempotent).

**Trade-off chấp nhận**: hash inject làm AUTO_START marker không còn là plain string `<!-- AUTO_START -->`. `merger.py` và `cli.py` load command phải dùng regex thay vì `str.index()` để tìm marker. Đã update cả hai.

## [manual] Invariants & Constraints — Phase: all

- `[manual]` section KHÔNG BAO GIỜ bị tool overwrite. Đây là invariant cốt lõi của toàn bộ project. Bất kỳ thay đổi nào trong `merger.py` phải verify lại invariant này.
- `load` command PHẢI có stdout sạch. Không được print bất cứ thứ gì ra stdout ngoài content của context file.
- `REGISTRY` chỉ được populate qua `register_plugin()`. Không được mutate trực tiếp từ `cli.py`.
- Parser mới KHÔNG được yêu cầu sửa `cli.py` hay `merger.py`. Nếu cần sửa — đó là signal thiết kế sai.
- `_process_directory()` phải language-agnostic. Không được có bất kỳ `if language == "rust"` nào trong function này.

## [manual] Behavior chưa implement — Phase: V3+

- **PyPI packaging**: `pyproject.toml` chưa được viết. `context-gen` chưa installable qua pip.
- **Python parser**: chưa có. Cần cho Django/FastAPI projects.
- **Go parser**: chưa có. Cần cho backend microservices.
- **Multi-language directory**: một thư mục có cả `.rs` và `.ts` (ví dụ generated bindings) — behavior hiện tại lấy plugin đầu tiên match. Cần define rõ priority hoặc merge strategy.
- **`test_merger.py`**: merger V3 có hash injection logic mới, chưa có test cover riêng. Cần viết để verify [manual] không bị overwrite sau khi inject hash.
- **`docs/prompts/add-parser.md`**: AGENTS.md section 4 reference file này nhưng chưa tồn tại.
- **`requirements.txt`**: AGENTS.md section 2.1 dùng `pip install -r requirements.txt` nhưng file chưa có.
<!-- MANUAL_END -->
