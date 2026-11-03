from __future__ import annotations
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent, QFont, QIcon
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QTextEdit, QCheckBox, QSpinBox, QSplitter, QMessageBox, QFrame,
    QApplication
)
from core.config import ConfigManager, normalize_target_name
from core.hunter import ProcessHunter, ProcessInfo, KillResult
from core.autostart import WindowsAutostart
from core.logger import LogEvent
from ui.components.process_table import ProcessTableWidget
from ui.components.target_list import TargetListWidget
from ui.workers import SentinelWorker, ProcessScannerWorker
from ui.tray import HunterTrayIcon, create_tray_pixmap


class MainWindow(QMainWindow):
    def __init__(
        self,
        config_manager: ConfigManager,
        hunter: ProcessHunter,
        autostart: WindowsAutostart,
        tray_icon: Optional[HunterTrayIcon] = None,
        logger: Optional[logging.Logger] = None,
        parent=None
    ) -> None:
        super().__init__(parent)
        self.config_manager = config_manager
        self.hunter = hunter
        self.autostart = autostart
        self.tray_icon = tray_icon
        self.logger = logger or logging.getLogger("ProcessHunter")
        self._is_force_exit = False

        self.setWindowTitle("ProcessHunter - Gerenciador de Processos")
        self.resize(1050, 720)
        self.setWindowIcon(QIcon(create_tray_pixmap(is_active=False)))

        # Background workers
        self.sentinel_worker = SentinelWorker(
            hunter=self.hunter,
            config_manager=self.config_manager,
            parent=self
        )
        self.scanner_worker: Optional[ProcessScannerWorker] = None

        self._init_ui()
        self._connect_signals()
        self._load_initial_data()

    def _init_ui(self) -> None:
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(12, 12, 12, 12)

        # 1. Top Header & Control Bar
        header_frame = QFrame()
        header_frame.setFrameShape(QFrame.Shape.StyledPanel)
        header_frame.setStyleSheet("""
            QFrame {
                background-color: #2b2b2b;
                border-radius: 6px;
                padding: 6px;
            }
            QLabel { color: #ffffff; }
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(10, 6, 10, 6)

        # Status badge
        self.status_badge = QLabel("○ Sentinela: PAUSADA")
        self.status_badge.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.status_badge.setStyleSheet("color: #aaaaaa;")
        header_layout.addWidget(self.status_badge)

        header_layout.addStretch()

        self.btn_hunt_now = QPushButton("⚡ Caçar Agora")
        self.btn_hunt_now.setStyleSheet("""
            QPushButton {
                background-color: #d32f2f;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #b71c1c; }
        """)
        header_layout.addWidget(self.btn_hunt_now)

        self.btn_toggle_sentinel = QPushButton("🛡️ Iniciar Sentinela")
        self.btn_toggle_sentinel.setStyleSheet("""
            QPushButton {
                background-color: #2e7d32;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #1b5e20; }
        """)
        header_layout.addWidget(self.btn_toggle_sentinel)

        main_layout.addWidget(header_frame)

        # 2. Central Splitter (Left: Targets, Right: Active Processes)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.target_list_widget = TargetListWidget()
        splitter.addWidget(self.target_list_widget)

        self.process_table_widget = ProcessTableWidget()
        splitter.addWidget(self.process_table_widget)

        splitter.setSizes([450, 600])
        main_layout.addWidget(splitter, stretch=2)

        # 3. Bottom Section: Log and Preferences
        bottom_layout = QVBoxLayout()

        # Log bar header
        log_header_layout = QHBoxLayout()
        log_title = QLabel("<b>Histórico de Atividades & Logs</b>")
        log_header_layout.addWidget(log_title)
        log_header_layout.addStretch()

        self.btn_clear_log = QPushButton("🧹 Limpar")
        self.btn_clear_log.clicked.connect(self._clear_log)
        log_header_layout.addWidget(self.btn_clear_log)

        self.btn_open_logfile = QPushButton("📂 Abrir Arquivo de Log")
        self.btn_open_logfile.clicked.connect(self._open_logfile)
        log_header_layout.addWidget(self.btn_open_logfile)

        bottom_layout.addLayout(log_header_layout)

        # Log Console
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                font-family: Consolas, monospace;
                font-size: 10pt;
                border: 1px solid #333333;
                border-radius: 4px;
            }
        """)
        self.log_view.setMaximumHeight(160)
        bottom_layout.addWidget(self.log_view)

        # Settings bar
        settings_layout = QHBoxLayout()
        self.chk_autostart = QCheckBox("Iniciar com o Windows (Minimizado na bandeja)")
        self.chk_autostart.toggled.connect(self._on_autostart_toggled)
        settings_layout.addWidget(self.chk_autostart)

        settings_layout.addSpacing(20)

        interval_label = QLabel("Intervalo da Sentinela:")
        settings_layout.addWidget(interval_label)

        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(1, 300)
        self.spin_interval.setSuffix(" seg")
        self.spin_interval.valueChanged.connect(self._on_interval_changed)
        settings_layout.addWidget(self.spin_interval)

        settings_layout.addSpacing(20)

        self.chk_notify = QCheckBox("Notificar na área de trabalho ao caçar")
        self.chk_notify.toggled.connect(self._on_notify_toggled)
        settings_layout.addWidget(self.chk_notify)

        settings_layout.addStretch()
        bottom_layout.addLayout(settings_layout)

        main_layout.addLayout(bottom_layout, stretch=1)

    def _connect_signals(self) -> None:
        # Top buttons
        self.btn_hunt_now.clicked.connect(self.hunt_now)
        self.btn_toggle_sentinel.clicked.connect(self.toggle_sentinel)

        # Target list events
        self.target_list_widget.target_added.connect(self._on_target_added)
        self.target_list_widget.target_removed.connect(self._on_target_removed)
        self.target_list_widget.target_toggled.connect(self._on_target_toggled)

        # Process table events
        self.process_table_widget.add_target_requested.connect(self._on_target_added)
        self.process_table_widget.refresh_requested.connect(self.refresh_active_processes)

        # Sentinel worker events
        self.sentinel_worker.hunt_completed.connect(self._on_hunt_completed)
        self.sentinel_worker.status_changed.connect(self._on_sentinel_status_changed)
        self.sentinel_worker.log_message.connect(self.append_log_message)

        # Tray signals (if attached)
        if self.tray_icon:
            self.tray_icon.restore_requested.connect(self.restore_window)
            self.tray_icon.hunt_now_requested.connect(self.hunt_now)
            self.tray_icon.toggle_sentinel_requested.connect(self.toggle_sentinel)
            self.tray_icon.exit_requested.connect(self.force_exit)

    def _load_initial_data(self) -> None:
        cfg = self.config_manager.config
        self.target_list_widget.set_targets(cfg.targets)
        self.spin_interval.setValue(cfg.sentinel_interval_seconds)
        self.sentinel_worker.set_interval(cfg.sentinel_interval_seconds)
        self.chk_notify.setChecked(cfg.notify_on_kill)

        # Check registry autostart state
        is_autostart = self.autostart.is_enabled()
        self.chk_autostart.blockSignals(True)
        self.chk_autostart.setChecked(is_autostart)
        self.chk_autostart.blockSignals(False)

        # Initial scan of processes
        QTimer.singleShot(200, self.refresh_active_processes)

    def refresh_active_processes(self) -> None:
        if self.scanner_worker and self.scanner_worker.isRunning():
            return
        self.process_table_widget.btn_refresh.setEnabled(False)
        self.scanner_worker = ProcessScannerWorker(hunter=self.hunter, parent=self)
        self.scanner_worker.scan_completed.connect(self._on_scan_completed)
        self.scanner_worker.scan_failed.connect(self._on_scan_failed)
        self.scanner_worker.start()

    def _on_scan_completed(self, processes: List[ProcessInfo]) -> None:
        self.process_table_widget.set_processes(processes)
        self.process_table_widget.btn_refresh.setEnabled(True)

        # Count active target instances
        counts: dict[str, int] = {}
        for p in processes:
            norm = normalize_target_name(p.name)
            counts[norm] = counts.get(norm, 0) + 1
        self.target_list_widget.update_running_counts(counts)

    def _on_scan_failed(self, error: str) -> None:
        self.process_table_widget.btn_refresh.setEnabled(True)
        self.append_log_message("ERROR", f"Falha ao listar processos: {error}")

    def hunt_now(self) -> None:
        active_targets = self.config_manager.get_active_targets()
        if not active_targets:
            self.append_log_message("WARNING", "Nenhum alvo ativo configurado para caçar.")
            return

        self.append_log_message("INFO", f"Iniciando caçada manual de {len(active_targets)} alvos...")
        results = self.hunter.kill_targets(active_targets)
        self._on_hunt_completed(results)
        QTimer.singleShot(500, self.refresh_active_processes)

    def toggle_sentinel(self) -> None:
        if self.sentinel_worker.is_sentinel_running():
            self.sentinel_worker.stop()
        else:
            self.sentinel_worker.start()

    def _on_sentinel_status_changed(self, is_running: bool) -> None:
        if is_running:
            self.status_badge.setText(f"● Sentinela: ATIVA ({self.config_manager.config.sentinel_interval_seconds}s)")
            self.status_badge.setStyleSheet("color: #4caf50;")
            self.btn_toggle_sentinel.setText("⏸️ Pausar Sentinela")
            self.btn_toggle_sentinel.setStyleSheet("""
                QPushButton {
                    background-color: #f57c00;
                    color: white;
                    font-weight: bold;
                    padding: 8px 16px;
                    border-radius: 4px;
                }
                QPushButton:hover { background-color: #e65100; }
            """)
        else:
            self.status_badge.setText("○ Sentinela: PAUSADA")
            self.status_badge.setStyleSheet("color: #aaaaaa;")
            self.btn_toggle_sentinel.setText("🛡️ Iniciar Sentinela")
            self.btn_toggle_sentinel.setStyleSheet("""
                QPushButton {
                    background-color: #2e7d32;
                    color: white;
                    font-weight: bold;
                    padding: 8px 16px;
                    border-radius: 4px;
                }
                QPushButton:hover { background-color: #1b5e20; }
            """)

        if self.tray_icon:
            self.tray_icon.update_status(is_running)

    def _on_hunt_completed(self, results: List[KillResult]) -> None:
        if not results:
            self.append_log_message("INFO", "Nenhuma instância dos alvos estava em execução.")
            return

        success_count = sum(1 for r in results if r.success)
        for r in results:
            if r.success:
                msg = f"SUCESSO: Processo '{r.name}' (PID: {r.pid}) encerrado."
                self.append_log_message("SUCCESS", msg)
            else:
                msg = f"FALHA: Não foi possível encerrar '{r.name}' (PID: {r.pid}). {r.error_message}"
                self.append_log_message("ERROR", msg)

        if success_count > 0:
            QTimer.singleShot(500, self.refresh_active_processes)
            if self.config_manager.config.notify_on_kill and self.tray_icon:
                self.tray_icon.notify_kill(results)

    def _on_target_added(self, name: str) -> None:
        if self.config_manager.add_target(name):
            self.target_list_widget.set_targets(self.config_manager.config.targets)
            self.append_log_message("INFO", f"Alvo adicionado: '{normalize_target_name(name)}'")
            self.refresh_active_processes()
        else:
            self.append_log_message("WARNING", f"Alvo '{normalize_target_name(name)}' já está na lista.")

    def _on_target_removed(self, name: str) -> None:
        if self.config_manager.remove_target(name):
            self.target_list_widget.set_targets(self.config_manager.config.targets)
            self.append_log_message("INFO", f"Alvo removido: '{name}'")
            self.refresh_active_processes()

    def _on_target_toggled(self, name: str, enabled: bool) -> None:
        self.config_manager.toggle_target(name, enabled)
        self.target_list_widget.set_targets(self.config_manager.config.targets)
        status_str = "ativado" if enabled else "desativado"
        self.append_log_message("INFO", f"Alvo '{name}' {status_str}.")

    def _on_autostart_toggled(self, checked: bool) -> None:
        entrypoint = str(Path(__file__).parent.parent / "app.py")
        if checked:
            success = self.autostart.enable(entrypoint_path=entrypoint, start_minimized=True)
            if success:
                self.config_manager.config.autostart = True
                self.config_manager.save()
                self.append_log_message("SUCCESS", "Inicialização com o Windows ativada com sucesso.")
            else:
                self.append_log_message("ERROR", "Falha ao registrar inicialização no Registro do Windows.")
                self.chk_autostart.setChecked(False)
        else:
            success = self.autostart.disable()
            if success:
                self.config_manager.config.autostart = False
                self.config_manager.save()
                self.append_log_message("INFO", "Inicialização com o Windows desativada.")
            else:
                self.append_log_message("ERROR", "Falha ao remover chave de registro.")

    def _on_interval_changed(self, value: int) -> None:
        self.config_manager.set_sentinel_interval(value)
        self.sentinel_worker.set_interval(value)
        if self.sentinel_worker.is_sentinel_running():
            self.status_badge.setText(f"● Sentinela: ATIVA ({value}s)")

    def _on_notify_toggled(self, checked: bool) -> None:
        self.config_manager.config.notify_on_kill = checked
        self.config_manager.save()

    def append_log_message(self, level: str, message: str) -> None:
        color_map = {
            "SUCCESS": "#4caf50",
            "INFO": "#2196f3",
            "WARNING": "#ff9800",
            "ERROR": "#f44336"
        }
        color = color_map.get(level.upper(), "#ffffff")
        html = f"<span style='color: {color};'><b>[{level.upper()}]</b> {message}</span>"
        self.log_view.append(html)

        # Write to physical logger as well
        if self.logger:
            lvl = level.upper()
            if lvl in ("ERROR", "FALHA"):
                self.logger.error(message)
            elif lvl in ("WARNING", "AVISO"):
                self.logger.warning(message)
            else:
                self.logger.info(message)

    def _clear_log(self) -> None:
        self.log_view.clear()

    def _open_logfile(self) -> None:
        appdata = os.environ.get("APPDATA")
        log_file = Path(appdata) / "ProcessHunter" / "processhunter.log" if appdata else Path("processhunter.log")
        if log_file.exists():
            os.startfile(str(log_file))
        else:
            QMessageBox.information(self, "Log", "O arquivo de log ainda não foi criado.")

    def restore_window(self) -> None:
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def force_exit(self) -> None:
        self._is_force_exit = True
        if self.sentinel_worker.isRunning():
            self.sentinel_worker.stop()
            self.sentinel_worker.wait(1000)
        if self.tray_icon:
            self.tray_icon.hide()
        self.close()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._is_force_exit or not self.config_manager.config.minimize_to_tray_on_close:
            if self.sentinel_worker.isRunning():
                self.sentinel_worker.stop()
                self.sentinel_worker.wait(1000)
            event.accept()
            app = QApplication.instance()
            if app:
                app.quit()
        else:
            event.ignore()
            self.hide()
            if self.tray_icon:
                self.tray_icon.showMessage(
                    "ProcessHunter",
                    "ProcessHunter continua rodando em segundo plano na bandeja.",
                    HunterTrayIcon.MessageIcon.Information,
                    2000
                )
