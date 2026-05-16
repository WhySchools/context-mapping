#!/usr/bin/env python3
"""
context-gen: sinh context map cho dự án Tauri/WordPress từ AST.

Dùng:
    python cli.py build                    # scan toàn bộ project
    python cli.py build --path src-tauri   # chỉ scan một thư mục
    python cli.py watch                    # watch mode (cần watchdog)
    python cli.py load src-tauri/src/commands  # print context ra stdout để pipe vào LLM

File output: .context/<path_with_underscores>.md
Phần [auto] được regenerate mỗi lần chạy.
Phần [manual] KHÔNG BAO GIỜ bị xóa.

Thêm language mới: tạo parsers/<lang>_parser.py với register_plugin() ở cuối.
cli.py không cần sửa.
"""
from __future__ import annotations
import sys
from pathlib import Path
import click
from rich.console import Console
from rich.tree import Tree as RichTree

sys.path.insert(0, str(Path(__file__).parent))

# Import schema trước — REGISTRY cần tồn tại trước khi parsers register
from schema import REGISTRY, AUTO_START, AUTO_END
from merger import merge_context_file
from global_context import generate_global_context

# Import parsers để trigger register_plugin() của mỗi language.
# Thêm language mới: chỉ cần import ở đây.
import parsers.rust_parser   # noqa: F401
import parsers.ts_parser     # noqa: F401
import parsers.php_parser    # noqa: F401

console = Console()
stderr = Console(stderr=True)   # dùng cho noise trong load command


# ─── helpers ─────────────────────────────────────────────────────────────────

def _output_path(project_root: Path, dir_path: Path) -> Path:
    """Map src-tauri/src/commands → .context/src-tauri_src_commands.md"""
    rel = dir_path.relative_to(project_root)
    stem = str(rel).replace("/", "_").replace("\\", "_")
    return project_root / ".context" / f"{stem}.md"


def _process_directory(
    dir_path: Path,
    project_root: Path,
    quiet: bool = False,
) -> tuple[str, int, int]:
    """
    Detect language qua REGISTRY và parse một thư mục.
    Returns (output_path_str, fn_count, struct_count).

    Không cần sửa hàm này khi thêm language mới —
    chỉ cần register_plugin() trong parser tương ứng.
    """
    out_path = _output_path(project_root, dir_path)

    for plugin in REGISTRY.values():
        files = [
            f
            for ext in plugin.extensions
            for f in dir_path.glob(f"*{ext}")
        ]
        if not files:
            continue

        ctx = plugin.parse_dir(dir_path, project_root)
        merge_context_file(ctx, out_path)
        return (
            str(out_path.relative_to(project_root)),
            len(ctx.public_functions),
            len(ctx.structs),
        )

    return "", 0, 0


# ─── commands ────────────────────────────────────────────────────────────────

@click.group()
def cli():
    """context-gen: AST-based context map generator cho Tauri/WordPress projects."""
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
        # Gom tất cả dirs từ mọi plugin đã register
        seen: set[Path] = set()
        dirs: list[Path] = []
        for plugin in REGISTRY.values():
            for d in plugin.find_dirs(root):
                if d not in seen:
                    seen.add(d)
                    dirs.append(d)
        dirs.sort()

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
        out, fn_count, struct_count = _process_directory(d, root, quiet)
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

    generate_global_context(root, module_paths, quiet=quiet)

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
        python cli.py load wp-content/plugins/my-plugin/includes --include-manual
    """
    root = Path(project_root).resolve()
    target = Path(target_path).resolve()

    # Regenerate nhưng suppress console output — stdout phải sạch để pipe
    _process_directory(target, root, quiet=True)

    out_path = _output_path(root, target)
    if not out_path.exists():
        stderr.print(f"[red]Context file không tồn tại: {out_path}[/red]")
        sys.exit(1)

    content = out_path.read_text(encoding="utf-8")

    if not include_manual:
        if AUTO_START in content and AUTO_END in content:
            start = content.index(AUTO_START) + len(AUTO_START)
            end   = content.index(AUTO_END)
            content = content[start:end].strip()

    # Print raw — không có rich markup để pipe sạch
    print(content)


@cli.command()
@click.argument("project_root", default=".", type=click.Path(exists=True))
def watch(project_root: str):
    """
    Watch mode: tự động regenerate khi source files thay đổi.
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

    # Tất cả extensions đã register
    watched_exts = {
        ext
        for plugin in REGISTRY.values()
        for ext in plugin.extensions
    }

    all_skip = {
        s
        for plugin in REGISTRY.values()
        for s in plugin.skip_dirs
    }

    console.print(f"[cyan]Watching[/cyan] {root} ...")
    console.print(f"[dim]Extensions: {', '.join(sorted(watched_exts))}[/dim]")

    class Handler(FileSystemEventHandler):
        def on_modified(self, event):
            if event.is_directory:
                return
            p = Path(event.src_path)
            if p.suffix not in watched_exts:
                return
            if any(s in p.parts for s in all_skip):
                return
            console.print(f"[dim]changed:[/dim] {p.name}")
            try:
                _process_directory(p.parent, root, quiet=True)
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
