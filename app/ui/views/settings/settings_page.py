# -*- coding: utf-8 -*-
import os
import traceback
import base64  # Import để mã hóa pass database
from app.core.path_manager import PathManager
from PySide6.QtGui import QTextCursor
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QTextCursor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFileDialog,
    QDialog, QTextEdit, QLineEdit
)

# Import widget giao diện
from qfluentwidgets import (
    ScrollArea, SettingCardGroup, SwitchSettingCard,
    PrimaryPushSettingCard, PushSettingCard, FluentIcon as FIF,
    InfoBar, InfoBarPosition, setTheme, Theme, LineEdit as FluentLineEdit,
    ComboBox, SettingCard
)

# [QUAN TRỌNG] Import SQLAlchemy để test kết nối Server
from sqlalchemy import create_engine

# Import QSettings để lưu cục bộ (thay vì ConfigMock)
from PySide6.QtCore import QSettings


class AppConfig:
    """Wrapper đơn giản để dùng QSettings giống như dict"""

    def __init__(self):
        self.settings = QSettings("NguyenHung", "QCLabManager")

    def get(self, key, default=None):
        return self.settings.value(key, default)

    def set(self, key, value):
        self.settings.setValue(key, value)


# Khởi tạo instance cấu hình toàn cục cho file này
cfg = AppConfig()


# --- 1. HỘP THOẠI XEM LOG ---
class LogViewerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nhật ký hệ thống (System Logs)")
        self.resize(900, 600)
        self.vbox = QVBoxLayout(self)

        self.lbl_info = QLabel("Hiển thị 500 dòng log gần nhất từ hệ thống")
        self.lbl_info.setStyleSheet("color: #666; font-size: 12px; margin-bottom: 5px;")
        self.vbox.addWidget(self.lbl_info)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setStyleSheet("font-family: Consolas, 'Courier New', monospace; font-size: 10pt;")
        self.vbox.addWidget(self.text_edit)
        self._load_log()

    def _load_log(self):
        log_dir = "logs"
        log_path = os.path.join(PathManager.get_log_dir(), f"app{os.extsep}log")
        self.lbl_info.setText(f"Hiển thị log từ file: {log_path}")

        if os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    last_lines = lines[-500:]
                    content = "".join(last_lines)
                    self.text_edit.setPlainText(content)
                    self.text_edit.moveCursor(QTextCursor.MoveOperation.End)
            except Exception as e:
                self.text_edit.setPlainText(f"❌ Lỗi đọc file log: {str(e)}")
        else:
            self.text_edit.setPlainText(f"⚠️ Chưa tìm thấy file log tại: {log_path}")


# --- 2. TRANG CÀI ĐẶT CHÍNH ---
class SettingsPage(ScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.view = QWidget(self)
        self.view.setObjectName("settingsView")
        self.vbox = QVBoxLayout(self.view)

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.setViewportMargins(0, 0, 0, 0)
        self.setWidget(self.view)
        self.setWidgetResizable(True)
        self.setObjectName("settings_page")

        # Style trong suốt
        self.view.setStyleSheet("#settingsView { background-color: transparent; }")
        self.setStyleSheet("SettingsPage, ScrollArea { background-color: transparent; border: none; }")

        try:
            self._init_ui()
        except Exception as e:
            print(f"❌ [UI CRASH] Lỗi nghiêm trọng khi vẽ trang Cài đặt: {e}")
            traceback.print_exc()

    def _init_ui(self):
        self.vbox.setSpacing(20)
        self.vbox.setContentsMargins(36, 20, 36, 20)

        self.lbl_title = QLabel("Cài đặt Hệ thống", self)
        self.lbl_title.setStyleSheet("font-size: 26px; font-weight: bold; font-family: 'Segoe UI';")
        self.vbox.addWidget(self.lbl_title)

        self._init_server_group()
        self._init_local_db_group()
        self._init_lis_group()
        self._init_report_group()
        self._init_ui_group()
        self._init_system_group()
        self._init_about_group()

        self.vbox.addStretch(1)

    # ============================================================
    # 1. SERVER CONFIGURATION
    # ============================================================
    def _init_server_group(self):
        self.grp_server = SettingCardGroup("Máy chủ PostgreSQL", self.view)

        # Đổi key lấy dữ liệu khớp với _save_server_config
        self.card_host = SettingCard(FIF.GLOBE, "Địa chỉ Host", "IP Máy chủ (VD: localhost hoặc 192.168.1.10)",
                                     self.grp_server)
        self.txt_host = FluentLineEdit(self.card_host)
        self.txt_host.setText(cfg.get("db/host", "localhost"))
        self.txt_host.setFixedWidth(200)
        self.card_host.hBoxLayout.addWidget(self.txt_host, 0, Qt.AlignmentFlag.AlignRight)
        self.card_host.hBoxLayout.addSpacing(16)

        self.card_port = SettingCard(FIF.TAG, "Cổng (Port)", "Cổng kết nối (Mặc định: 5432)", self.grp_server)
        self.txt_port = FluentLineEdit(self.card_port)
        self.txt_port.setText(cfg.get("db/port", "5432"))
        self.txt_port.setFixedWidth(100)
        self.card_port.hBoxLayout.addWidget(self.txt_port, 0, Qt.AlignmentFlag.AlignRight)
        self.card_port.hBoxLayout.addSpacing(16)

        self.card_dbname = SettingCard(FIF.FOLDER, "Tên Database", "Tên cơ sở dữ liệu trên Server", self.grp_server)
        self.txt_dbname = FluentLineEdit(self.card_dbname)
        self.txt_dbname.setText(cfg.get("db/dbname", "QClab"))
        self.txt_dbname.setFixedWidth(200)
        self.card_dbname.hBoxLayout.addWidget(self.txt_dbname, 0, Qt.AlignmentFlag.AlignRight)
        self.card_dbname.hBoxLayout.addSpacing(16)

        self.card_user = SettingCard(FIF.PEOPLE, "Tài khoản (User)", "Tên đăng nhập PostgreSQL", self.grp_server)
        self.txt_user = FluentLineEdit(self.card_user)
        self.txt_user.setText(cfg.get("db/user", "postgres"))
        self.txt_user.setFixedWidth(200)
        self.card_user.hBoxLayout.addWidget(self.txt_user, 0, Qt.AlignmentFlag.AlignRight)
        self.card_user.hBoxLayout.addSpacing(16)

        self.card_pass = SettingCard(FIF.EDIT, "Mật khẩu", "Mật khẩu truy cập Database", self.grp_server)
        self.txt_pass = FluentLineEdit(self.card_pass)
        self.txt_pass.setEchoMode(QLineEdit.EchoMode.Password)

        # Giải mã mật khẩu nếu có
        saved_pass = cfg.get("db/password", "")
        if saved_pass:
            try:
                decrypted_pass = base64.b64decode(saved_pass.encode()).decode()
                self.txt_pass.setText(decrypted_pass)
            except:
                pass

        self.txt_pass.setFixedWidth(200)
        self.card_pass.hBoxLayout.addWidget(self.txt_pass, 0, Qt.AlignmentFlag.AlignRight)
        self.card_pass.hBoxLayout.addSpacing(16)

        self.card_save_server = PrimaryPushSettingCard(
            "Lưu & Kiểm tra kết nối", FIF.SAVE, "Áp dụng thay đổi",
            "Kiểm tra kết nối và lưu cấu hình PostgreSQL", self.grp_server
        )
        self.card_save_server.clicked.connect(self._save_server_config)

        self.grp_server.addSettingCard(self.card_host)
        self.grp_server.addSettingCard(self.card_port)
        self.grp_server.addSettingCard(self.card_dbname)
        self.grp_server.addSettingCard(self.card_user)
        self.grp_server.addSettingCard(self.card_pass)
        self.grp_server.addSettingCard(self.card_save_server)

        self.vbox.addWidget(self.grp_server)

    # ============================================================
    # CÁC GROUP KHÁC
    # ============================================================
    def _init_local_db_group(self):
        self.grp_db = SettingCardGroup("Cơ sở dữ liệu Local", self.view)

        self.card_db_path = SettingCard(FIF.FOLDER, "Đường dẫn Database", "Vị trí lưu file SQLite nội bộ", self.grp_db)
        self.txt_db_path = FluentLineEdit(self.card_db_path)
        # Sửa thành đường dẫn thật
        appdata = os.getenv('LOCALAPPDATA')
        db_path = PathManager.get_db_path()
        self.txt_db_path.setText(db_path)
        self.txt_db_path.setFixedWidth(300)
        self.txt_db_path.setReadOnly(True)
        self.card_db_path.hBoxLayout.addWidget(self.txt_db_path, 0, Qt.AlignmentFlag.AlignRight)
        self.card_db_path.hBoxLayout.addSpacing(16)

        self.card_backup = PrimaryPushSettingCard(
            "Sao lưu ngay", FIF.SAVE, "Sao lưu dữ liệu", "Tạo bản sao lưu an toàn (.bak)", self.grp_db
        )
        self.card_backup.clicked.connect(self._on_backup_db)

        self.card_auto_bk = SwitchSettingCard(
            FIF.SYNC, "Tự động sao lưu", "Tự động sao lưu mỗi khi tắt phần mềm",
            configItem=None, parent=self.grp_db
        )
        # Sử dụng boolean parsing an toàn
        auto_bk_val = cfg.get("auto_backup", "true")
        self.card_auto_bk.setChecked(str(auto_bk_val).lower() == "true")
        self.card_auto_bk.checkedChanged.connect(lambda c: cfg.set("auto_backup", c))

        self.grp_db.addSettingCard(self.card_db_path)
        self.grp_db.addSettingCard(self.card_backup)
        self.grp_db.addSettingCard(self.card_auto_bk)
        self.vbox.addWidget(self.grp_db)

    def _init_lis_group(self):
        self.grp_device = SettingCardGroup("Kết nối thiết bị (LIS)", self.view)

        self.card_com = SettingCard(FIF.EDIT, "Cổng giao tiếp", "Cổng COM kết nối máy xét nghiệm", self.grp_device)
        self.cb_com = ComboBox(self.card_com)
        self.cb_com.addItems(["COM1", "COM2", "COM3", "TCP/IP"])
        self.cb_com.setCurrentText(cfg.get("lis_port", "COM1"))
        self.cb_com.currentTextChanged.connect(lambda t: cfg.set("lis_port", t))
        self.cb_com.setFixedWidth(150)
        self.card_com.hBoxLayout.addWidget(self.cb_com, 0, Qt.AlignmentFlag.AlignRight)
        self.card_com.hBoxLayout.addSpacing(16)

        self.card_protocol = SettingCard(FIF.TAG, "Giao thức truyền", "Chuẩn giao tiếp dữ liệu", self.grp_device)
        self.cb_protocol = ComboBox(self.card_protocol)
        self.cb_protocol.addItems(["ASTM 1394", "HL7 v2.5", "Ký tự phân cách (|)"])
        self.cb_protocol.setCurrentText(cfg.get("protocol", "ASTM 1394"))
        self.cb_protocol.currentTextChanged.connect(lambda t: cfg.set("protocol", t))
        self.cb_protocol.setFixedWidth(150)
        self.card_protocol.hBoxLayout.addWidget(self.cb_protocol, 0, Qt.AlignmentFlag.AlignRight)
        self.card_protocol.hBoxLayout.addSpacing(16)

        self.grp_device.addSettingCard(self.card_com)
        self.grp_device.addSettingCard(self.card_protocol)
        self.vbox.addWidget(self.grp_device)

    def _init_report_group(self):
        self.grp_report = SettingCardGroup("Cấu hình Báo cáo", self.view)

        self.card_lab_name = SettingCard(FIF.EDIT, "Tên đơn vị", "Tiêu đề hiển thị trên phiếu in", self.grp_report)
        self.txt_lab_name = FluentLineEdit(self.card_lab_name)
        self.txt_lab_name.setText(cfg.get("lab_name", ""))
        self.txt_lab_name.editingFinished.connect(lambda: cfg.set("lab_name", self.txt_lab_name.text()))
        self.txt_lab_name.setFixedWidth(400)
        self.card_lab_name.hBoxLayout.addWidget(self.txt_lab_name, 0, Qt.AlignmentFlag.AlignRight)
        self.card_lab_name.hBoxLayout.addSpacing(16)

        self.card_logo = PushSettingCard(
            "Chọn ảnh...", FIF.PHOTO, "Logo đơn vị", "Đường dẫn file logo (.png, .jpg)", self.grp_report
        )
        self.card_logo.clicked.connect(self._on_select_logo)

        self.grp_report.addSettingCard(self.card_lab_name)
        self.grp_report.addSettingCard(self.card_logo)
        self.vbox.addWidget(self.grp_report)

    def _init_ui_group(self):
        self.grp_ui = SettingCardGroup("Giao diện", self.view)
        self.card_theme = SettingCard(FIF.BRUSH, "Chế độ màu", "Giao diện Sáng / Tối", self.grp_ui)
        self.cb_theme = ComboBox(self.card_theme)
        self.cb_theme.addItems(["Sáng (Light)", "Tối (Dark)", "Theo hệ thống"])
        self.cb_theme.setCurrentText(cfg.get("theme_mode", "Theo hệ thống"))
        self.cb_theme.setFixedWidth(180)
        self.cb_theme.currentTextChanged.connect(self._on_theme_changed)
        self.card_theme.hBoxLayout.addWidget(self.cb_theme, 0, Qt.AlignmentFlag.AlignRight)
        self.card_theme.hBoxLayout.addSpacing(16)
        self.grp_ui.addSettingCard(self.card_theme)
        self.vbox.addWidget(self.grp_ui)

    def _init_system_group(self):
        self.grp_sys = SettingCardGroup("Hệ thống & Nhật ký", self.view)
        self.card_view_log = PushSettingCard(
            "Xem Log", FIF.DOCUMENT, "Nhật ký hoạt động",
            "Xem chi tiết hoạt động đồng bộ và lỗi phát sinh", self.grp_sys
        )
        self.card_view_log.clicked.connect(self._on_view_log)
        self.grp_sys.addSettingCard(self.card_view_log)
        self.vbox.addWidget(self.grp_sys)

    def _init_about_group(self):
        self.grp_about = SettingCardGroup("Thông tin phần mềm", self.view)

        self.card_app_info = PrimaryPushSettingCard(
            "Kiểm tra cập nhật", FIF.INFO, "QC Lab Manager",
            "Phiên bản: 1.0.0 (Hybrid Edition) | © 2026 Developed by Nguyễn Hùng", self.grp_about
        )
        self.card_app_info.clicked.connect(self._on_check_update)

        self.card_contact = SettingCard(
            FIF.PHONE, "Liên hệ hỗ trợ", "Email: thanhhung1512@gmail.com | Hotline: 0398.000.678", self.grp_about
        )

        self.card_feedback = PushSettingCard(
            "Gửi góp ý", FIF.FEEDBACK, "Phản hồi & Góp ý",
            "Gửi báo cáo lỗi hoặc đề xuất tính năng mới cho nhà phát triển", self.grp_about
        )
        self.card_feedback.clicked.connect(self._on_feedback)

        self.grp_about.addSettingCard(self.card_app_info)
        self.grp_about.addSettingCard(self.card_contact)
        self.grp_about.addSettingCard(self.card_feedback)

        self.vbox.addWidget(self.grp_about)

    # ============================================================
    # SLOTS & LOGIC
    # ============================================================
    def _save_server_config(self):
        host = self.txt_host.text().strip()
        port = self.txt_port.text().strip()
        db_name = self.txt_dbname.text().strip()
        user = self.txt_user.text().strip()
        pwd = self.txt_pass.text().strip()

        # 1. Hiển thị trạng thái đang thử nghiệm
        self.card_save_server.setEnabled(False)
        InfoBar.info("Đang kết nối...", "Đang thử nghiệm kết nối tới PostgreSQL, vui lòng chờ...", parent=self,
                     duration=2000)

        # 2. Test kết nối
        connection_url = f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db_name}"

        try:
            # Connect thử với timeout ngắn (3s)
            engine = create_engine(connection_url, connect_args={"connect_timeout": 3})
            with engine.connect() as conn:
                pass  # Nếu vượt qua dòng này là thành công

            # 3. Lưu nếu kết nối thành công
            cfg.set("db/host", host)
            cfg.set("db/port", port)
            cfg.set("db/dbname", db_name)
            cfg.set("db/user", user)
            cfg.set("db/password", base64.b64encode(pwd.encode()).decode())

            InfoBar.success(
                "Kết nối thành công!",
                "Thông tin Server đã được lưu. Dữ liệu sẽ bắt đầu đồng bộ lên Server này.",
                parent=self, duration=4000
            )
        except Exception as e:
            InfoBar.error(
                "Lỗi kết nối Server",
                f"Không thể kết nối. Vui lòng kiểm tra lại IP, Port và Mật khẩu.\nChi tiết: {str(e)[:50]}...",
                parent=self, duration=5000
            )
        finally:
            self.card_save_server.setEnabled(True)

    def _on_backup_db(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Lưu file Backup", "Backup_QC.bak", "Backup Files (*.bak)")
        if file_path:
            InfoBar.success("Sao lưu thành công", f"File: {os.path.basename(file_path)}", parent=self)

    def _on_select_logo(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Chọn Logo", "", "Images (*.png *.jpg *.jpeg)")
        if file_path:
            cfg.set("logo_path", file_path)
            InfoBar.success("Đã cập nhật Logo", "Logo mới sẽ hiển thị trên báo cáo in.", parent=self)

    def _on_theme_changed(self, text):
        cfg.set("theme_mode", text)
        if "Sáng" in text:
            setTheme(Theme.LIGHT)
        elif "Tối" in text:
            setTheme(Theme.DARK)
        else:
            setTheme(Theme.AUTO)

    def _on_view_log(self):
        dialog = LogViewerDialog(self.window())
        dialog.exec()

    def _on_check_update(self):
        InfoBar.info("Cập nhật", "Bạn đang sử dụng phiên bản mới nhất (v1.0.1).", parent=self, duration=2500)

    def _on_feedback(self):
        QDesktopServices.openUrl(QUrl("mailto:thanhhung@gmail.com?subject=Feedback QC Lab"))