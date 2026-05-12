import os
import subprocess
import sys
from typing import Optional

import psutil

from driveanalyzer.adapters.os_adapter import DriveInfo, OSAdapter

_SKIP_FSTYPES = frozenset({
    "squashfs", "tmpfs", "devtmpfs", "devpts", "sysfs", "proc",
    "cgroup", "cgroup2", "pstore", "bpf", "tracefs", "debugfs",
    "hugetlbfs", "mqueue", "fusectl", "overlay",
})


class LinuxAdapter(OSAdapter):

    def _run(self, cmd: list[str], timeout: int = 5) -> str:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return r.stdout.strip()
        except Exception:
            return ""

    def _block_device_for_mount(self, mountpoint: str) -> Optional[str]:
        out = self._run(["lsblk", "-no", "PKNAME", mountpoint])
        return out.splitlines()[0].strip() if out else None

    def _read_sys(self, dev: str, attr: str) -> str:
        try:
            with open(f"/sys/block/{dev}/device/{attr}") as f:
                return f.read().strip()
        except OSError:
            return "Unknown"

    def _get_interface(self, dev: str) -> str:
        out = self._run(["lsblk", "-no", "TRAN", f"/dev/{dev}"])
        tran = out.splitlines()[0].strip().upper() if out else ""
        if tran == "USB":
            return "USB"
        if tran == "NVME":
            return "NVMe"
        if tran in ("SATA", "ATA"):
            return "SATA"
        if tran:
            return tran.title()
        # Fallback: inspect sysfs symlink
        try:
            link = os.readlink(f"/sys/block/{dev}")
            link_lower = link.lower()
            if "usb" in link_lower:
                return "USB"
            if "nvme" in link_lower:
                return "NVMe"
        except OSError:
            pass
        return "Unknown"

    def _get_macos_info(self, device: str) -> tuple[str, str, str]:
        """Use diskutil on macOS to get model/serial/interface."""
        out = self._run(["diskutil", "info", device])
        model = serial = iface = "Unknown"
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("Device / Media Name:"):
                model = line.split(":", 1)[1].strip() or "Unknown"
            elif line.startswith("Volume UUID:"):
                pass
            elif line.startswith("Media Serial Number:"):
                serial = line.split(":", 1)[1].strip() or "Unknown"
            elif line.startswith("Protocol:"):
                proto = line.split(":", 1)[1].strip()
                if "USB" in proto:
                    iface = "USB"
                elif "NVMe" in proto:
                    iface = "NVMe"
                elif proto:
                    iface = proto
        return model, serial, iface

    def list_drives(self) -> list[DriveInfo]:
        is_macos = sys.platform == "darwin"
        drives: list[DriveInfo] = []
        for p in psutil.disk_partitions(all=False):
            if not p.mountpoint:
                continue
            if p.fstype.lower() in _SKIP_FSTYPES:
                continue
            try:
                usage = psutil.disk_usage(p.mountpoint)
            except (PermissionError, FileNotFoundError, OSError):
                continue

            if is_macos:
                model, serial, iface = self._get_macos_info(p.device)
            else:
                dev_base = self._block_device_for_mount(p.mountpoint)
                if dev_base:
                    model = self._read_sys(dev_base, "model")
                    serial = self._read_sys(dev_base, "serial")
                    iface = self._get_interface(dev_base)
                else:
                    model = serial = iface = "Unknown"

            drives.append(DriveInfo(
                device=p.device,
                mountpoint=p.mountpoint,
                fstype=p.fstype,
                total=usage.total,
                used=usage.used,
                free=usage.free,
                model=model,
                serial=serial,
                interface=iface,
            ))
        return drives

    def get_drive_info(self, path: str) -> Optional[DriveInfo]:
        path = os.path.realpath(path)
        best: Optional[DriveInfo] = None
        for drive in self.list_drives():
            if path.startswith(drive.mountpoint):
                if best is None or len(drive.mountpoint) > len(best.mountpoint):
                    best = drive
        return best
