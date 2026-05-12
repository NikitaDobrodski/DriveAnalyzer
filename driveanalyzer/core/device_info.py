from typing import Optional

from driveanalyzer.adapters.os_adapter import DriveInfo, OSAdapter


class DeviceInfo:
    def __init__(self, adapter: OSAdapter) -> None:
        self.adapter = adapter

    def list_all(self) -> list[DriveInfo]:
        return self.adapter.list_drives()

    def get_info(self, path: str) -> Optional[DriveInfo]:
        return self.adapter.get_drive_info(path)
