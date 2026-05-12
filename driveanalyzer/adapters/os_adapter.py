import sys
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DriveInfo:
    device: str
    mountpoint: str
    fstype: str
    total: int
    used: int
    free: int
    model: str = "Unknown"
    serial: str = "Unknown"
    interface: str = "Unknown"

    @property
    def usage_percent(self) -> float:
        if self.total == 0:
            return 0.0
        return self.used / self.total * 100


class OSAdapter:
    def list_drives(self) -> list[DriveInfo]:
        raise NotImplementedError

    def get_drive_info(self, path: str) -> Optional[DriveInfo]:
        raise NotImplementedError


def get_adapter() -> OSAdapter:
    if sys.platform == "win32":
        from driveanalyzer.adapters.windows import WindowsAdapter
        return WindowsAdapter()
    else:
        from driveanalyzer.adapters.linux import LinuxAdapter
        return LinuxAdapter()
