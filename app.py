from __future__ import annotations
import argparse
import sys
from pathlib import Path
from PySide6.QtCore import QDir, QLockFile
from PySide6.QtWidgets import QApplication, QMessageBox

from core.config import ConfigManager
from core.hunter import ProcessHunter
from core.autostart import WindowsAutostart
from core.logger import setup_app_logger
from ui.tray import HunterTrayIcon
from ui.main_window import MainWindow
from ui.theme import apply_dark_theme


def main() -> int:
    parser = argparse.ArgumentParser(description="ProcessHunter GUI")
    parser.add_argument("--minimized", action="store_true", help="Inicia minimizado na bandeja do sistema")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    apply_dark_theme(app)

    # 1. Single Instance Lock
    lock_path = Path(QDir.tempPath()) / "processhunter_instance.lock"
    lock_file = QLockFile(str(lock_path))
    lock_file.setStaleLockTime(5000)

    if not lock_file.tryLock(100):
        print("Já existe uma instância do ProcessHunter em execução.")
        if not args.minimized:
            # Show friendly message
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setWindowTitle("ProcessHunter")
            msg.setText("O ProcessHunter já está em execução no sistema (verifique a bandeja/System Tray ao lado do relógio).")
            msg.exec()
        return 0

    try:
        # 2. Core services initialization
        logger, _ = setup_app_logger()
        logger.info("Iniciando ProcessHunter GUI...")

        config_manager = ConfigManager()
        config_manager.load()

        hunter = ProcessHunter()
        autostart = WindowsAutostart(app_name="ProcessHunter")

        # 3. UI setup
        tray_icon = HunterTrayIcon()
        main_window = MainWindow(
            config_manager=config_manager,
            hunter=hunter,
            autostart=autostart,
            tray_icon=tray_icon,
            logger=logger
        )

        tray_icon.show()

        # 4. Show or start minimized
        if args.minimized:
            logger.info("ProcessHunter iniciado minimizado com o Windows.")
            # Automatically activate sentinel on Windows boot
            main_window.toggle_sentinel()
            if config_manager.config.notify_on_kill:
                tray_icon.showMessage(
                    "ProcessHunter",
                    "ProcessHunter iniciado e monitorando em segundo plano.",
                    HunterTrayIcon.MessageIcon.Information,
                    2000
                )
        else:
            main_window.show()

        return app.exec()
    finally:
        lock_file.unlock()


if __name__ == "__main__":
    sys.exit(main())
