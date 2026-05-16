"""
Rust parser: trích xuất public functions, structs, tauri commands từ AST.
Dùng tree-sitter-rust, không regex, không string matching.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional, Generator
import tree_sitter_rust as tsr
from tree_sitter import Language, Parser, Node

from schema import FunctionInfo, StructInfo, ModuleContext

RUST_LANG = Language(tsr.language())
_parser = Parser(RUST_LANG)


# ─── helpers ────────────────────────────────────────────────────────────────

def _children_of_type(node: Node, *types: str) -> list[Node]:
    return [c for c in node.children if c.type in types]


def _first_child_of_type(node: Node, *types: str) -> Optional[Node]:
    return next((c for c in node.children if c.type in types), None)


def _text(node: Optional[Node], src: bytes) -> str:
    if node is None:
        return ""
    return src[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _walk(node: Node) -> Generator[Node, None, None]:
    yield node
    for child in node.children:
        yield from _walk(child)


# ─── doc comment extraction ─────────────────────────────────────────────────

def _extract_doc_comment(node: Node, src: bytes) -> Optional[str]:
    """Lấy /// doc comment đứng ngay trước node."""
    lines = []
    # Traverse prev siblings
    parent = node.parent
    if parent is None:
        return None
    siblings = parent.children
    idx = next((i for i, c in enumerate(siblings) if c.id == node.id), -1)
    if idx <= 0:
        return None
    i = idx - 1
    while i >= 0:
        sib = siblings[i]
        if sib.type in ("line_comment", "block_comment"):
            text = _text(sib, src).strip()
            if text.startswith("///"):
                lines.insert(0, text[3:].strip())
                i -= 1
            else:
                break
        elif sib.type in ("attribute_item",):
            i -= 1  # skip attributes, keep looking
        else:
            break
    return "\n".join(lines) if lines else None


# ─── attribute helpers ───────────────────────────────────────────────────────

def _has_attribute(node: Node, src: bytes, attr: str) -> bool:
    """Check if node has #[attr] in the contiguous attribute block directly above it."""
    parent = node.parent
    if parent is None:
        return False
    siblings = parent.children
    idx = next((i for i, c in enumerate(siblings) if c.id == node.id), -1)
    if idx <= 0:
        return False
    # Walk backwards, only through attribute_item and whitespace — stop at anything else
    i = idx - 1
    while i >= 0:
        sib = siblings[i]
        if sib.type == "attribute_item":
            t = _text(sib, src)
            if attr in t:
                return True
            i -= 1
        elif sib.is_named and sib.type not in ("line_comment", "block_comment"):
            # Hit another statement/item — stop
            break
        else:
            i -= 1
    return False


def _extract_derives(node: Node, src: bytes) -> list[str]:
    """Lấy #[derive(A, B)] từ struct."""
    derives: list[str] = []
    parent = node.parent
    if parent is None:
        return derives
    siblings = parent.children
    idx = next((i for i, c in enumerate(siblings) if c.id == node.id), -1)
    for i in range(max(0, idx - 5), idx):
        sib = siblings[i]
        if sib.type == "attribute_item":
            t = _text(sib, src)
            if "derive" in t:
                # extract inner idents
                inner = t[t.find("(") + 1:t.rfind(")")] if "(" in t else ""
                derives.extend(d.strip() for d in inner.split(",") if d.strip())
    return derives


# ─── function parser ─────────────────────────────────────────────────────────

def _parse_function(node: Node, src: bytes) -> Optional[FunctionInfo]:
    """Parse a function_item node."""
    # visibility
    vis = _first_child_of_type(node, "visibility_modifier")
    is_public = vis is not None and "pub" in _text(vis, src)

    # async
    is_async = any(c.type == "async" for c in node.children)

    # name
    name_node = _first_child_of_type(node, "identifier")
    if name_node is None:
        return None
    name = _text(name_node, src)

    # params
    params_node = _first_child_of_type(node, "parameters")
    params: list[str] = []
    if params_node:
        for param in params_node.children:
            if param.type in ("parameter", "self_parameter"):
                params.append(_text(param, src).strip())

    # return type
    ret_node = _first_child_of_type(node, "type_identifier",
                                     "scoped_type_identifier",
                                     "generic_type",
                                     "reference_type",
                                     "tuple_type")
    # better: look for -> then next type node
    ret_type: Optional[str] = None
    found_arrow = False
    for c in node.children:
        if c.type == "->":
            found_arrow = True
            continue
        if found_arrow and c.type not in ("{", "block"):
            ret_type = _text(c, src).strip()
            break

    doc = _extract_doc_comment(node, src)
    is_cmd = _has_attribute(node, src, "tauri::command") or _has_attribute(node, src, "command")

    return FunctionInfo(
        name=name,
        is_public=is_public,
        is_async=is_async,
        params=params,
        return_type=ret_type,
        doc_comment=doc,
        line=node.start_point[0] + 1,
    ), is_cmd


# ─── struct parser ───────────────────────────────────────────────────────────

def _parse_struct(node: Node, src: bytes) -> Optional[StructInfo]:
    vis = _first_child_of_type(node, "visibility_modifier")
    is_public = vis is not None and "pub" in _text(vis, src)

    name_node = _first_child_of_type(node, "type_identifier")
    if name_node is None:
        return None
    name = _text(name_node, src)

    fields: list[str] = []
    field_list = _first_child_of_type(node, "field_declaration_list")
    if field_list:
        for f in field_list.children:
            if f.type == "field_declaration":
                fields.append(_text(f, src).strip())

    doc = _extract_doc_comment(node, src)
    derives = _extract_derives(node, src)

    return StructInfo(
        name=name,
        is_public=is_public,
        fields=fields,
        doc_comment=doc,
        derives=derives,
    )


# ─── file parser ─────────────────────────────────────────────────────────────

def parse_rust_file(path: Path) -> tuple[list[FunctionInfo], list[StructInfo], list[str], list[str]]:
    """
    Returns (functions, structs, imports, tauri_commands).
    tauri_commands là tên các fn có #[tauri::command].
    """
    src = path.read_bytes()
    tree = _parser.parse(src)

    functions: list[FunctionInfo] = []
    structs: list[StructInfo] = []
    imports: list[str] = []
    tauri_commands: list[str] = []

    for node in _walk(tree.root_node):
        if node.type == "function_item":
            result = _parse_function(node, src)
            if result:
                fn, is_cmd = result
                if fn.is_public:
                    functions.append(fn)
                if is_cmd:
                    tauri_commands.append(fn.name)

        elif node.type == "struct_item":
            s = _parse_struct(node, src)
            if s and s.is_public:
                structs.append(s)

        elif node.type == "use_declaration":
            t = _text(node, src).strip()
            if t:
                imports.append(t)

    return functions, structs, imports, tauri_commands


# ─── directory parser ────────────────────────────────────────────────────────

def parse_rust_directory(dir_path: Path, project_root: Path) -> ModuleContext:
    """Parse toàn bộ .rs files trong một thư mục (không recursive)."""
    rel = str(dir_path.relative_to(project_root))
    ctx = ModuleContext(path=rel, language="rust")

    rs_files = sorted(dir_path.glob("*.rs"))
    for f in rs_files:
        ctx.source_files.append(str(f.relative_to(project_root)))
        fns, structs, imports, cmds = parse_rust_file(f)
        ctx.public_functions.extend(fns)
        ctx.structs.extend(structs)
        ctx.tauri_commands.extend(cmds)
        for imp in imports:
            if imp not in ctx.imports:
                ctx.imports.append(imp)

    return ctx
