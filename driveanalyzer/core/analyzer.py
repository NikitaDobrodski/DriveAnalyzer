from driveanalyzer.adapters.os_adapter import get_adapter
from driveanalyzer.core.device_info import DeviceInfo
from driveanalyzer.core.health import HealthCheck


class DriveAnalyzer:
    def __init__(self) -> None:
        self.adapter = get_adapter()
        self.device_info = DeviceInfo(self.adapter)

    def health_check(self, mountpoint: str) -> HealthCheck:
        return HealthCheck(mountpoint)
