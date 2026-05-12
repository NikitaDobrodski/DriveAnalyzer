import os
from typing import Optional

import psutil

from driveanalyzer.adapters.os_adapter import DriveInfo, OSAdapter


class WindowsAdapter(OSAdapter):

    def _get_wmi_data(self) -> dict[str, tuple[str, str, str]]:
        """Returns dict mapping uppercase drive letter (e.g. 'C:\\') to (model, serial, interface)."""
        data: dict[str, tuple[str, str, str]] = {}
        try:
            import wmi  # type: ignore
            c = wmi.WMI()
            for disk in c.Win32_DiskDrive():
                model = (disk.Model or "").strip() or "Unknown"
                serial = (disk.SerialNumber or "").strip() or "Unknown"
                raw_iface = (disk.InterfaceType or "").upper()

                if "USB" in raw_iface:
                    iface = "USB"
                elif "nvme" in model.lower():
                    iface = "NVMe"
                elif raw_iface in ("SCSI", "IDE", "ATA", "SATA"):
                    iface = "SATA"
                else:
                    iface = raw_iface or "Unknown"

                try:
                    for part in disk.associators("Win32_DiskDriveToDiskPartition"):
                        for logical in part.associators("Win32_LogicalDiskToPartition"):
                            letter = logical.DeviceID.upper() + "\\"
                            data[letter] = (model, serial, iface)
                except Exception:
                    pass
        except Exception:
            pass
        return data

    def list_drives(self) -> list[DriveInfo]:
        wmi_data = self._get_wmi_data()
        drives: list[DriveInfo] = []
        for p in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(p.mountpoint)
            except (PermissionError, OSError):
                continue
            key = p.mountpoint.upper()
            model, serial, iface = wmi_data.get(key, ("Unknown", "Unknown", "Unknown"))
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
        path = os.path.abspath(path)
        drive_letter = os.path.splitdrive(path)[0].upper() + "\\"
        for drive in self.list_drives():
            if drive.mountpoint.upper() == drive_letter:
                return drive
        return None
