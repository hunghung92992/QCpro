# -*- coding: utf-8 -*-
import requests
import logging

logger = logging.getLogger(__name__)


class APIClient:
    def __init__(self):
        # Tạm thời dùng một Mock API miễn phí để test việc nhận JSON
        # Sau này bạn thay bằng Domain thật: "https://api.qclab-server.com"
        self.base_url = "https://jsonplaceholder.typicode.com"

        # API Key hoặc Token để Server nhận diện phòng lab của bạn
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer YOUR_SECRET_TOKEN_HERE"
        }

    def push_sync_data(self, payload):
        """Hàm gửi cục JSON từ SyncManager lên Server"""
        endpoint = f"{self.base_url}/posts"  # Dùng /posts của JSONPlaceholder để test

        try:
            print(f"🌐 Đang kết nối tới Server: {endpoint}...")

            # Thực hiện lệnh POST gửi dữ liệu lên Cloud
            response = requests.post(endpoint, json=payload, headers=self.headers, timeout=10)

            # Nếu Server trả về mã 200, 201 (Thành công)
            if response.status_code in [200, 201]:
                print("✅ Máy chủ Cloud đã phản hồi: Đã nhận dữ liệu!")
                return True
            else:
                print(f"⚠️ Server từ chối. Mã lỗi: {response.status_code} - {response.text}")
                return False

        except requests.exceptions.RequestException as e:
            print(f"❌ Mất kết nối mạng hoặc Server sập: {e}")
            return False

    def fetch_sync_data(self) -> dict:
        print("🌐 [API] Đang kiểm tra dữ liệu mới từ Cloud...")
        return {
            "departments": [
                {
                    # Thay uuid.uuid4() bằng một ID cố định
                    "id": "mock-uuid-1234-abcd-department",
                    "code": "KHTH",
                    "name": "Kế hoạch Tổng hợp (Tải từ Cloud)",
                    "active": 1,
                    "sync_flag": 0
                }
            ]
        }

if __name__ == "__main__":
    # Test thử kết nối mạng
    client = APIClient()
    test_payload = {"message": "Hello from QCLab Desktop!"}
    client.push_sync_data(test_payload)