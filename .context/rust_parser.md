<!-- AUTO_START -->
# Context: `parsers/rust_parser.py`

> **[auto-generated — không sửa tay phần này]**
> Language: `python` (parses `rust`)
> Source files: 1

## [auto] Public Functions

### `parse_rust_file(path)` (line ~150)
```python
def parse_rust_file(path: Path) -> tuple[list[FunctionInfo], list[StructInfo], list[str], list[str]]
```
Returns: (functions, structs, imports, tauri_commands)

### `parse_rust_directory(dir_path, project_root)` (line ~199)
```python
def parse_rust_directory(dir_path: Path, project_root: Path) -> ModuleContext
```
Entry point cho registry. Parse toàn bộ `*.rs` trong một thư mục, không recursive.

## [auto] Tauri Commands (IPC Bridge)

Detection: `_has_attribute(node, src, "tauri::command")` hoặc `"command"`.
Walk backwards từ function node, qua `attribute_item` nodes, dừng tại bất kỳ named node nào khác.

## [auto] Plugin Registration

```python
register_plugin(ParserPlugin(
    language="rust",
    extensions=[".rs"],
    find_dirs=_find_rust_dirs,
    parse_dir=parse_rust_directory,
    skip_dirs={"target", ".git"},
    ipc_label="Tauri Commands (IPC Bridge)",
))
```
<!-- AUTO_END -->

<!-- MANUAL_START -->
## [manual] Design Decisions

### `_has_attribute()` — tại sao stop tại function boundary

Bug cũ (V1): `_has_attribute()` scan toàn bộ siblings từ index hiện tại về 0, không dừng lại. Nếu function A có `#[tauri::command]` và function B đứng ngay sau mà không có attribute, B vẫn bị detect là Tauri command — false positive.

Fix: walk backwards chỉ qua `attribute_item` và comments. Gặp bất kỳ `is_named` node nào khác (kể cả function khác, struct, use declaration) → break ngay. Đây là "contiguous attribute block" — đúng với Rust semantics.

```python
elif sib.is_named and sib.type not in ("line_comment", "block_comment"):
    break   # ← đây là function boundary guard
```

Invariant: `_has_attribute()` chỉ nhìn attribute block trực tiếp trên function đang xét, không nhìn xa hơn.

### `_find_rust_dirs` chuyển từ `cli.py` vào parser — tại sao

V1: `_find_rust_dirs` nằm trong `cli.py`. Đây là vấn đề về ownership — logic "đâu là thư mục chứa Rust code" là kiến thức của Rust parser, không phải của CLI. CLI chỉ cần biết "hỏi từng plugin xem nó cần scan đâu".

V2: `_find_rust_dirs` là private function của `rust_parser.py`, được đăng ký qua `ParserPlugin.find_dirs`. CLI loop qua registry, gọi `plugin.find_dirs(root)` — không biết gì về Rust cụ thể.

Hệ quả: nếu cần thêm logic "bỏ qua thư mục `generated/`" cho Rust, sửa `rust_parser.py`, không phải `cli.py`.

### Parse không recursive — tại sao

`parse_rust_directory` chỉ glob `*.rs` ở level hiện tại, không rglob. `cli.py` gọi `_find_rust_dirs` để discover tất cả directories, sau đó gọi `_process_directory` cho từng dir một.

Lý do: tránh double-counting. Nếu `src/commands/mod.rs` và `src/commands/auth.rs` đều tồn tại, `_find_rust_dirs` trả về `src/commands/` một lần, và `parse_rust_directory` parse tất cả `*.rs` trong đó. Nếu dùng rglob trong parse, kết hợp với rglob trong find_dirs sẽ tạo ra overlap.

## [manual] Invariants & Constraints

- `_has_attribute()` PHẢI stop tại function boundary — không được scan qua `is_named` non-comment nodes. Đây là fix của bug V1, không được revert.
- `parse_rust_directory` KHÔNG được recursive. Discovery là việc của `_find_rust_dirs` + `cli.py`.
- `_SKIP_DIRS` PHẢI include `"target"` — Rust build artifacts có thể có hàng triệu dòng `.rs` generated code.
- Parser chỉ extract `pub fn` và `pub struct` — private items không đưa vào context map. Invariant: `is_public=True` iff có `visibility_modifier` chứa `"pub"`.

## [manual] Behavior chưa implement — Phase V3

- `pub(crate)` visibility: hiện tại bị skip (không có `pub` keyword) nhưng thực ra là semi-public trong crate. Có thể cần flag riêng trong `FunctionInfo`.
- `enum` extraction: chỉ extract `struct`, không extract `enum`. Rust enums (đặc biệt error enums) thường quan trọng không kém struct.
- `trait` extraction: public traits chưa được capture.
- Generic type parameters trong signature: bị truncate. `fn process<T: Serialize>(item: T)` sẽ mất `<T: Serialize>`.
<!-- MANUAL_END -->
