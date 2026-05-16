#!/usr/bin/env python3
"""
context-gen: sinh context map cho dự án Tauri từ AST.

Dùng:
    python cli.py build                    # scan toàn bộ project
    python cli.py build --path src-tauri   # chỉ scan một thư mục
    python cli.py watch                    # watch mode (cần watchdog)
    python cli.py load src-tauri/src/commands  # print context ra stdout để pipe vào LLM

File output: .context/<path_with_underscores>.md
Phần [auto] được regenerate mỗi lần chạy.
Phần [manual] KHÔNG BAO GIỜ bị xóa.
"""
from __future__ import annotations
import sys
from pathlib import Path
import click
from rich.console import Console
from rich.tree import Tree as RichTree

# Thêm project root vào sys.path
sys.path.insert(0, str(Path(__file__).parent))

from parsers.rust_parser import parse_rust_directory
from parsers.ts_parser import parse_ts_directory
from merger import merge_context_file
from global_context import generate_global_context
from schema import AUTO_START, AUTO_END

console = Console()

# ─── helpers ─────────────────────────────────────────────────────────────────

def _find_rust_dirs(root: Path) -> list[Path]:
    """Tìm các thư mục chứa .rs files (không đệ quy vào target/)."""
    dirs: list[Path] = []
    for rs in root.rglob("*.rs"):
        if "target" in rs.parts or ".git" in rs.parts:
            continue
        if rs.parent not in dirs:
            dirs.append(rs.parent)
    return sorted(dirs)


def _find_ts_dirs(root: Path) -> list[Path]:
    """Tìm các thư mục chứa .ts/.tsx files (bỏ qua node_modules, dist)."""
    dirs: list[Path] = []
    skip = {"node_modules", "dist", ".git", "target", ".vite"}
    for ts in list(root.rglob("*.ts")) + list(root.rglob("*.tsx")):
        if any(p in ts.parts for p in skip):
            continue
        if ts.parent not in dirs:
            dirs.append(ts.parent)
    return sorted(dirs)


def _output_path(project_root: Path, dir_path: Path) -> Path:
    """Map src-tauri/src/commands → .context/src-tauri_src_commands.md"""
    rel = dir_path.relative_to(project_root)
    stem = str(rel).replace("/", "_").replace("\\", "_")
    return project_root / ".context" / f"{stem}.md"


def _process_directory(dir_path: Path, project_root: Path) -> tuple[str, int, int]:
    """
    Auto-detect language và parse một thư mục.
    Returns (output_path_str, fn_count, struct_count).
    """
    rs_files = list(dir_path.glob("*.rs"))
    ts_files = list(dir_path.glob("*.ts")) + list(dir_path.glob("*.tsx"))

    out_path = _output_path(project_root, dir_path)

    if rs_files:
        ctx = parse_rust_directory(dir_path, project_root)
        merge_context_file(ctx, out_path)
        return str(out_path.relative_to(project_root)), len(ctx.public_functions), len(ctx.structs)

    elif ts_files:
        ctx = parse_ts_directory(dir_path, project_root)
        merge_context_file(ctx, out_path)
        return str(out_path.relative_to(project_root)), len(ctx.public_functions), len(ctx.structs)

    return "", 0, 0


# ─── commands ────────────────────────────────────────────────────────────────

@click.group()
def cli():
    """context-gen: AST-based context map generator cho Tauri projects."""
    pass


@cli.command()
@click.argument("project_root", default=".", type=click.Path(exists=True))
@click.option("--path", "-p", default=None,
              help="Chỉ scan một subdirectory cụ thể")
@click.option("--quiet", "-q", is_flag=True, help="Chỉ print errors")
def build(project_root: str, path: str | None, quiet: bool):
    """Scan project và sinh/cập nhật toàn bộ .context/*.md files."""
    root = Path(project_root).resolve()

    if path:
        target = root / path
        if not target.exists():
            console.print(f"[red]Không tìm thấy: {target}[/red]")
            sys.exit(1)
        dirs = [target]
    else:
        rs_dirs = _find_rust_dirs(root)
        ts_dirs = _find_ts_dirs(root)
        # Merge, dedupe
        all_dirs = list({d for d in rs_dirs + ts_dirs})
        dirs = sorted(all_dirs)

    if not dirs:
        console.print("[yellow]Không tìm thấy source files.[/yellow]")
        sys.exit(0)

    if not quiet:
        console.print(f"\n[bold cyan]context-gen[/bold cyan] → [dim]{root}[/dim]\n")

    module_paths: list[str] = []
    total_fns = 0
    total_types = 0

    tree = RichTree(f"[bold].context/[/bold]")

    for d in dirs:
        out, fn_count, struct_count = _process_directory(d, root)
        if not out:
            continue
        rel = str(d.relative_to(root))
        module_paths.append(rel)
        total_fns += fn_count
        total_types += struct_count
        if not quiet:
            tree.add(
                f"[green]{out}[/green]  "
                f"[dim]{fn_count} fn, {struct_count} types[/dim]"
            )

    # Global context
    generate_global_context(root, module_paths)

    if not quiet:
        console.print(tree)
        console.print(
            f"\n[bold green]✓[/bold green] "
            f"{len(module_paths)} modules, "
            f"{total_fns} functions, "
            f"{total_types} types indexed\n"
        )


@cli.command()
@click.argument("target_path", type=click.Path(exists=True))
@click.argument("project_root", default=".", type=click.Path(exists=True))
@click.option("--include-manual", "-m", is_flag=True,
              help="Include phần [manual] vào output (mặc định chỉ auto)")
def load(target_path: str, project_root: str, include_manual: bool):
    """
    Print context của một module ra stdout.
    Dùng để pipe vào clipboard hoặc LLM prompt.

    Ví dụ:
        python cli.py load src-tauri/src/commands | pbcopy
        python cli.py load src-tauri/src/commands --include-manual
    """
    root = Path(project_root).resolve()
    target = Path(target_path).resolve()

    # First regenerate
    _process_directory(target, root)

    out_path = _output_path(root, target)
    if not out_path.exists():
        console.print(f"[red]Context file không tồn tại: {out_path}[/red]")
        sys.exit(1)

    content = out_path.read_text(encoding="utf-8")

    if not include_manual:
        # Extract only auto section
        if AUTO_START in content and AUTO_END in content:
            start = content.index(AUTO_START) + len(AUTO_START)
            end   = content.index(AUTO_END)
            content = content[start:end].strip()

    # Print raw (no rich markup) for piping
    print(content)


@cli.command()
@click.argument("project_root", default=".", type=click.Path(exists=True))
def watch(project_root: str):
    """
    Watch mode: tự động regenerate khi .rs/.ts files thay đổi.
    Cần: pip install watchdog
    """
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
        import time
    except ImportError:
        console.print("[red]watchdog chưa install:[/red] pip install watchdog")
        sys.exit(1)

    root = Path(project_root).resolve()
    console.print(f"[cyan]Watching[/cyan] {root} ...")

    class Handler(FileSystemEventHandler):
        def on_modified(self, event):
            if event.is_directory:
                return
            p = Path(event.src_path)
            if p.suffix not in (".rs", ".ts", ".tsx"):
                return
            skip = {"target", "node_modules", "dist", ".git"}
            if any(s in p.parts for s in skip):
                return
            console.print(f"[dim]changed:[/dim] {p.name}")
            try:
                _process_directory(p.parent, root)
                console.print(f"[green]✓[/green] {p.parent.relative_to(root)}")
            except Exception as e:
                console.print(f"[red]Error:[/red] {e}")

    observer = Observer()
    observer.schedule(Handler(), str(root), recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    cli()
