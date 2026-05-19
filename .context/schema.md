<!-- AUTO_START -->
# Context: `schema.py`

> **[auto-generated — không sửa tay phần này]**
> Language: `python`
> Source files: 1

## [auto] Public Types & Dataclasses

- `FunctionInfo` — metadata của một function (name, params, return type, doc, line)
- `StructInfo` — metadata của một struct/class/interface
- `ModuleContext` — aggregated context của một thư mục: functions + structs + imports + ipc hooks
- `ParserPlugin` — descriptor cho một language plugin: extensions, find_dirs, parse_dir, skip_dirs, ipc_label
- `REGISTRY: dict[str, ParserPlugin]` — global plugin registry
- `register_plugin(plugin)` — đăng ký plugin vào REGISTRY

## [auto] Key Constants

- `AUTO_START` / `AUTO_END` — HTML comment markers cho vùng auto
- `MANUAL_SECTION` — template mặc định cho [manual] khi tạo file mới
<!-- AUTO_END -->

<!-- MANUAL_START -->
## [manual] Design Decisions

### `signature(language)` — tại sao là method của FunctionInfo, không phải của parser

Renderer (`merger.py`) cần sinh signature — không phải parser. Parser chỉ extract data. Merger chịu trách nhiệm presentation. Vì vậy `signature()` thuộc về `FunctionInfo` (data layer) với `language` param, không phải thuộc về từng parser.

Nếu để trong parser: mỗi parser phải implement rendering logic → duplication. Nếu để trong merger: merger phải biết về từng language → coupling.

`FunctionInfo.signature(language)` là điểm duy nhất chịu trách nhiệm "data → display string". Đúng với single responsibility.

### `ParserPlugin.ipc_label` — tại sao không hardcode trong merger

IPC label là ngữ nghĩa thuộc về ecosystem của language, không phải về rendering. Rust/Tauri gọi là "Tauri Commands". WordPress gọi là "WordPress Hooks". Python Django có thể gọi là "URL Endpoints". Merger không nên biết điều này — plugin mới biết.

### `REGISTRY` là global dict — trade-off đã cân nhắc

Global mutable state là anti-pattern trong nhiều context. Chấp nhận ở đây vì:
1. Tool là single-process, không concurrent
2. REGISTRY chỉ được write lúc import time (register_plugin), sau đó read-only
3. Alternative (dependency injection) sẽ làm CLI code phức tạp hơn không cần thiết

## [manual] Invariants & Constraints

- `FunctionInfo.signature()` PHẢI backward compatible — default `language="rust"` để không break existing code
- `REGISTRY` chỉ được mutate qua `register_plugin()`, không được assign trực tiếp
- `MANUAL_SECTION` template KHÔNG được xóa bất kỳ section nào — agent dựa vào template để biết [manual] chưa được điền

## [manual] Behavior chưa implement

- `signature()` cho Python, Go chưa có case — hiện tại rơi vào generic fallback
- `ModuleContext.tauri_commands` field name vẫn là "tauri_commands" dù giờ dùng cho WP hooks và các IPC bridge khác. Rename thành `ipc_hooks` sẽ semantic hơn — nhưng là breaking change, để V3.
<!-- MANUAL_END -->
