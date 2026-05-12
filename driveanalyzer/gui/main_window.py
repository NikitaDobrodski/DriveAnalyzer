from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from driveanalyzer.adapters.os_adapter import DriveInfo
from driveanalyzer.core.analyzer import DriveAnalyzer
from driveanalyzer.core.smart import SMARTData
from driveanalyzer.core.speed_test import RANDOM_OPS, SpeedResult
from driveanalyzer.gui.workers import HealthWorker, SpeedWorker

STYLE = """
QMainWindow, QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
}
QListWidget {
    background-color: #181825;
    border: none;
    border-radius: 8px;
    padding: 4px;
}
QListWidget::item {
    padding: 10px 14px;
    border-radius: 6px;
    color: #cdd6f4;
}
QListWidget::item:selected {
    background-color: #313244;
    color: #cba6f7;
}
QListWidget::item:hover:!selected {
    background-color: #252535;
}
QTabWidget::pane {
    border: none;
    background-color: #1e1e2e;
}
QTabBar::tab {
    background-color: #181825;
    color: #a6adc8;
    padding: 8px 22px;
    border-radius: 6px 6px 0 0;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #313244;
    color: #cba6f7;
}
QPushButton {
    background-color: #cba6f7;
    color: #1e1e2e;
    border: none;
    border-radius: 6px;
    padding: 8px 20px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #d5b8ff;
}
QPushButton:pressed {
    background-color: #b893e8;
}
QPushButton:disabled {
    background-color: #45475a;
    color: #6c7086;
}
QProgressBar {
    border: none;
    border-radius: 4px;
    background-color: #313244;
    height: 10px;
    text-align: center;
}
QProgressBar::chunk {
    border-radius: 4px;
    background-color: #cba6f7;
}
QSpinBox {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 4px 8px;
}
QFrame[frameShape="4"], QFrame[frameShape="5"] {
    color: #313244;
}
QStatusBar {
    background-color: #181825;
    color: #6c7086;
}
"""


def _label(text: str, bold: bool = False, color: str = "") -> QLabel:
    lbl = QLabel(text)
    font = lbl.font()
    if bold:
        font.setBold(True)
    lbl.setFont(font)
    if color:
        lbl.setStyleSheet(f"color: {color};")
    return lbl


def _row(key: str, value: str, value_color: str = "") -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 2, 0, 2)
    key_lbl = _label(key, bold=True)
    key_lbl.setStyleSheet("color: #a6adc8;")
    key_lbl.setFixedWidth(160)
    val_lbl = _label(value, color=value_color)
    lay.addWidget(key_lbl)
    lay.addWidget(val_lbl)
    lay.addStretch()
    return w


def _separator() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet("color: #313244;")
    return line


class DriveListPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title = _label("  Диски", bold=True)
        title.setStyleSheet("color: #cba6f7; font-size: 15px; padding: 8px 0;")
        layout.addWidget(title)

        self.list_widget = QListWidget()
        self.list_widget.setMinimumWidth(140)
        layout.addWidget(self.list_widget)

        refresh_btn = QPushButton("Обновить")
        refresh_btn.clicked.connect(self._on_refresh)
        layout.addWidget(refresh_btn)

        self._analyzer = DriveAnalyzer()
        self._drives: list[DriveInfo] = []
        self.refresh()

    def refresh(self) -> None:
        self._drives = self._analyzer.device_info.list_all()
        self.list_widget.clear()
        for d in self._drives:
            item = QListWidgetItem(f"  {d.mountpoint.rstrip(chr(92))}  ")
            self.list_widget.addItem(item)
        if self._drives:
            self.list_widget.setCurrentRow(0)

    def _on_refresh(self) -> None:
        self.refresh()

    def selected_drive(self) -> Optional[DriveInfo]:
        row = self.list_widget.currentRow()
        if 0 <= row < len(self._drives):
            return self._drives[row]
        return None

    def drives(self) -> list[DriveInfo]:
        return self._drives


class InfoTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self._layout.setSpacing(6)
        self._layout.addStretch()

    def update_drive(self, drive: DriveInfo) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._layout.addWidget(_label(drive.mountpoint.rstrip("\\"), bold=True,
                                      color="#cba6f7"))
        self._layout.addSpacing(8)
        self._layout.addWidget(_separator())
        self._layout.addSpacing(4)

        self._layout.addWidget(_row("Устройство", drive.device))
        self._layout.addWidget(_row("Файловая система", drive.fstype or "N/A"))
        self._layout.addWidget(_row("Модель", drive.model))
        self._layout.addWidget(_row("Серийный номер", drive.serial))
        self._layout.addWidget(_row("Интерфейс", drive.interface))
        self._layout.addSpacing(12)
        self._layout.addWidget(_separator())
        self._layout.addSpacing(4)

        total_gb = drive.total / 1024 ** 3
        used_gb = drive.used / 1024 ** 3
        free_gb = drive.free / 1024 ** 3
        pct = drive.usage_percent

        self._layout.addWidget(_row("Всего", f"{total_gb:.1f} GB"))
        self._layout.addWidget(_row("Занято", f"{used_gb:.1f} GB"))
        self._layout.addWidget(_row("Свободно", f"{free_gb:.1f} GB"))

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(int(pct))
        bar.setFormat(f"{pct:.1f}%")
        bar.setFixedHeight(14)
        if pct >= 90:
            bar.setStyleSheet(bar.styleSheet() +
                              "QProgressBar::chunk { background-color: #f38ba8; }")
        elif pct >= 75:
            bar.setStyleSheet(bar.styleSheet() +
                              "QProgressBar::chunk { background-color: #fab387; }")
        self._layout.addWidget(bar)
        self._layout.addStretch()


class SpeedTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._mountpoint: Optional[str] = None
        self._worker: Optional[SpeedWorker] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        ctrl = QHBoxLayout()
        ctrl.addWidget(_label("Размер файла (MB):"))
        self._size_spin = QSpinBox()
        self._size_spin.setRange(64, 4096)
        self._size_spin.setValue(512)
        self._size_spin.setSingleStep(64)
        ctrl.addWidget(self._size_spin)
        ctrl.addStretch()
        self._run_btn = QPushButton("Запустить тест")
        self._run_btn.clicked.connect(self._run)
        ctrl.addWidget(self._run_btn)
        layout.addLayout(ctrl)
        layout.addWidget(_separator())

        self._status_lbl = _label("Нажмите кнопку для запуска теста",
                                   color="#6c7086")
        layout.addWidget(self._status_lbl)

        self._results = QStackedWidget()
        self._empty = QWidget()
        self._results_widget = self._build_results_widget()
        self._results.addWidget(self._empty)
        self._results.addWidget(self._results_widget)
        layout.addWidget(self._results)
        layout.addStretch()

    def _build_results_widget(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(6)
        self._write_row = _label("")
        self._read_row = _label("")
        self._random_row = _label("")
        lay.addWidget(self._write_row)
        lay.addWidget(self._read_row)
        lay.addWidget(self._random_row)
        return w

    def set_mountpoint(self, mountpoint: str) -> None:
        self._mountpoint = mountpoint
        self._status_lbl.setText("Нажмите кнопку для запуска теста")
        self._status_lbl.setStyleSheet("color: #6c7086;")
        self._results.setCurrentIndex(0)

    def _run(self) -> None:
        if not self._mountpoint:
            return
        self._run_btn.setEnabled(False)
        self._status_lbl.setText("Тест запущен, подождите...")
        self._status_lbl.setStyleSheet("color: #a6e3a1;")
        self._results.setCurrentIndex(0)

        self._worker = SpeedWorker(self._mountpoint, self._size_spin.value())
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_done(self, result: SpeedResult) -> None:
        self._run_btn.setEnabled(True)
        self._status_lbl.setText("Тест завершён")
        self._status_lbl.setStyleSheet("color: #a6e3a1;")

        def fmt(v, write=False):
            if v is None:
                return "<span style='color:#6c7086'>N/A</span>"
            thresholds = (30, 100) if write else (50, 150)
            color = "#a6e3a1" if v >= thresholds[1] else (
                "#fab387" if v >= thresholds[0] else "#f38ba8")
            return f"<span style='color:{color}; font-size:15px; font-weight:bold'>{v:.1f} MB/s</span>"

        size = result.file_size_mb
        self._write_row.setText(
            f"<b style='color:#a6adc8'>Последовательная запись ({size} MB):</b>  "
            f"{fmt(result.write_seq_mbps, write=True)}")
        self._write_row.setTextFormat(Qt.TextFormat.RichText)
        self._read_row.setText(
            f"<b style='color:#a6adc8'>Последовательное чтение ({size} MB):</b>  "
            f"{fmt(result.read_seq_mbps)}")
        self._read_row.setTextFormat(Qt.TextFormat.RichText)
        self._random_row.setText(
            f"<b style='color:#a6adc8'>Случайное чтение ({RANDOM_OPS} ops x 4KB):</b>  "
            f"{fmt(result.read_random_mbps)}")
        self._random_row.setTextFormat(Qt.TextFormat.RichText)
        self._results.setCurrentIndex(1)

    def _on_error(self, msg: str) -> None:
        self._run_btn.setEnabled(True)
        self._status_lbl.setText(f"Ошибка: {msg}")
        self._status_lbl.setStyleSheet("color: #f38ba8;")


class HealthTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._mountpoint: Optional[str] = None
        self._worker: Optional[HealthWorker] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        ctrl = QHBoxLayout()
        self._run_btn = QPushButton("Проверить SMART")
        self._run_btn.clicked.connect(self._run)
        ctrl.addWidget(self._run_btn)
        ctrl.addStretch()
        layout.addLayout(ctrl)
        layout.addWidget(_separator())

        self._status_lbl = _label("Нажмите кнопку для проверки", color="#6c7086")
        layout.addWidget(self._status_lbl)

        self._results_area = QVBoxLayout()
        layout.addLayout(self._results_area)
        layout.addStretch()

    def set_mountpoint(self, mountpoint: str) -> None:
        self._mountpoint = mountpoint
        self._status_lbl.setText("Нажмите кнопку для проверки")
        self._status_lbl.setStyleSheet("color: #6c7086;")
        self._clear_results()

    def _clear_results(self) -> None:
        while self._results_area.count():
            item = self._results_area.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _run(self) -> None:
        if not self._mountpoint:
            return
        self._run_btn.setEnabled(False)
        self._status_lbl.setText("Считывание SMART...")
        self._status_lbl.setStyleSheet("color: #a6e3a1;")
        self._clear_results()

        self._worker = HealthWorker(self._mountpoint)
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_done(self, smart: SMARTData) -> None:
        self._run_btn.setEnabled(True)
        status_colors = {"PASSED": "#a6e3a1", "FAILED": "#f38ba8"}
        color = status_colors.get(smart.status, "#fab387")
        self._status_lbl.setText(
            f"<span style='color:{color}; font-weight:bold; font-size:15px'>"
            f"{smart.status}</span>")
        self._status_lbl.setTextFormat(Qt.TextFormat.RichText)

        self._clear_results()
        rows = [
            ("Модель", smart.model),
            ("Серийный номер", smart.serial),
            ("Прошивка", smart.firmware),
        ]
        if smart.temperature_c is not None:
            temp = smart.temperature_c
            tc = "#f38ba8" if temp >= 60 else "#fab387" if temp >= 50 else "#a6e3a1"
            rows.append(("Температура",
                         f"<span style='color:{tc}'>{temp} °C</span>"))
        if smart.power_on_hours is not None:
            rows.append(("Часов работы", str(smart.power_on_hours)))

        def sect_color(v):
            return "#f38ba8" if v and v > 0 else "#a6e3a1"

        for label, field_val in [
            ("Переназначенных секторов", smart.reallocated_sectors),
            ("Ожидающих секторов", smart.pending_sectors),
            ("Неисправимых ошибок", smart.uncorrectable_errors),
        ]:
            if field_val is not None:
                c = sect_color(field_val)
                rows.append((label,
                              f"<span style='color:{c}'>{field_val}</span>"))

        for key, val in rows:
            w = QWidget()
            lay = QHBoxLayout(w)
            lay.setContentsMargins(0, 2, 0, 2)
            k = _label(key, bold=True)
            k.setStyleSheet("color: #a6adc8;")
            k.setFixedWidth(200)
            v = QLabel()
            v.setText(str(val))
            v.setTextFormat(Qt.TextFormat.RichText)
            lay.addWidget(k)
            lay.addWidget(v)
            lay.addStretch()
            self._results_area.addWidget(w)

        if smart.warnings:
            self._results_area.addWidget(_separator())
            for w_text in smart.warnings:
                lbl = _label(f"  {w_text}", color="#fab387")
                lbl.setWordWrap(True)
                self._results_area.addWidget(lbl)

    def _on_error(self, msg: str) -> None:
        self._run_btn.setEnabled(True)
        self._status_lbl.setText(f"Ошибка: {msg}")
        self._status_lbl.setStyleSheet("color: #f38ba8;")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("DriveAnalyzer")
        self.setMinimumSize(820, 520)
        self.setStyleSheet(STYLE)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background-color: #313244; }")

        self._drive_panel = DriveListPanel()
        self._drive_panel.list_widget.currentRowChanged.connect(self._on_drive_changed)
        splitter.addWidget(self._drive_panel)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self._tabs = QTabWidget()
        self._info_tab = InfoTab()
        self._speed_tab = SpeedTab()
        self._health_tab = HealthTab()
        self._tabs.addTab(self._info_tab, "Info")
        self._tabs.addTab(self._speed_tab, "Speed")
        self._tabs.addTab(self._health_tab, "Health")
        right_layout.addWidget(self._tabs)

        splitter.addWidget(right)
        splitter.setSizes([160, 660])

        self.setCentralWidget(splitter)

        status = QStatusBar()
        self.setStatusBar(status)
        self._status_bar = status

        self._on_drive_changed(0)

    def _on_drive_changed(self, _row: int) -> None:
        drive = self._drive_panel.selected_drive()
        if drive is None:
            return
        self._info_tab.update_drive(drive)
        self._speed_tab.set_mountpoint(drive.mountpoint)
        self._health_tab.set_mountpoint(drive.mountpoint)
        self._status_bar.showMessage(
            f"{drive.mountpoint}  |  {drive.model}  |  {drive.interface}")
