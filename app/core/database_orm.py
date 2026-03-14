# -*- coding: utf-8 -*-
"""
app/core/database_orm.py
Quản lý kết nối Database Local (SQLite) và Remote (PostgreSQL).
Tự động khởi tạo Schema và dữ liệu mẫu.
"""
import logging
import os
import sqlite3
import uuid
import base64
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from PySide6.QtCore import QSettings

# 🌟 IMPORT ĐƯỜNG DẪN CHUẨN
from app.core.path_manager import PathManager
# 🌟 IMPORT BASE (Chỉ import Base để tránh Circular Import)
from app.models.base import Base

logger = logging.getLogger(__name__)

# --- 0. THIẾT LẬP ĐƯỜNG DẪN LOCAL DB ---
db_path = PathManager.get_db_path()
engine = create_engine(f"sqlite:///{db_path}")
DB_PATH = db_path
os.makedirs(os.path.dirname(db_path), exist_ok=True)

clean_path = db_path.replace('\\', '/')
SQLALCHEMY_DATABASE_URL = f"sqlite:///{clean_path}"


# --- 1. HÀM MIGRATION TỰ ĐỘNG ---
def apply_migrations(engine_obj):
    """Tự động vá tất cả các cột thiếu cho bảng audit_logs"""
    TABLE_NAME = "audit_logs"
    columns_to_add = [
        ("user_id", "TEXT"),
        ("action_type", "TEXT"),
        ("details", "TEXT"),
        ("old_value", "TEXT"),
        ("new_value", "TEXT")
    ]

    try:
        # Sử dụng begin() thay vì connect() để tự động commit trong SQLAlchemy 2.0
        with engine_obj.begin() as conn:
            check_table = conn.execute(text(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name='{TABLE_NAME}'"
            )).fetchone()

            if not check_table:
                return

            cursor = conn.execute(text(f"PRAGMA table_info({TABLE_NAME})"))
            existing_columns = [row[1] for row in cursor]

            for col_name, col_type in columns_to_add:
                if col_name not in existing_columns:
                    print(f"🔧 [Migration] Đang vá cột: '{col_name}' vào bảng '{TABLE_NAME}'...")
                    conn.execute(text(f"ALTER TABLE {TABLE_NAME} ADD COLUMN {col_name} {col_type}"))

    except Exception as e:
        logger.warning(f"⚠️ [Migration Info] {e}")


# --- 2. TỰ ĐỘNG KHỞI TẠO SCHEMA & DỮ LIỆU MẪU ---
def init_database(engine_obj):
    """
    Import toàn bộ Models và khởi tạo bảng.
    """
    try:
        # 🌟 PHẢI IMPORT ĐẦY ĐỦ Ở ĐÂY để Metadata nhận diện được TẤT CẢ các bảng
        from app.models.core_models import User, Department, AuditLog, Device, DeviceTestMap
        from app.models.catalog_models import CatalogLot, CatalogAnalyte
        from app.models.iqc_models import IQCRun, IQCResult, DeviceMessage
        from app.models.eqa_models import EQAProvider, EQAProgram, EQATask
        from app.models.sync_models import SyncState, SyncHistory

        # 1. Tạo bảng (SQLAlchemy sẽ chỉ tạo những bảng chưa tồn tại)
        Base.metadata.create_all(bind=engine_obj)

        # 2. Chạy migration vá cột
        apply_migrations(engine_obj)

        print("✅ [DB] Toàn bộ Schema (bao gồm LIS và EQA) đã được kiểm tra/khởi tạo.")

        # 3. Khởi tạo tài khoản Admin mặc định
        Session = sessionmaker(bind=engine_obj)
        with Session() as session:
            admin_user = session.query(User).filter(User.username == 'admin').first()
            if not admin_user:
                print("⚠️ [DB] Đang tạo tài khoản Admin mặc định...")
                new_admin = User()
                new_admin.id = str(uuid.uuid4())
                new_admin.username = 'admin'
                new_admin.fullname = 'Administrator'
                new_admin.role = 'SUPERADMIN'

                # Gán thuộc tính linh hoạt để tránh lỗi "invalid keyword"
                for field in ['active', 'is_active']:
                    if hasattr(new_admin, field):
                        setattr(new_admin, field, 1)

                if hasattr(new_admin, 'password_hash'):
                    new_admin.password_hash = '$2b$12$l.xjCmCVCPZmjq/W8sAgVu6eVslNGTNpri.cQQURGAuVoPvevlPxa'

                session.add(new_admin)
                session.commit()
                print("✅ [DB] Đã khởi tạo thành công tài khoản: admin / admin123")

    except Exception as e:
        logger.error(f"⚠️ [DB INIT ERROR] {e}")
        print(f"❌ [DB INIT ERROR] {e}")


# --- 3. KHỞI TẠO ENGINE VÀ SESSION CHO LOCAL DB ---
try:
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Thực hiện khởi tạo ngay
    init_database(engine)
    print(f"🚀 [DB] Kết nối Local thành công tại: {db_path}")

except Exception as e:
    logger.critical(f"❌ [DB CRITICAL] {e}")
    engine = None
    SessionLocal = sessionmaker()


# --- 4. ENGINE ĐỒNG BỘ SERVER (POSTGRESQL) ---
def get_remote_engine():
    """
    Tạo engine kết nối tới PostgreSQL để phục vụ tiến trình Đồng bộ 2 chiều.
    Lấy cấu hình trực tiếp từ QSettings do người dùng cài đặt trên UI.
    """
    settings = QSettings("NguyenHung", "QCLabManager")
    host = settings.value("db/host", "")
    port = settings.value("db/port", "5432")
    db_name = settings.value("db/dbname", "QClab")
    user = settings.value("db/user", "postgres")

    saved_pass = settings.value("db/password", "")
    pwd = ""
    if saved_pass:
        try:
            pwd = base64.b64decode(saved_pass.encode()).decode()
        except Exception:
            pass

    # Nếu chưa cài đặt Host, bỏ qua việc tạo kết nối
    if not host:
        return None

    # URL chuẩn của PostgreSQL trong SQLAlchemy
    url = f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db_name}"

    try:
        remote_engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
        return remote_engine
    except Exception as e:
        logger.error(f"Lỗi khởi tạo Remote Engine: {e}")
        return None


# --- 5. CÁC HÀM TIỆN ÍCH ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_connection():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn