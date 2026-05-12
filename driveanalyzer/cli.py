import argparse
import sys
import warnings
from typing import Optional

warnings.filterwarnings("ignore", category=SyntaxWarning, module="wmi")

from rich.console import Console
from rich.markup import escape
from rich.table import Table
from rich import box
from rich.text import Text

from driveanalyzer import __version__
from driveanalyzer.adapters.os_adapter import DriveInfo
from driveanalyzer.core.analyzer import DriveAnalyzer
from driveanalyzer.core.smart import SMARTData
from driveanalyzer.core.speed_test import RANDOM_OPS, SpeedResult, SpeedTest

console = Console()


def fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024.0:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"


def usage_color(percent: float) -> str:
    if percent >= 90:
        return "red"
    if percent >= 80:
        return "yellow"
    return "green"


def cmd_list(analyzer: DriveAnalyzer) -> None:
    drives = analyzer.device_info.list_all()
    if not drives:
        console.print("[yellow]No drives found.[/yellow]")
        return

    table = Table(
        title=f"[bold]DriveAnalyzer[/bold] v{__version__} - Connected Drives",
        box=box.ROUNDED,
        show_lines=False,
        header_style="bold cyan",
    )
    table.add_column("Device", style="bold", no_wrap=True)
    table.add_column("Mount", no_wrap=True)
    table.add_column("FS", no_wrap=True)
    table.add_column("Total", justify="right")
    table.add_column("Used", justify="right")
    table.add_column("Free", justify="right")
    table.add_column("Use%", justify="right")
    table.add_column("Model", min_width=16)
    table.add_column("Interface", no_wrap=True)

    for d in drives:
        pct = d.usage_percent
        color = usage_color(pct)
        table.add_row(
            d.device,
            d.mountpoint,
            d.fstype or "-",
            fmt_bytes(d.total),
            fmt_bytes(d.used),
            fmt_bytes(d.free),
            Text(f"{pct:.1f}%", style=color),
            d.model,
            d.interface,
        )

    console.print(table)


def cmd_info(path: str, analyzer: DriveAnalyzer) -> None:
    drive = analyzer.device_info.get_info(path)
    if drive is None:
        console.print(f"[red]No drive found for path:[/red] {path}")
        sys.exit(1)

    _print_drive_panel(drive)


def _print_drive_panel(d: DriveInfo) -> None:
    pct = d.usage_percent
    color = usage_color(pct)

    table = Table(
        title=f"[bold]Drive Info - {escape(d.mountpoint)}[/bold]",
        box=box.ROUNDED,
        show_header=False,
        padding=(0, 1),
    )
    table.add_column("Field", style="bold cyan", no_wrap=True)
    table.add_column("Value")

    table.add_row("Device", d.device)
    table.add_row("Mountpoint", d.mountpoint)
    table.add_row("Filesystem", d.fstype or "-")
    table.add_row("Total", fmt_bytes(d.total))
    table.add_row("Used", Text(f"{fmt_bytes(d.used)} ({pct:.1f}%)", style=color))
    table.add_row("Free", fmt_bytes(d.free))
    table.add_row("Model", d.model)
    table.add_row("Serial", d.serial)
    table.add_row("Interface", d.interface)

    console.print(table)


def _speed_color(mbps: float, write: bool = False) -> str:
    thresholds = (30, 100) if write else (50, 150)
    if mbps >= thresholds[1]:
        return "green"
    if mbps >= thresholds[0]:
        return "yellow"
    return "red"


def _fmt_speed(mbps: Optional[float], write: bool = False) -> Text:
    if mbps is None:
        return Text("N/A", style="dim")
    color = _speed_color(mbps, write=write)
    return Text(f"{mbps:.1f} MB/s", style=color)


def cmd_speed(path: str, size_mb: int, analyzer: DriveAnalyzer) -> None:
    drive = analyzer.device_info.get_info(path)
    if drive is None:
        console.print(f"[red]No drive found for path:[/red] {path}")
        sys.exit(1)

    console.print(
        f"[bold]Speed Test[/bold] - {escape(drive.mountpoint)}  "
        f"[dim]{drive.model} / {drive.interface}[/dim]"
    )
    console.print(f"[dim]File size: {size_mb} MB  |  Block: 1 MB  |  Random ops: {RANDOM_OPS} x 4 KB[/dim]")

    test = SpeedTest(mountpoint=drive.mountpoint, size_mb=size_mb)
    try:
        result = test.run(console)
    except PermissionError:
        console.print("[red]Permission denied.[/red] Try running as administrator.")
        sys.exit(1)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Test interrupted.[/yellow]")
        sys.exit(130)

    _print_speed_result(result, drive.mountpoint)


def _print_speed_result(result: SpeedResult, mountpoint: str) -> None:
    table = Table(
        title=f"[bold]Speed Test Results - {escape(mountpoint)}[/bold]",
        box=box.ROUNDED,
        header_style="bold cyan",
        min_width=48,
    )
    table.add_column("Test", style="bold", min_width=32)
    table.add_column("Result", justify="right", min_width=12)

    table.add_row(
        f"Sequential Write  ({result.file_size_mb} MB)",
        _fmt_speed(result.write_seq_mbps, write=True),
    )
    table.add_row(
        f"Sequential Read   ({result.file_size_mb} MB)",
        _fmt_speed(result.read_seq_mbps),
    )
    table.add_row(
        f"Random Read       ({RANDOM_OPS} ops x 4 KB)",
        _fmt_speed(result.read_random_mbps),
    )

    console.print(table)
    if result.read_seq_mbps is not None and result.read_seq_mbps > 800:
        console.print(
            "[dim]Note: sequential read may be inflated by OS page cache. "
            "Use a larger --size (e.g. > RAM) for accurate disk read speed.[/dim]"
        )


def cmd_health(path: str, analyzer: DriveAnalyzer) -> None:
    drive = analyzer.device_info.get_info(path)
    if drive is None:
        console.print(f"[red]No drive found for path:[/red] {path}")
        sys.exit(1)

    console.print(
        f"[bold]Health Check[/bold] - {escape(drive.mountpoint)}  "
        f"[dim]{drive.model} / {drive.interface}[/dim]"
    )

    hc = analyzer.health_check(drive.mountpoint)
    smart = hc.run_smart()
    _print_smart_result(smart)


def _status_style(status: str) -> str:
    return {"PASSED": "bold green", "FAILED": "bold red"}.get(status, "bold yellow")


def _val_or_dash(v: Optional[int]) -> Text:
    if v is None:
        return Text("-", style="dim")
    return Text(str(v))


def _sector_text(v: Optional[int]) -> Text:
    if v is None:
        return Text("-", style="dim")
    if v > 0:
        return Text(str(v), style="red bold")
    return Text("0", style="green")


def _temp_text(v: Optional[int]) -> Text:
    if v is None:
        return Text("-", style="dim")
    if v >= 60:
        return Text(f"{v} C", style="red")
    if v >= 50:
        return Text(f"{v} C", style="yellow")
    return Text(f"{v} C", style="green")


def _print_smart_result(smart: SMARTData) -> None:
    status_style = _status_style(smart.status)

    table = Table(
        title=f"[bold]SMART Health - {escape(smart.device)}[/bold]",
        box=box.ROUNDED,
        show_header=False,
        padding=(0, 1),
        min_width=48,
    )
    table.add_column("Field", style="bold cyan", no_wrap=True, min_width=24)
    table.add_column("Value", min_width=20)

    table.add_row("Overall Status", Text(smart.status, style=status_style))
    table.add_row("Model", smart.model)
    table.add_row("Serial", smart.serial)
    table.add_row("Firmware", smart.firmware)
    table.add_row("Temperature", _temp_text(smart.temperature_c))
    table.add_row("Power-On Hours", _val_or_dash(smart.power_on_hours))
    table.add_row("Reallocated Sectors", _sector_text(smart.reallocated_sectors))
    table.add_row("Pending Sectors", _sector_text(smart.pending_sectors))
    table.add_row("Uncorrectable Errors", _sector_text(smart.uncorrectable_errors))

    console.print(table)

    if smart.warnings:
        console.print()
        for w in smart.warnings:
            icon = "[red]![/red]" if "FAILED" in w or "!" in w else "[yellow]~[/yellow]"
            console.print(f"  {icon} {w}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="driveanalyzer",
        description="DriveAnalyzer - USB/disk diagnostic tool",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    sub.add_parser("list", help="List all available drives")

    info_p = sub.add_parser("info", help="Show device metadata for a path")
    info_p.add_argument("path", help="Path on the target drive (e.g. C:\\ or /mnt/usb)")

    speed_p = sub.add_parser("speed", help="Run sequential and random speed tests")
    speed_p.add_argument("path", help="Path on the target drive")
    speed_p.add_argument(
        "--size",
        metavar="MB",
        type=int,
        default=512,
        help="Test file size in MB (default: 512)",
    )

    health_p = sub.add_parser("health", help="Run SMART health diagnostics")
    health_p.add_argument("path", help="Path on the target drive")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    analyzer = DriveAnalyzer()

    if args.command == "list":
        cmd_list(analyzer)
    elif args.command == "info":
        cmd_info(args.path, analyzer)
    elif args.command == "speed":
        cmd_speed(args.path, args.size, analyzer)
    elif args.command == "health":
        cmd_health(args.path, analyzer)
