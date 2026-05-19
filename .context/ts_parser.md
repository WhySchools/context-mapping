<!-- AUTO_START -->
# Context: `parsers/ts_parser.py`

> **[auto-generated — không sửa tay phần này]**
> Language: `python` (parses `typescript`, `tsx`)
> Source files: 1

## [auto] Public Functions

### `parse_ts_file(path)` (entry point per-file)
```python
def parse_ts_file(path: Path) -> tuple[list[FunctionInfo], list[StructInfo], list[str]]
```
Returns: (functions, interfaces, imports). Tự detect `.tsx` vs `.ts` để chọn parser.

### `parse_ts_directory(dir_path, project_root)` (entry point per-dir)
```python
def parse_ts_directory(dir_path: Path, project_root: Path) -> ModuleContext
```
Entry point cho registry. Parse `*.ts` + `*.tsx`, không recursive.

## [auto] Exported API

Detection: node cha là `export_statement`. Không detect `export default` anonymous.

## [auto] Plugin Registration

```python
register_plugin(ParserPlugin(
    language="typescript",
    extensions=[".ts", ".tsx"],
    find_dirs=_find_ts_dirs,
    parse_dir=parse_ts_directory,
    skip_dirs={"node_modules", "dist", ".git", "target", ".vite"},
    ipc_label="Exported API",
))
```
<!-- AUTO_END -->

<!-- MANUAL_START -->
## [manual] Design Decisions

### Hai parser riêng biệt: `_ts_parser` và `_tsx_parser`

tree-sitter-typescript expose hai grammar riêng: `language_typescript()` và `language_tsx()`. TSX grammar có thêm JSX node types — nếu dùng TS grammar để parse TSX, JSX expressions sẽ bị parse error và có thể làm bẩn output.

Switch đơn giản: `parser = _tsx_parser if path.suffix == ".tsx" else _ts_parser`. Không phức tạp hơn cần thiết.

### `ipc_label = "Exported API"` — tại sao không phải "Tauri Commands"

TypeScript frontend không có IPC bridge theo nghĩa Tauri. `export function` là API surface của module, không phải hook vào external system. Dùng label "Exported API" phản ánh đúng semantics hơn.

Trong một Tauri project, TypeScript phía frontend gọi `invoke()` — nhưng đó là Rust side expose, không phải TS side. TS context map nên focus vào exported functions mà *components khác consume*, không phải IPC layer.

### `_find_ts_dirs` chuyển từ `cli.py` vào parser — cùng lý do với Rust

V1 nằm trong `cli.py`. V2 move vào `ts_parser.py` như private function, register qua `ParserPlugin.find_dirs`. Logic "bỏ qua `node_modules`, `dist`, `.vite`" là kiến thức của TS ecosystem, không phải CLI.

### Arrow function detection qua `lexical_declaration`

TypeScript có hai cách export function:

```typescript
// 1. function declaration
export function useAuth() { ... }

// 2. arrow function qua const
export const useAuth = () => { ... }
export const useAuth = async (): Promise<Auth> => { ... }
```

Cách 2 parse thành `export_statement → lexical_declaration → variable_declarator → arrow_function`. Parser handle cả hai pattern bằng cách check child type của `export_statement`.

Custom hooks (`useXxx`) và utility functions thường dùng pattern 2 — quan trọng để capture đủ.

## [manual] Invariants & Constraints

- `_SKIP_DIRS` PHẢI include `"node_modules"` — TS projects có thể có hàng nghìn `.ts` files trong deps.
- Parser chỉ extract `export`ed items. Non-exported functions không đưa vào context map — chúng là implementation detail.
- `.tsx` PHẢI dùng `_tsx_parser`, không dùng `_ts_parser`. Ngược lại có thể gây parse error với JSX syntax.
- `parse_ts_directory` KHÔNG được recursive. Cùng lý do với Rust parser.

## [manual] Behavior chưa implement — Phase V3

- `export default function` / `export default class`: pattern này không được detect. Common trong React components (`export default function HomePage()`).
- Re-export detection: `export { foo } from './foo'` — chưa capture. Quan trọng cho barrel files (`index.ts`).
- Generic type parameter trong interface: `interface Repository<T>` — `<T>` bị drop.
- JSX component detection trong TSX: functional components (`function MyComponent(): JSX.Element`) được capture như regular exported function — đúng nhưng thiếu context "đây là React component".
- Vue SFC (`.vue`): chưa support. Người dùng có một số project Vue — cần parser riêng hoặc extend TS parser.
<!-- MANUAL_END -->
