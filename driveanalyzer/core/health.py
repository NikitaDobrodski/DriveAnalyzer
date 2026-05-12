from driveanalyzer.core.smart import SMARTData, SMARTReader


class HealthCheck:
    def __init__(self, mountpoint: str) -> None:
        self.mountpoint = mountpoint
        self.smart = SMARTReader.from_mountpoint(mountpoint)

    def run_smart(self) -> SMARTData:
        return self.smart.read()
