# -*- coding: utf-8 -*-
"""
main.py (Win 11 Fluent Version)
M6 FINALIZED: Integrated LIS Workers, Parsers, Auto-Services, Bootstrap & Compiled Resources
"""
import sys
import os
import traceback
import ctypes
import datetime as dt
from PySide6.QtCore import Qt

# [PHASE 4.2 KHẮC PHỤC LỖI ICON] Nạp file resources đã được biên dịch từ resources.qrc
try:
    import app.resources_rc
except ImportError:
    print("⚠️ Cảnh báo: Chưa tìm thấy file app/resources_rc.py.")
    print("👉 Hãy chạy lệnh: pyside6-rcc resources.qrc -o app/resources_rc.py")

# Ngắt các cảnh báo rác của Qt (Không cần chặn qt.svg nữa vì resource đã được compile chuẩn)
os.environ["QT_LOGGING_RULES"] = "qt.qpa.drawing=false"

# 1. IMPORT THEO CẤU TRÚC PATH MANAGER MỚI (Khắc phục lỗi ImportError)
from app.core.path_manager import PathManager
from app.core.logger import setup_logger
from app.core.backup_manager import perform_backup

# Khởi tạo thư mục và Logger
PathManager.ensure_structure()
logger = setup_logger()

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QIcon
from qfluentwidgets import setTheme, Theme

# Khai báo App ID để Windows không gom nhóm Icon (Taskbar Fix)
try:
    myappid = 'nguyenhung.qclabmanager.pro.1.0.1'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass


def resource_path(relative_path):
    """ Lấy đường dẫn tuyệt đối cho assets (logo, v.v.) """
    # 2. CẬP NHẬT CÁCH GỌI get_project_root()
    base_path = str(PathManager.get_project_root())
    return os.path.join(base_path, relative_path)


def exception_hook(exctype, value, tb):
    """ Bắt lỗi crash toàn cục và ghi log """
    error_msg = "".join(traceback.format_exception(exctype, value, tb))
    logger.critical(f"CRITICAL ERROR: {value}\n{error_msg}")

    if QApplication.instance():
        QMessageBox.critical(None, "Lỗi Hệ Thống", f"Ứng dụng đã dừng đột ngột:\n{value}")
    sys.exit(1)


def main():
    sys.excepthook = exception_hook

    # Cấu hình DPI cho màn hình độ phân giải cao
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("QC Lab Manager")

    # Nạp Icon ứng dụng từ assets (Logo App không nhất thiết phải cho vào qrc)
    app_icon_path = resource_path(os.path.join("app", "assets", "logo.ico"))
    app.setWindowIcon(QIcon(app_icon_path))

    # Áp dụng Fluent Theme
    setTheme(Theme.AUTO)

    # --- PHẦN IMPORT TRỄ (Lazy Import) ---
    from app.ui.views.auth.login_page import FluentLoginWindow
    from app.ui.main_window import MainWindowFluent

    # Import các Service lõi của LIS M6
    from app.services.iqc_service import IQCService
    from app.services.device_service import DeviceService
    from app.integration.device_worker_service import DeviceWorkerService
    from app.integration.parsers.lis_parser_service import LisParserService

    # 3. GỌI BOOTSTRAP TẠO DB/SEED DỮ LIỆU (Hoàn thiện Phase 1.3)
    from app.core.bootstrap import run_bootstrap
    try:
        run_bootstrap()
    except Exception as e:
        logger.error(f"Bootstrap failed: {e}")
        QMessageBox.critical(None, "Lỗi Database", "Không thể khởi tạo cơ sở dữ liệu.")
        return 1

    # 4. Khởi tạo Login và Quản lý Service
    login_window = FluentLoginWindow()
    windows = {"main": None}

    lis_services = {
        "worker_manager": None,
        "parser_manager": None
    }

    def show_main_window(user_data):
        try:
            # A. Khởi tạo Giao diện chính
            mw = MainWindowFluent(user_data)
            windows["main"] = mw
            mw.show()

            # 5. FIX LỖI THOÁT APP: Dùng .hide() thay vì .close()
            login_window.hide()

            # B. Kích hoạt Hệ thống LIS M6
            logger.info("🤖 Đang khởi động hệ thống tự động hóa LIS...")

            try:
                # Khởi tạo các Service phụ thuộc
                iqc_svc = IQCService()
                dev_svc = DeviceService()

                # Chạy LisParser
                parser = LisParserService(iqc_svc, dev_svc)
                parser.start(poll_interval=10)
                lis_services["parser_manager"] = parser

                # Chạy DeviceWorkers
                worker_manager = DeviceWorkerService(dev_svc)
                worker_manager.start_workers()
                lis_services["worker_manager"] = worker_manager

                logger.info("✅ LIS Workers & Parser đã sẵn sàng!")

            except Exception as lis_err:
                logger.error(f"LIS Startup Error: {lis_err}")

        except Exception as e:
            logger.error(f"Main Window Init Error: {e}")
            QMessageBox.critical(None, "Lỗi Giao Diện", f"Không thể mở trang chủ: {e}")

    login_window.loginSuccess.connect(show_main_window)
    login_window.show()

    # --- THỰC THI BIẾN BIẾN ---
    exit_code = app.exec()

    # --- DỌN DẸP KHI THOÁT ---
    try:
        logger.info("Đang dừng các dịch vụ LIS...")
        if lis_services["worker_manager"]:
            lis_services["worker_manager"].stop_workers()

        if lis_services["parser_manager"]:
            lis_services["parser_manager"].stop()

        logger.info("Ứng dụng đang đóng... Bắt đầu tiến trình Auto-Backup.")
        perform_backup()
    except Exception as e:
        logger.error(f"Cleanup/Backup failed during exit: {e}")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()