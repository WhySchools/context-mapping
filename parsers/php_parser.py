"""
PHP parser: trích xuất functions, classes, WordPress hooks từ AST.

"IPC bridge" của WordPress là add_action() / add_filter() —
chúng là điểm nối giữa plugin code và WordPress core,
tương tự #[tauri::command] trong Tauri.

Dùng tree-sitter-php, không regex.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional, Generator
import tree_sitter_php as tsp
from tree_sitter import Language, Parser, Node

from schema import FunctionInfo, StructInfo, ModuleContext, ParserPlugin, register_plugin

PHP_LANG = Language(tsp.language_php())
_parser = Parser(PHP_LANG)

_SKIP_DIRS = {"vendor", "node_modules", ".git", "cache", "tmp", "dist"}

# add_action / add_filter: callback là argument thứ 2 (index 1)
_WP_HOOK_CALLS = {"add_action", "add_filter"}


# ─── helpers ────────────────────────────────────────────────────────────────

def _text(node: Optional[Node], src: bytes) -> str:
    if node is None:
        return ""
    return src[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _walk(node: Node) -> Generator[Node, None, None]:
    yield node
    for child in node.children:
        yield from _walk(child)


def _first_child_of_type(node: Node, *types: str) -> Optional[Node]:
    return next((c for c in node.children if c.type in types), None)


def _children_of_type(node: Node, *types: str) -> list[Node]:
    return [c for c in node.children if c.type in types]


# ─── doc comment extraction ─────────────────────────────────────────────────

def _extract_phpdoc(node: Node, src: bytes) -> Optional[str]:
    """Lấy /** PHPDoc */ hoặc // comment đứng ngay trước node."""
    parent = node.parent
    if parent is None:
        return None
    siblings = parent.children
    idx = next((i for i, c in enumerate(siblings) if c.id == node.id), -1)
    if idx <= 0:
        return None
    # Walk backwards qua whitespace-only nodes
    i = idx - 1
    while i >= 0 and not siblings[i].is_named:
        i -= 1
    if i < 0:
        return None
    sib = siblings[i]
    if sib.type == "comment":
        t = _text(sib, src).strip()
        if t.startswith("/**"):
            # Strip /** ... */ và các * đầu dòng
            inner = t[3:]
            if inner.endswith("*/"):
                inner = inner[:-2]
            lines = [l.strip().lstrip("*").strip() for l in inner.splitlines()]
            result = " ".join(l for l in lines if l)
            return result or None
        if t.startswith("//"):
            return t[2:].strip() or None
        if t.startswith("#"):
            return t[1:].strip() or None
    return None


# ─── WordPress hook detection ────────────────────────────────────────────────

def _extract_wp_hooks(node: Node, src: bytes) -> list[str]:
    """
    Tìm tất cả add_action() / add_filter() bên trong một function body.
    Trả về danh sách tên callback (argument thứ 2).

    add_action('hook_name', 'callback_fn')   → 'callback_fn'
    add_action('hook_name', [$this, 'method']) → bỏ qua (method call, khó resolve)
    add_filter('hook_name', 'callback_fn', 10, 1) → 'callback_fn'
    """
    hooked: list[str] = []
    for n in _walk(node):
        if n.type != "function_call_expression":
            continue
        name_node = _first_child_of_type(n, "name")
        if name_node is None:
            continue
        fn_name = _text(name_node, src)
        if fn_name not in _WP_HOOK_CALLS:
            continue
        args_node = _first_child_of_type(n, "arguments")
        if args_node is None:
            continue
        args = _children_of_type(args_node, "argument")
        if len(args) < 2:
            continue
        # Argument thứ 2 là callback
        cb = args[1]
        # Chỉ handle string literal callback (ví dụ 'my_function')
        str_node = _first_child_of_type(cb, "string")
        if str_node:
            content = _first_child_of_type(str_node, "string_content")
            if content:
                cb_name = _text(content, src).strip()
                if cb_name and cb_name not in hooked:
                    hooked.append(cb_name)
    return hooked


# ─── function parser ─────────────────────────────────────────────────────────

def _parse_function(node: Node, src: bytes, is_method: bool = False) -> Optional[FunctionInfo]:
    """
    Parse function_definition hoặc method_declaration.
    is_method=True → check visibility_modifier.
    """
    # visibility
    vis_node = _first_child_of_type(node, "visibility_modifier")
    if is_method:
        if vis_node is None:
            is_public = False  # default visibility
        else:
            vis_text = _text(vis_node, src)
            is_public = "public" in vis_text
    else:
        # Top-level functions in PHP are always globally accessible
        is_public = True

    # name
    name_node = _first_child_of_type(node, "name")
    if name_node is None:
        return None
    name = _text(name_node, src)

    # params
    params_node = _first_child_of_type(node, "formal_parameters")
    params: list[str] = []
    if params_node:
        for param in params_node.children:
            if param.type in ("simple_parameter", "variadic_parameter",
                              "property_promotion_parameter"):
                params.append(_text(param, src).strip())

    # return type (PHP 7+: `: ReturnType`)
    ret_type: Optional[str] = None
    found_colon = False
    for c in node.children:
        if c.type == ":":
            found_colon = True
            continue
        if found_colon and c.type not in ("compound_statement",):
            ret_type = _text(c, src).strip()
            break

    doc = _extract_phpdoc(node, src)

    return FunctionInfo(
        name=name,
        is_public=is_public,
        is_async=False,       # PHP không có async/await ở function level
        params=params,
        return_type=ret_type,
        doc_comment=doc,
        line=node.start_point[0] + 1,
    )


# ─── class parser ────────────────────────────────────────────────────────────

def _parse_class(node: Node, src: bytes) -> Optional[StructInfo]:
    """Parse class_declaration → StructInfo (public methods làm fields)."""
    name_node = _first_child_of_type(node, "name")
    if name_node is None:
        return None
    name = _text(name_node, src)

    # Lấy public method names làm "fields" — giống như TS interface
    fields: list[str] = []
    body = _first_child_of_type(node, "declaration_list")
    if body:
        for child in body.children:
            if child.type == "method_declaration":
                vis_node = _first_child_of_type(child, "visibility_modifier")
                vis_text = _text(vis_node, src) if vis_node else ""
                if "public" in vis_text or not vis_node:
                    method_name = _first_child_of_type(child, "name")
                    if method_name:
                        fields.append(f"{_text(method_name, src)}: method")

    doc = _extract_phpdoc(node, src)
    return StructInfo(
        name=name,
        is_public=True,
        fields=fields,
        doc_comment=doc,
        derives=[],   # PHP dùng implements/extends, không cần capture ở đây
    )


# ─── file parser ─────────────────────────────────────────────────────────────

def parse_php_file(path: Path) -> tuple[list[FunctionInfo], list[StructInfo], list[str], list[str]]:
    """
    Returns (functions, classes, imports, wp_hook_callbacks).

    wp_hook_callbacks: tên các function được đăng ký qua add_action/add_filter.
    Đây là "Tauri commands" tương đương của WordPress plugin.
    """
    src = path.read_bytes()
    tree = _parser.parse(src)

    functions: list[FunctionInfo] = []
    classes: list[StructInfo] = []
    imports: list[str] = []
    wp_hooks: list[str] = []

    for node in _walk(tree.root_node):
        if node.type == "function_definition":
            fn = _parse_function(node, src, is_method=False)
            if fn:
                functions.append(fn)

        elif node.type == "class_declaration":
            cls = _parse_class(node, src)
            if cls:
                classes.append(cls)

        elif node.type in ("require_expression", "require_once_expression",
                           "include_expression", "include_once_expression"):
            t = _text(node, src).strip().rstrip(";")
            if t:
                imports.append(t)

        elif node.type == "namespace_use_declaration":
            t = _text(node, src).strip()
            if t:
                imports.append(t)

        # Detect add_action / add_filter ở top level hoặc trong function body
        elif node.type == "function_call_expression":
            name_node = _first_child_of_type(node, "name")
            if name_node and _text(name_node, src) in _WP_HOOK_CALLS:
                args_node = _first_child_of_type(node, "arguments")
                if args_node:
                    args = _children_of_type(args_node, "argument")
                    if len(args) >= 2:
                        cb = args[1]
                        str_node = _first_child_of_type(cb, "string")
                        if str_node:
                            content = _first_child_of_type(str_node, "string_content")
                            if content:
                                cb_name = _text(content, src).strip()
                                if cb_name and cb_name not in wp_hooks:
                                    wp_hooks.append(cb_name)

    return functions, classes, imports, wp_hooks


# ─── directory parser ────────────────────────────────────────────────────────

def parse_php_directory(dir_path: Path, project_root: Path) -> ModuleContext:
    """Parse toàn bộ .php files trong một thư mục (không recursive)."""
    rel = str(dir_path.relative_to(project_root))
    ctx = ModuleContext(path=rel, language="php")

    php_files = sorted(dir_path.glob("*.php"))
    for f in php_files:
        ctx.source_files.append(str(f.relative_to(project_root)))
        fns, classes, imports, hooks = parse_php_file(f)
        ctx.public_functions.extend(fns)
        ctx.structs.extend(classes)
        ctx.tauri_commands.extend(h for h in hooks if h not in ctx.tauri_commands)
        for imp in imports:
            if imp not in ctx.imports:
                ctx.imports.append(imp)

    return ctx


def _find_php_dirs(root: Path) -> list[Path]:
    """Tìm các thư mục chứa .php files, bỏ qua vendor/ và cache/."""
    dirs: list[Path] = []
    for php in root.rglob("*.php"):
        if any(p in php.parts for p in _SKIP_DIRS):
            continue
        if php.parent not in dirs:
            dirs.append(php.parent)
    return sorted(dirs)


# ─── Register plugin ─────────────────────────────────────────────────────────

register_plugin(ParserPlugin(
    language="php",
    extensions=[".php"],
    find_dirs=_find_php_dirs,
    parse_dir=parse_php_directory,
    skip_dirs=_SKIP_DIRS,
    ipc_label="WordPress Hooks (add_action / add_filter)",
))
