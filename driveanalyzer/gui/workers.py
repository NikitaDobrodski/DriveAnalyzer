from PyQt6.QtCore import QThread, pyqtSignal
from rich.console import Console

from driveanalyzer.core.analyzer import DriveAnalyzer
from driveanalyzer.core.smart import SMARTData
from driveanalyzer.core.speed_test import SpeedResult, SpeedTest


class SpeedWorker(QThread):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, mountpoint: str, size_mb: int) -> None:
        super().__init__()
        self.mountpoint = mountpoint
        self.size_mb = size_mb

    def run(self) -> None:
        try:
            test = SpeedTest(mountpoint=self.mountpoint, size_mb=self.size_mb)
            result: SpeedResult = test.run(Console(quiet=True))
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class HealthWorker(QThread):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, mountpoint: str) -> None:
        super().__init__()
        self.mountpoint = mountpoint

    def run(self) -> None:
        try:
            analyzer = DriveAnalyzer()
            hc = analyzer.health_check(self.mountpoint)
            result: SMARTData = hc.run_smart()
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
