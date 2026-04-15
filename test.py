import threading
import urllib.request
import urllib.error
import json
import time

URL = "http://127.0.0.1:2026/login"
NUM_REQUESTS = 10

def send_request(thread_id):
    data = json.dumps({"username": "admin", "password": "8"}).encode('utf-8')
    req = urllib.request.Request(
        URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            elapsed = time.time() - start
            print(f"[Thread {thread_id}] ✅ {resp.status} - {elapsed:.2f}s")
    except Exception as e:
        elapsed = time.time() - start
        print(f"[Thread {thread_id}] ❌ Lỗi sau {elapsed:.2f}s: {e}")

# Tạo tất cả thread cùng lúc
threads = [threading.Thread(target=send_request, args=(i,)) for i in range(NUM_REQUESTS)]

print(f"Gửi {NUM_REQUESTS} request cùng lúc...")
start_all = time.time()

# Start tất cả cùng 1 lúc
for t in threads:
    t.start()

# Chờ tất cả xong
for t in threads:
    t.join()

print(f"\nTổng thời gian: {time.time() - start_all:.2f}s")