# -*- coding: utf-8 -*-
"""
app/services/sync_service.py
Service đảm nhiệm logic đồng bộ qua REST API.
Kế thừa tinh hoa Incremental Pull, Versioning và Ghost Cleaning của bản cũ.
"""
import datetime
import json
import requests
import logging
from app.core.path_manager import PathManager
from app.core.database_orm import SessionLocal

# Import các Models chính
from app.models.catalog_models import CatalogLot, CatalogAnalyte
from app.models.iqc_models import IQCRun, IQCResult
# Import Model đồng bộ
from app.models.sync_models import SyncState
from app.models.core_models import Department, User, AuditLog

logger = logging.getLogger(__name__)


class SyncService:
    def __init__(self):
        self.device_id = "device_local_temp_01"
        self._load_config()

        # Ánh xạ tên bảng API với Model Local (Theo chuẩn v2 của bạn)
        self.model_mapping = {
            "department_v2": Department,
            "users_v2": User,
            "catalog_lot_v2": CatalogLot,
            "catalog_analyte_v2": CatalogAnalyte,
            "iqc_run_v2": IQCRun,
            "iqc_result_v2": IQCResult,
            "audit_log_v2": AuditLog
        }

    def _load_config(self):
        """Đọc URL API và Token từ config.json"""
        self.api_base_url = "http://localhost:8000/api/v1"
        self.api_token = "YOUR_SECURE_TOKEN_HERE"
        self.timeout = 10

        try:
            config_path = PathManager.get_config_path()
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                server_cfg = config.get("server", {})
                self.api_base_url = server_cfg.get("api_url", self.api_base_url)
                self.api_token = server_cfg.get("api_token", self.api_token)
        except Exception:
            pass

    def _get_headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_token}",
            "X-Device-ID": self.device_id
        }

    def _record_to_dict(self, record):
        """Chuyển SQLAlchemy Object thành Dictionary để dump JSON"""
        d = {}
        for column in record.__table__.columns:
            val = getattr(record, column.name)
            # Ép kiểu datetime sang chuỗi ISO 8601 để gửi API
            if isinstance(val, (datetime.date, datetime.datetime)):
                val = val.isoformat()
            d[column.name] = val
        return d

    # --- 1. PUSH (ĐẨY LÊN API) ---
    def push_changes(self):
        """Gom dữ liệu sync_flag != 0 đóng gói JSON đẩy lên API Server"""
        local_session = SessionLocal()
        total_pushed = 0
        errors = []
        payload = {}

        try:
            # Thu thập dữ liệu
            for table_name, model_class in self.model_mapping.items():
                pending = local_session.query(model_class).filter(model_class.sync_flag != 0).all()
                if pending:
                    payload[table_name] = [self._record_to_dict(r) for r in pending]
                    total_pushed += len(pending)

            if not payload:
                return True, 0, []

            logger.info(f"⬆️ [PUSH] Đang đẩy {total_pushed} bản ghi lên API...")

            # GỌI API THẬT (Khi nào có Backend thì mở comment đoạn này)
            """
            endpoint = f"{self.api_base_url}/sync/push"
            response = requests.post(endpoint, json=payload, headers=self._get_headers(), timeout=self.timeout)
            response.raise_for_status()

            # Lấy danh sách ID đã push thành công từ Server trả về để hạ cờ
            # response_data = response.json()
            # success_ids = response_data.get("success_ids", {})
            """

            # (Giả lập) Hạ cờ toàn bộ sau khi Push thành công
            for table_name, model_class in self.model_mapping.items():
                local_session.query(model_class).filter(model_class.sync_flag != 0).update({"sync_flag": 0})

            local_session.commit()
            return True, total_pushed, errors

        except Exception as e:
            local_session.rollback()
            logger.error(f"❌ [PUSH ERROR] {e}")
            return False, 0, [str(e)]
        finally:
            local_session.close()

    # --- 2. PULL (KÉO TỪ API - INCREMENTAL) ---
    def pull_changes(self):
        """Chỉ kéo dữ liệu thay đổi từ Server dựa trên mốc SyncState"""
        local_session = SessionLocal()
        total_pulled = 0
        errors = []

        try:
            for table_name, model_class in self.model_mapping.items():
                # Lấy mốc thời gian Pull cuối cùng (Có lọc thêm device_id)
                state = local_session.query(SyncState).filter_by(
                    table_name=table_name,
                    device_id=self.device_id
                ).first()

                if not state:
                    state = SyncState(
                        device_id=self.device_id,
                        table_name=table_name,
                        last_pull_time=datetime.datetime(2000, 1, 1)
                    )
                    local_session.add(state)

                last_pull_str = state.last_pull_time.isoformat()
                current_pull_start = datetime.datetime.utcnow()

                # GỌI API THẬT
                """
                endpoint = f"{self.api_base_url}/sync/pull"
                params = {"table": table_name, "since": last_pull_str}
                response = requests.get(endpoint, headers=self._get_headers(), params=params, timeout=self.timeout)
                response.raise_for_status()
                server_records = response.json().get("data", [])
                """

                server_records = []  # Giả lập rỗng khi chưa có backend

                if server_records:
                    valid_columns = [c.key for c in model_class.__table__.columns]

                    for data in server_records:
                        filtered_data = {k: v for k, v in data.items() if k in valid_columns}
                        filtered_data['sync_flag'] = 0

                        is_deleted = int(data.get('is_deleted', 0))

                        existing = local_session.query(model_class).filter_by(id=data['id']).first()

                        if is_deleted == 1:
                            if existing: local_session.delete(existing)
                        else:
                            if existing:
                                for k, v in filtered_data.items(): setattr(existing, k, v)
                            else:
                                local_session.add(model_class(**filtered_data))

                        total_pulled += 1

                # Cập nhật mốc thời gian
                state.last_pull_time = current_pull_start

            local_session.commit()
            return True, total_pulled, errors

        except Exception as e:
            local_session.rollback()
            logger.error(f"❌ [PULL ERROR] {e}")
            return False, 0, [str(e)]
        finally:
            local_session.close()

    # --- 3. FORCE RESYNC (ÉP TẢI LẠI TOÀN BỘ) ---
    def force_resync_all(self):
        """Xóa mốc SyncState để tải lại toàn bộ từ Server"""
        local_session = SessionLocal()
        try:
            logger.info("🔄 [RESET] Đang xóa mốc đồng bộ để Force Resync...")
            # Chỉ xóa mốc của thiết bị hiện tại
            local_session.query(SyncState).filter_by(device_id=self.device_id).delete()
            local_session.commit()
            return self.pull_changes()
        except Exception as e:
            local_session.rollback()
            return False, 0, [str(e)]
        finally:
            local_session.close()