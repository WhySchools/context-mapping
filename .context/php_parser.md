<!-- AUTO_START -->
# Context: `parsers/php_parser.py`

> **[auto-generated — không sửa tay phần này]**
> Language: `python` (parses `php`)
> Source files: 1

## [auto] WordPress Hooks (add_action / add_filter)

Các function được detect là WP IPC bridge:
- Bất kỳ function nào được đăng ký qua `add_action('hook', 'fn_name')` hoặc `add_filter('hook', 'fn_name')`
- Chỉ string literal callback — array `[$this, 'method']` và closure chưa support

## [auto] Public Functions

### `parse_php_file(path)` (entry point per-file)
```python
def parse_php_file(path: Path) -> tuple[list[FunctionInfo], list[StructInfo], list[str], list[str]]
```
Returns: (functions, classes, imports, wp_hook_callbacks)

### `parse_php_directory(dir_path, project_root)` (entry point per-dir)
```python
def parse_php_directory(dir_path: Path, project_root: Path) -> ModuleContext
```

## [auto] Plugin Registration

```python
register_plugin(ParserPlugin(
    language="php",
    extensions=[".php"],
    find_dirs=_find_php_dirs,
    parse_dir=parse_php_directory,
    skip_dirs={"vendor", "node_modules", ".git", "cache", "tmp", "dist"},
    ipc_label="WordPress Hooks (add_action / add_filter)",
))
```
<!-- AUTO_END -->

<!-- MANUAL_START -->
## [manual] Design Decisions

### WordPress hooks là "IPC bridge" của PHP plugin ecosystem

`add_action()` và `add_filter()` là điểm nối giữa plugin code và WordPress core — chính xác là analogy của `#[tauri::command]` trong Tauri. Cả hai đều là:
- Điểm expose code ra bên ngoài
- Điểm mà agent cần biết trước khi sửa — vì side effects có thể rộng
- Điểm không được xóa ngẫu nhiên — breaking change đối với ecosystem

Vì vậy WP hooks được map vào `tauri_commands` field của `ModuleContext` và hiển thị prominent trong [auto] section.

### Chỉ detect string literal callback — tại sao

`add_action('init', 'my_function')` — callback là string → có thể resolve tĩnh qua AST.
`add_action('init', [$this, 'my_method'])` — callback là array → cần biết runtime class instance.
`add_action('init', function() {...})` — closure → anonymous, không có tên để reference.

Static analysis không thể resolve array/closure callback reliably mà không có type inference. False positive (detect sai) tệ hơn false negative (bỏ sót) trong context này — agent đọc [auto] và tin vào nó.

### Top-level PHP functions là public — tại sao

PHP không có access modifier cho top-level functions — mọi function đều globally accessible sau khi file được include. Vì vậy `is_public=True` cho tất cả top-level functions là semantics đúng, không phải assumption.

## [manual] Invariants & Constraints

- Parser KHÔNG được recursive vào subdirectories — `parse_php_directory` chỉ glob `*.php` ở level hiện tại. `cli.py` lo việc find directories.
- `vendor/` PHẢI nằm trong `skip_dirs`. WP projects có vendor/ với hàng nghìn PHP files — parse hết sẽ làm bẩn context map bằng third-party code.
- WP hook detection phải run ở AST level, không phải regex. `add_action` có thể xuất hiện trong string ("use add_action to...") — regex sẽ false positive.

## [manual] Behavior chưa implement — Phase V3

- Array callback detection: `[$this, 'method']` → resolve sang class method
- Closure callback: không có tên, có thể extract body summary
- `@param` / `@return` PHPDoc type extraction vào `FunctionInfo.params` / `return_type`
- `implements` / `extends` extraction vào `StructInfo.derives`
- `add_shortcode()` detection — shortcode là một loại hook khác trong WP ecosystem
<!-- MANUAL_END -->
