# -*- coding: utf-8 -*-
"""
app/services/sync_manager.py
Orchestration: Quản lý luồng chạy ngầm (QThread) và điều phối SyncService.
Hoàn thiện Phase 2.3 (Phân vai) & Phase 4.1 (Dừng Thread an toàn).
"""
import time
import logging
from PySide6.QtCore import QThread, Signal

from app.services.sync_service import SyncService

logger = logging.getLogger(__name__)


class SyncManager(QThread):
    # Các tín hiệu (Signals) bắn ra để UI cập nhật
    sync_started = Signal()
    sync_finished = Signal(bool, str)  # (Success, Message)
    sync_progress = Signal(str)  # Log realtime cho giao diện
    sync_stats = Signal(int, int)  # (Pushed Count, Pulled Count)

    def __init__(self, parent=None, interval_seconds=30):
        super().__init__(parent)
        self.interval = interval_seconds
        self._is_running = False
        self.sync_service = SyncService()

    def run(self):
        """Vòng lặp vĩnh cửu chạy ngầm, gọi mỗi X giây."""
        self._is_running = True
        logger.info(f"🔄 [SyncManager] Thread đã khởi động (Chu kỳ {self.interval}s).")

        while self._is_running:
            self.sync_started.emit()
            self.sync_progress.emit("Đang kiểm tra kết nối API Server...")

            try:
                # 1. Thực hiện PUSH
                self.sync_progress.emit("Đang đẩy dữ liệu lên Server...")
                push_ok, push_count, push_errors = self.sync_service.push_changes()

                # 2. Thực hiện PULL
                self.sync_progress.emit("Đang lấy dữ liệu mới từ Server...")
                pull_ok, pull_count, pull_errors = self.sync_service.pull_changes()

                # Emit thống kê cho UI (VD: Vẽ biểu đồ hoặc Dashboard)
                self.sync_stats.emit(push_count, pull_count)

                # Đánh giá tổng thể
                if push_ok and pull_ok:
                    msg = f"Hoàn tất! Đẩy: {push_count} | Kéo: {pull_count}"
                    self.sync_finished.emit(True, msg)
                else:
                    err_msg = "Lỗi "
                    if not push_ok: err_msg += f"Push: {push_errors} "
                    if not pull_ok: err_msg += f"Pull: {pull_errors}"
                    self.sync_finished.emit(False, err_msg)

            except Exception as e:
                logger.error(f"❌ [SyncManager] Crash Exception: {e}")
                self.sync_finished.emit(False, f"Lỗi nghiêm trọng: {e}")

            # Nghỉ ngơi chờ chu kỳ tiếp theo (Chia nhỏ thời gian ngủ để ngắt Thread tức thời)
            for _ in range(self.interval):
                if not self._is_running:
                    break
                time.sleep(1)

        logger.info("🛑 [SyncManager] Thread đã dừng hoàn toàn.")

    def stop(self):
        """Phase 4.1: Dừng QThread an toàn chuẩn mực."""
        logger.info("⏳ [SyncManager] Nhận lệnh dừng. Đang đợi luồng đồng bộ kết thúc...")
        self._is_running = False
        self.quit()
        self.wait()  # Chặn an toàn không cho luồng chính (Main App) thoát trước