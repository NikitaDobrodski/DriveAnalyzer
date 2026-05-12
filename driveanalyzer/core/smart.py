import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional

import psutil

SMART_TIMEOUT = 10

_SMARTCTL_FALLBACKS = (
    [
        r"C:\Program Files\smartmontools\bin\smartctl.exe",
        r"C:\Program Files (x86)\smartmontools\bin\smartctl.exe",
    ]
    if sys.platform == "win32"
    else ["/usr/local/sbin/smartctl", "/usr/sbin/smartctl"]
)


def _smartctl_bin() -> Optional[str]:
    found = shutil.which("smartctl")
    if found:
        return found
    for p in _SMARTCTL_FALLBACKS:
        if os.path.isfile(p):
            return p
    return None


@dataclass
class SMARTAttribute:
    id: int
    name: str
    raw_value: int
    value: int = 0
    worst: int = 0
    thresh: int = 0


@dataclass
class SMARTData:
    status: str          # "PASSED" | "FAILED" | "UNKNOWN"
    device: str
    model: str = "Unknown"
    serial: str = "Unknown"
    firmware: str = "Unknown"
    temperature_c: Optional[int] = None
    power_on_hours: Optional[int] = None
    reallocated_sectors: Optional[int] = None
    pending_sectors: Optional[int] = None
    uncorrectable_errors: Optional[int] = None
    warnings: list[str] = field(default_factory=list)
    attributes: list[SMARTAttribute] = field(default_factory=list)
    raw_output: str = ""


def _strip_partition(device: str) -> str:
    """Remove partition suffix: /dev/sda1 → /dev/sda, /dev/nvme0n1p1 → /dev/nvme0n1."""
    base = re.sub(r"p\d+$", "", device)   # NVMe/eMMC
    if base != device:
        return base
    stripped = re.sub(r"\d+$", "", device)  # SATA/USB
    return stripped or device


def _resolve_device(mountpoint: str) -> str:
    """Convert a mountpoint (or path) to a smartctl device string."""
    if sys.platform == "win32":
        drive = os.path.splitdrive(mountpoint)[0]  # "C:\" → "C:"
        return drive if drive else mountpoint
    for p in psutil.disk_partitions(all=True):
        if os.path.normpath(p.mountpoint) == os.path.normpath(mountpoint):
            return _strip_partition(p.device)
    return _strip_partition(mountpoint)


def _is_admin_windows() -> bool:
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


class SMARTReader:
    def __init__(self, device_path: str) -> None:
        self.device_path = device_path

    @classmethod
    def from_mountpoint(cls, mountpoint: str) -> "SMARTReader":
        return cls(_resolve_device(mountpoint))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def read(self) -> SMARTData:
        smartctl = _smartctl_bin()
        if not smartctl:
            return self._unavailable(
                "smartctl not found. Install smartmontools: https://www.smartmontools.org"
            )

        if sys.platform == "win32" and not _is_admin_windows():
            return self._unavailable(
                "SMART data requires administrator privileges on Windows. "
                "Run the program as Administrator."
            )

        proc = self._run(smartctl, ["-a", "--json=c", self.device_path])
        if proc is None:
            return self._unavailable("smartctl timed out or could not be started.")

        # smartctl returns exit codes as bitmask; code 0 or 4 (attribute warning)
        # are still valid outputs. Codes ≥ 8 indicate access/parse failure.
        if proc.returncode >= 8 and not proc.stdout.strip():
            return self._unavailable(
                f"smartctl returned error code {proc.returncode}. "
                "Try running as root/administrator."
            )

        try:
            data = json.loads(proc.stdout)
            return self._parse_json(data, proc.stdout)
        except (json.JSONDecodeError, ValueError):
            return self._parse_text(proc.stdout, proc.returncode)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _unavailable(self, message: str) -> SMARTData:
        return SMARTData(status="UNKNOWN", device=self.device_path, warnings=[message])

    def _run(self, smartctl: str, args: list[str]) -> Optional[subprocess.CompletedProcess]:
        try:
            return subprocess.run(
                [smartctl] + args,
                capture_output=True,
                text=True,
                timeout=SMART_TIMEOUT,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return None

    def _parse_json(self, data: dict, raw: str) -> SMARTData:
        smart_status = data.get("smart_status", {})
        passed = smart_status.get("passed")
        if passed is True:
            status = "PASSED"
        elif passed is False:
            status = "FAILED"
        else:
            status = "UNKNOWN"

        model = data.get("model_name", "Unknown").strip()
        serial = data.get("serial_number", "Unknown").strip()
        firmware = data.get("firmware_version", "Unknown").strip()

        temp: Optional[int] = data.get("temperature", {}).get("current")
        power_on: Optional[int] = data.get("power_on_time", {}).get("hours")

        reallocated = pending = uncorrectable = None
        warnings: list[str] = []
        attrs: list[SMARTAttribute] = []

        for a in data.get("ata_smart_attributes", {}).get("table", []):
            aid = a.get("id", 0)
            raw_val = a.get("raw", {}).get("value", 0)
            attrs.append(SMARTAttribute(
                id=aid,
                name=a.get("name", "Unknown"),
                raw_value=raw_val,
                value=a.get("value", 0),
                worst=a.get("worst", 0),
                thresh=a.get("thresh", 0),
            ))
            if aid == 5:
                reallocated = raw_val
            elif aid == 197:
                pending = raw_val
            elif aid == 198:
                uncorrectable = raw_val
            elif aid == 9 and power_on is None:
                power_on = raw_val

        # NVMe health log
        nvme = data.get("nvme_smart_health_information_log", {})
        if nvme:
            if power_on is None:
                power_on = nvme.get("power_on_hours")
            if temp is None:
                raw_temp = nvme.get("temperature")
                if raw_temp is not None:
                    temp = raw_temp  # smartctl 7.x outputs Celsius directly
            media_err = nvme.get("media_errors", 0)
            if media_err:
                uncorrectable = media_err
                warnings.append(f"NVMe media errors: {media_err}")
            crit = nvme.get("critical_warning", 0)
            if crit:
                warnings.append(f"NVMe critical warning flags: {crit:#04x}")

        warnings += _build_attr_warnings(reallocated, pending, uncorrectable)
        if status == "FAILED":
            warnings.insert(0, "SMART self-assessment FAILED - drive failure may be imminent!")

        return SMARTData(
            status=status,
            device=self.device_path,
            model=model,
            serial=serial,
            firmware=firmware,
            temperature_c=temp,
            power_on_hours=power_on,
            reallocated_sectors=reallocated,
            pending_sectors=pending,
            uncorrectable_errors=uncorrectable,
            warnings=warnings,
            attributes=attrs,
            raw_output=raw,
        )

    def _parse_text(self, output: str, returncode: int) -> SMARTData:
        """Fallback parser for smartctl builds without --json support."""
        status = "UNKNOWN"
        if "SMART overall-health self-assessment test result: PASSED" in output:
            status = "PASSED"
        elif "SMART overall-health self-assessment test result: FAILED" in output:
            status = "FAILED"

        model = serial = firmware = "Unknown"
        temp: Optional[int] = None
        power_on: Optional[int] = None
        reallocated = pending = uncorrectable = None
        attrs: list[SMARTAttribute] = []

        for line in output.splitlines():
            if line.startswith("Device Model:") or line.startswith("Product:"):
                model = line.split(":", 1)[1].strip()
            elif line.startswith("Serial Number:") or line.startswith("Serial number:"):
                serial = line.split(":", 1)[1].strip()
            elif line.startswith("Firmware Version:"):
                firmware = line.split(":", 1)[1].strip()
            elif "Temperature_Celsius" in line or "Airflow_Temperature" in line:
                m = re.search(r"\s(\d+)$", line)
                if m:
                    temp = int(m.group(1))

            # ATA attribute line: ID# ATTRIBUTE_NAME FLAG VALUE WORST THRESH TYPE UPDATED WHEN_FAILED RAW_VALUE
            m = re.match(
                r"\s*(\d+)\s+(\S+)\s+\S+\s+(\d+)\s+(\d+)\s+(\d+)\s+\S+\s+\S+\s+\S+\s+(\d+)",
                line,
            )
            if m:
                aid = int(m.group(1))
                raw_val = int(m.group(6))
                attrs.append(SMARTAttribute(
                    id=aid,
                    name=m.group(2),
                    raw_value=raw_val,
                    value=int(m.group(3)),
                    worst=int(m.group(4)),
                    thresh=int(m.group(5)),
                ))
                if aid == 5:
                    reallocated = raw_val
                elif aid == 197:
                    pending = raw_val
                elif aid == 198:
                    uncorrectable = raw_val
                elif aid == 9:
                    power_on = raw_val

        warnings = _build_attr_warnings(reallocated, pending, uncorrectable)
        if status == "FAILED":
            warnings.insert(0, "SMART self-assessment FAILED - drive failure may be imminent!")

        return SMARTData(
            status=status,
            device=self.device_path,
            model=model,
            serial=serial,
            firmware=firmware,
            temperature_c=temp,
            power_on_hours=power_on,
            reallocated_sectors=reallocated,
            pending_sectors=pending,
            uncorrectable_errors=uncorrectable,
            warnings=warnings,
            attributes=attrs,
            raw_output=output,
        )


def _build_attr_warnings(
    reallocated: Optional[int],
    pending: Optional[int],
    uncorrectable: Optional[int],
) -> list[str]:
    msgs: list[str] = []
    if reallocated is not None and reallocated > 0:
        msgs.append(f"Reallocated sectors: {reallocated} - drive has remapped bad sectors!")
    if pending is not None and pending > 0:
        msgs.append(f"Pending sectors: {pending} - unstable sectors awaiting reallocation!")
    if uncorrectable is not None and uncorrectable > 0:
        msgs.append(f"Uncorrectable errors: {uncorrectable}")
    return msgs
