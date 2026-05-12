import os
import random
import time
import uuid
from dataclasses import dataclass
from typing import Optional

import psutil
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

BLOCK_SIZE = 1024 * 1024  # 1 MB
RANDOM_OPS = 512
RANDOM_READ_SIZE = 4096   # 4 KB per seek+read


@dataclass
class SpeedResult:
    write_seq_mbps: Optional[float]
    read_seq_mbps: Optional[float]
    read_random_mbps: Optional[float]
    file_size_mb: int


def _progress_bytes(description: str, total: int, console: Console) -> Progress:
    return Progress(
        TextColumn(f"[bold cyan]{description:<18}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=True,
    )


def _progress_ops(description: str, console: Console) -> Progress:
    return Progress(
        TextColumn(f"[bold cyan]{description:<18}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=True,
    )


class SpeedTest:
    def __init__(self, mountpoint: str, size_mb: int = 512) -> None:
        self.mountpoint = mountpoint
        self.size_mb = size_mb

    def _tmp_path(self) -> str:
        name = f"driveanalyzer_{uuid.uuid4().hex[:8]}.tmp"
        return os.path.join(self.mountpoint, name)

    def _check_space(self) -> None:
        usage = psutil.disk_usage(self.mountpoint)
        needed = self.size_mb * 1024 * 1024
        if usage.free < needed:
            free_mb = usage.free / 1024 / 1024
            raise ValueError(
                f"Not enough free space: need {self.size_mb} MB, "
                f"only {free_mb:.0f} MB available"
            )

    def run(self, console: Console) -> SpeedResult:
        self._check_space()
        tmpfile = self._tmp_path()

        write_mbps: Optional[float] = None
        read_mbps: Optional[float] = None
        random_mbps: Optional[float] = None

        try:
            write_mbps = self._write_test(tmpfile, console)
            read_mbps = self._read_test(tmpfile, console)
            random_mbps = self._random_test(tmpfile, console)
        finally:
            try:
                os.unlink(tmpfile)
            except OSError:
                pass

        return SpeedResult(
            write_seq_mbps=write_mbps,
            read_seq_mbps=read_mbps,
            read_random_mbps=random_mbps,
            file_size_mb=self.size_mb,
        )

    def _write_test(self, path: str, console: Console) -> float:
        total_bytes = self.size_mb * BLOCK_SIZE
        # Reuse one random block to avoid OS zero-page shortcuts
        block = os.urandom(BLOCK_SIZE)

        with _progress_bytes("Sequential Write", total_bytes, console) as progress:
            task = progress.add_task("", total=total_bytes)
            start = time.monotonic()
            with open(path, "wb") as f:
                for _ in range(self.size_mb):
                    f.write(block)
                    progress.advance(task, BLOCK_SIZE)
                f.flush()
                os.fsync(f.fileno())
            elapsed = time.monotonic() - start

        return self.size_mb / elapsed

    def _read_test(self, path: str, console: Console) -> float:
        total_bytes = self.size_mb * BLOCK_SIZE

        with _progress_bytes("Sequential Read", total_bytes, console) as progress:
            task = progress.add_task("", total=total_bytes)
            start = time.monotonic()
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(BLOCK_SIZE)
                    if not chunk:
                        break
                    progress.advance(task, len(chunk))
            elapsed = time.monotonic() - start

        return self.size_mb / elapsed

    def _random_test(self, path: str, console: Console) -> float:
        max_pos = self.size_mb * BLOCK_SIZE - RANDOM_READ_SIZE

        with _progress_ops("Random Read", console) as progress:
            task = progress.add_task("", total=RANDOM_OPS)
            start = time.monotonic()
            with open(path, "rb") as f:
                for _ in range(RANDOM_OPS):
                    f.seek(random.randint(0, max_pos))
                    f.read(RANDOM_READ_SIZE)
                    progress.advance(task, 1)
            elapsed = time.monotonic() - start

        total_mb = RANDOM_OPS * RANDOM_READ_SIZE / 1024 / 1024
        return total_mb / elapsed
