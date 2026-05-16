"""
Schema: các dataclass mô tả cấu trúc context map.
Phần [auto] do tool generate, phần [manual] do con người viết.
Tool KHÔNG BAO GIỜ overwrite vùng [manual].
"""
from dataclasses import dataclass, field
from typing import Optional
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

    def signature(self) -> str:
        prefix = ""
        if self.is_public:
            prefix += "pub "
        if self.is_async:
            prefix += "async "
        params = ", ".join(self.params)
        ret = f" -> {self.return_type}" if self.return_type else ""
        return f"{prefix}fn {self.name}({params}){ret}"


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
    language: str                      # "rust" | "typescript"
    public_functions: list[FunctionInfo] = field(default_factory=list)
    structs: list[StructInfo] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    tauri_commands: list[str] = field(default_factory=list)  # fn có #[tauri::command]
    source_files: list[str] = field(default_factory=list)


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
