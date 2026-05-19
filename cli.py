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

V3: staleness detection — detect khi [auto] thay đổi mà [manual] chưa review.

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

from schema import REGISTRY, AUTO_START, AUTO_END
from merger import merge_context_file, _render_auto
from global_context import generate_global_context
from staleness import check_file, StalenessResult, StalenessReport
from tensions_writer import write_staleness_tensions, write_single_staleness

import parsers.rust_parser   # noqa: F401
import parsers.ts_parser     # noqa: F401
import parsers.php_parser    # noqa: F401

console = Console()
stderr = Console(stderr=True)


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


def _process_directory_with_staleness(
    dir_path: Path,
    project_root: Path,
    quiet: bool = False,
) -> tuple[str, int, int, StalenessResult | None]:
    """
    Như _process_directory nhưng check staleness TRƯỚC khi write.

    Staleness check cần chạy TRƯỚC merge_context_file vì sau khi merge
    thì hash trong file đã được update thành hash mới rồi.

    Returns (output_path_str, fn_count, struct_count, staleness_result | None)
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

        # Render [auto] content để tính hash mới — TRƯỚC khi write
        new_auto_content = _render_auto(ctx)
        stale_result = check_file(out_path, new_auto_content)

        # Merge và write (bao gồm inject hash mới vào marker)
        merge_context_file(ctx, out_path)

        return (
            str(out_path.relative_to(project_root)),
            len(ctx.public_functions),
            len(ctx.structs),
            stale_result,
        )

    return "", 0, 0, None


def _print_staleness_summary(stale_results: list[StalenessResult]) -> None:
    """In staleness warning ra stderr sau build."""
    if not stale_results:
        return
    console.print(
        f"\n[yellow]⚠  {len(stale_results)} module(s) có [auto] thay đổi "
        f"— [manual] cần review:[/yellow]"
    )
    for r in stale_results:
        console.print(
            f"   [yellow]{r.module_name}[/yellow]  "
            f"[dim]{r.old_hash} → {r.new_hash}[/dim]"
        )
    console.print("   [dim]→ Chi tiết trong .context/TENSIONS.md[/dim]\n")


# ─── V3 helpers ──────────────────────────────────────────────────────────────

def _warn_old_tensions_format(root: Path) -> None:
    """
    Warn ra stderr nếu project dùng TENSIONS.md format cũ mà chưa migrate.
    Chỉ warn — không tự migrate.
    """
    old_file = root / ".context" / "TENSIONS.md"
    new_file = root / ".context" / "TENSIONS_OPEN.md"
    if old_file.exists() and not new_file.exists():
        stderr.print(
            "\n[yellow]⚠  TENSIONS.md format cũ detected.[/yellow]\n"
            "   Chạy [bold]context-gen migrate-tensions .[/bold] "
            "để migrate sang V3 format.\n"
            "   Không tự migrate — cần human review trước.\n"
        )


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
    """
    Scan project và sinh/cập nhật toàn bộ .context/*.md files.
    Sau khi build, kiểm tra staleness và ghi TENSIONS.md nếu [auto] thay đổi.
    """
    root = Path(project_root).resolve()
    context_dir = root / ".context"

    # V3: warn nếu dùng format cũ
    _warn_old_tensions_format(root)

    # V3: đọc current milestone một lần cho toàn bộ build
    from tensions_writer import _read_current_milestone
    current_milestone = _read_current_milestone(context_dir)

    if path:
        target = root / path
        if not target.exists():
            console.print(f"[red]Không tìm thấy: {target}[/red]")
            sys.exit(1)
        dirs = [target]
    else:
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
    stale_results: list[StalenessResult] = []
    tree = RichTree(f"[bold].context/[/bold]")

    for d in dirs:
        out, fn_count, struct_count, stale = _process_directory_with_staleness(d, root, quiet)
        if not out:
            continue
        rel = str(d.relative_to(root))
        module_paths.append(rel)
        total_fns += fn_count
        total_types += struct_count

        if stale and stale.is_stale:
            stale_results.append(stale)

        if not quiet:
            stale_tag = " [yellow]⚠ stale[/yellow]" if (stale and stale.is_stale) else ""
            tree.add(
                f"[green]{out}[/green]  "
                f"[dim]{fn_count} fn, {struct_count} types[/dim]"
                f"{stale_tag}"
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

    # Ghi TENSIONS.md nếu có stale — sau khi print tree để order hợp lý
    if stale_results:
        report = StalenessReport(stale=stale_results)
        written = write_staleness_tensions(context_dir, report, milestone=current_milestone)
        _print_staleness_summary(written)
    elif not quiet:
        console.print("[dim]✓ [manual] sections up to date[/dim]\n")


@cli.command()
@click.argument("target_path", type=click.Path(exists=True))
@click.argument("project_root", default=".", type=click.Path(exists=True))
@click.option("--include-manual", "-m", is_flag=True,
              help="Include phần [manual] vào output (mặc định chỉ auto)")
def load(target_path: str, project_root: str, include_manual: bool):
    """
    Print context của một module ra stdout.
    Warn ra stderr nếu [manual] có thể stale (không block output).

    Dùng để pipe vào clipboard hoặc LLM prompt:
        python cli.py load src-tauri/src/commands | pbcopy
        python cli.py load wp-content/plugins/my-plugin/includes --include-manual
    """
    root = Path(project_root).resolve()
    target = Path(target_path).resolve()
    context_dir = root / ".context"
    out_path = _output_path(root, target)

    # Regenerate + staleness check — suppress console output, stdout phải sạch
    out, _, _, stale = _process_directory_with_staleness(target, root, quiet=True)

    if not out_path.exists():
        stderr.print(f"[red]Context file không tồn tại: {out_path}[/red]")
        sys.exit(1)

    # Warn staleness ra stderr — không block stdout
    if stale and stale.is_stale:
        stderr.print(
            f"[yellow]⚠  STALENESS WARNING[/yellow]  {stale.module_name}\n"
            f"   [auto] thay đổi kể từ lần build trước "
            f"({stale.old_hash} → {stale.new_hash})\n"
            f"   [manual] có thể outdated. Kiểm tra .context/TENSIONS_OPEN.md."
        )
        from tensions_writer import _read_current_milestone
        current_milestone = _read_current_milestone(context_dir)
        write_single_staleness(context_dir, stale, milestone=current_milestone)

    # Output ra stdout — chỉ content, không có rich markup
    content = out_path.read_text(encoding="utf-8")

    if not include_manual:
        if AUTO_START in content and AUTO_END in content:
            # Tìm AUTO_START (có thể có hash trong marker)
            import re
            auto_start_pattern = re.compile(r"<!--\s*AUTO_START[^>]*-->", re.IGNORECASE)
            start_m = auto_start_pattern.search(content)
            end_idx = content.find(AUTO_END)
            if start_m and end_idx != -1:
                content = content[start_m.end():end_idx].strip()

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
    context_dir = root / ".context"

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
                _, _, _, stale = _process_directory_with_staleness(p.parent, root, quiet=True)
                label = str(p.parent.relative_to(root))
                if stale and stale.is_stale:
                    console.print(f"[green]✓[/green] {label}  [yellow]⚠ stale → TENSIONS.md[/yellow]")
                    write_single_staleness(context_dir, stale)
                else:
                    console.print(f"[green]✓[/green] {label}")
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


@cli.command("check-consistency")
@click.argument("project_root", default=".", type=click.Path(exists=True))
def check_consistency(project_root: str):
    """
    Verify context files are internally consistent.
    Exit code 1 nếu có errors, 0 nếu chỉ có warnings hoặc clean.
    """
    from consistency import run_consistency_checks
    root = Path(project_root).resolve()
    errors, warnings = run_consistency_checks(root)

    for e in errors:
        stderr.print(f"[red]ERROR[/red]  {e}\n")
    for w in warnings:
        stderr.print(f"[yellow]WARN[/yellow]   {w}\n")
    if not errors and not warnings:
        console.print("[green]OK[/green]  Context files consistent.")

    raise SystemExit(1 if errors else 0)


@cli.command("migrate-tensions")
@click.argument("project_root", default=".", type=click.Path(exists=True))
def migrate_tensions(project_root: str):
    """
    Preview migration từ TENSIONS.md sang 3 file V3.
    Hỏi confirm trước khi tạo file. Không xóa TENSIONS.md cũ.
    """
    from consistency import parse_tension_entries, format_tensions_file

    root = Path(project_root).resolve()
    context_dir = root / ".context"
    old_file = context_dir / "TENSIONS.md"

    if not old_file.exists():
        console.print("[green]Không tìm thấy TENSIONS.md — không cần migrate.[/green]")
        return

    open_file    = context_dir / "TENSIONS_OPEN.md"
    active_file  = context_dir / "TENSIONS_ACTIVE.md"
    history_file = context_dir / "TENSIONS_HISTORY.md"

    if open_file.exists() or active_file.exists():
        console.print(
            "[yellow]TENSIONS_OPEN.md hoặc TENSIONS_ACTIVE.md đã tồn tại.[/yellow]\n"
            "Migration có thể đã được thực hiện. Kiểm tra trước khi chạy lại."
        )
        return

    entries = parse_tension_entries(old_file)
    open_entries    = [e for e in entries if e["status"] == "OPEN"]
    active_entries  = [e for e in entries if e["status"] == "RESOLVED_ACTIVE"]
    history_entries = [e for e in entries if e["status"] == "ARCHIVED"]

    # Preview
    console.print("\n[bold]Migration preview:[/bold]")
    console.print(f"\n  [cyan]TENSIONS_OPEN.md[/cyan]     ← {len(open_entries)} entries")
    for e in open_entries:
        console.print(f"    [dim]- {e['title']}[/dim]")
    console.print(f"\n  [cyan]TENSIONS_ACTIVE.md[/cyan]   ← {len(active_entries)} entries")
    for e in active_entries:
        console.print(f"    [dim]- {e['title']}[/dim]")
    console.print(f"\n  [cyan]TENSIONS_HISTORY.md[/cyan]  ← {len(history_entries)} entries")
    for e in history_entries:
        console.print(f"    [dim]- {e['title']}[/dim]")

    console.print(
        "\n[dim]TENSIONS.md cũ sẽ KHÔNG bị xóa.[/dim]\n"
        "[dim]Xóa thủ công sau khi verify 3 file mới đúng.[/dim]\n"
    )

    click.confirm("Tiếp tục tạo 3 file mới?", abort=True)

    _OPEN_HEADER = (
        "# Tensions — OPEN\n\n"
        "> Chỉ chứa Status: OPEN entries.\n"
        "> Agent luôn đọc toàn bộ file này trước mỗi task.\n"
        "> Khi human resolve → move sang TENSIONS_ACTIVE.md, đổi Status: RESOLVED_ACTIVE.\n\n"
        "---\n\n"
    )
    _ACTIVE_HEADER = (
        "# Tensions — Active\n\n"
        "> Chỉ chứa Status: RESOLVED_ACTIVE entries của milestone hiện tại.\n"
        "> Agent đọc file này với tag filter (xem AGENTS.md Section 3.1).\n"
        "> Move sang TENSIONS_HISTORY.md chỉ khi human approve milestone transition.\n\n"
        "---\n\n"
    )
    _HISTORY_HEADER = (
        "# Tensions — History\n\n"
        "> Chỉ chứa Status: ARCHIVED entries.\n"
        "> KHÔNG load mặc định — chỉ đọc khi human yêu cầu audit.\n"
        "> Chỉ move entries vào đây khi human approve milestone transition.\n\n"
        "---\n\n"
    )

    open_file.write_text(
        format_tensions_file(_OPEN_HEADER, open_entries), encoding="utf-8"
    )
    active_file.write_text(
        format_tensions_file(_ACTIVE_HEADER, active_entries), encoding="utf-8"
    )
    history_file.write_text(
        format_tensions_file(_HISTORY_HEADER, history_entries), encoding="utf-8"
    )

    console.print("\n[green]✓[/green] 3 file đã được tạo:")
    console.print(f"   {open_file.relative_to(root)}")
    console.print(f"   {active_file.relative_to(root)}")
    console.print(f"   {history_file.relative_to(root)}")
    console.print(
        "\n[dim]Kiểm tra nội dung 3 file, sau đó xóa TENSIONS.md cũ nếu đúng.[/dim]\n"
    )


if __name__ == "__main__":
    cli()
