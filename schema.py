"""
Schema: các dataclass mô tả cấu trúc context map.
Phần [auto] do tool generate, phần [manual] do con người viết.
Tool KHÔNG BAO GIỜ overwrite vùng [manual].
"""
from dataclasses import dataclass, field
from typing import Optional, Callable
from pathlib import Path


@dataclass
class FunctionInfo:
    name: str
    is_public: bool
    is_async: bool
    params: list[str]          # ["name: String", "state: State<DbPool>"]
    return_type: Optional[str]
    doc_comment: Optional[str]
    line: int

    def signature(self, language: str = "rust") -> str:
        """Sinh function signature đúng syntax theo language."""
        if language == "rust":
            prefix = ""
            if self.is_public:
                prefix += "pub "
            if self.is_async:
                prefix += "async "
            params = ", ".join(self.params)
            ret = f" -> {self.return_type}" if self.return_type else ""
            return f"{prefix}fn {self.name}({params}){ret}"

        elif language == "typescript":
            prefix = "export "
            if self.is_async:
                prefix += "async "
            params = ", ".join(self.params)
            ret = f": {self.return_type}" if self.return_type else ""
            return f"{prefix}function {self.name}({params}){ret}"

        elif language == "php":
            params = ", ".join(self.params)
            ret = f": {self.return_type}" if self.return_type else ""
            vis = "public " if self.is_public else ""
            return f"{vis}function {self.name}({params}){ret}"

        else:
            params = ", ".join(self.params)
            ret = f" -> {self.return_type}" if self.return_type else ""
            return f"function {self.name}({params}){ret}"


@dataclass
class StructInfo:
    name: str
    is_public: bool
    fields: list[str]
    doc_comment: Optional[str]
    derives: list[str]         # ["Serialize", "Deserialize", "Debug"]


@dataclass
class ModuleContext:
    """Context của một thư mục/module."""
    path: str                          # relative path từ project root
    language: str                      # "rust" | "typescript" | "php"
    public_functions: list[FunctionInfo] = field(default_factory=list)
    structs: list[StructInfo] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    tauri_commands: list[str] = field(default_factory=list)  # IPC hooks: tauri::command, add_action, add_filter
    source_files: list[str] = field(default_factory=list)


@dataclass
class ParserPlugin:
    """
    Plugin descriptor cho một ngôn ngữ.
    Thêm language mới = tạo ParserPlugin + register vào REGISTRY.
    Không cần sửa cli.py hay merger.py.
    """
    language: str                      # "rust" | "typescript" | "php"
    extensions: list[str]             # [".php"] hoặc [".ts", ".tsx"]
    find_dirs: Callable                # fn(root: Path) -> list[Path]
    parse_dir: Callable                # fn(dir: Path, root: Path) -> ModuleContext
    skip_dirs: set[str] = field(default_factory=set)
    ipc_label: str = "IPC / Hook Bridge"  # label thay cho "Tauri Commands"


# Registry toàn cục — populated bởi từng parser module khi import
REGISTRY: dict[str, "ParserPlugin"] = {}


def register_plugin(plugin: ParserPlugin) -> None:
    """Đăng ký một parser plugin vào registry."""
    REGISTRY[plugin.language] = plugin


# Markers dùng để tách vùng auto vs manual trong file .context.md
AUTO_START = "<!-- AUTO_START -->"
AUTO_END   = "<!-- AUTO_END -->"
MANUAL_SECTION = """<!-- MANUAL_START -->
## [manual] Design Decisions
> Tại sao module này được thiết kế như vậy? Trade-off gì đã được chọn?

_Chưa có ghi chú._

## [manual] Invariants & Constraints
> Các quy tắc KHÔNG BAO GIỜ được vi phạm khi sửa code ở đây.

_Chưa có ghi chú._

## [manual] Test Strategy
> Cách test module này: unit/integration, mock gì, test case quan trọng nhất là gì?

_Chưa có ghi chú._

## [manual] Behavior chưa implement (TODO)
> Các behavior đã thiết kế nhưng chưa code. LLM đọc để không "sáng tác" sai hướng.

_Chưa có ghi chú._
<!-- MANUAL_END -->"""
