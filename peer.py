#
# peer.py
# ~~~~~~~~~~~~~~~~~
# Mỗi peer chạy 1 instance của file này với port riêng.
# Peer tự đăng ký lên tracker, lắng nghe kết nối từ peer khác,
# và xử lý các API: /connect-peer, /send-peer, /broadcast-peer
#

import socket
import threading
import json
import argparse

from daemon import AsynapRous

# ── Cấu hình mặc định ─────────────────────────────────────────────
TRACKER_IP   = "127.0.0.1"
TRACKER_PORT = 2026

# ── State của peer này ────────────────────────────────────────────
# Danh sách các peer đã kết nối: {username: {"ip":..., "port":...}}
CONNECTED_PEERS = {}

# Lịch sử tin nhắn: [{"from": ..., "msg": ...}]
MESSAGES = []

# Thông tin peer này
MY_USERNAME = ""
MY_IP       = "127.0.0.1"
MY_PORT     = 3001

app = AsynapRous()


# ══════════════════════════════════════════════════════════════════
# Helper: gọi HTTP tới tracker hoặc peer khác
# ══════════════════════════════════════════════════════════════════

def http_post(ip, port, path, data: dict) -> dict:
    """
    Gửi HTTP POST request tới ip:port/path với body JSON.

    :param ip (str): IP đích.
    :param port (int): Port đích.
    :param path (str): URL path.
    :param data (dict): Dữ liệu gửi đi dạng JSON.
    :rtype dict: Response body được parse từ JSON.
    """
    body = json.dumps(data).encode("utf-8")
    request = (
        "POST {} HTTP/1.1\r\n"
        "Host: {}:{}\r\n"
        "Content-Type: application/json\r\n"
        "Content-Length: {}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).format(path, ip, port, len(body)).encode("utf-8") + body

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((ip, port))
        s.sendall(request)

        response = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            response += chunk
        s.close()

        # Parse response body (sau \r\n\r\n)
        if b"\r\n\r\n" in response:
            body_bytes = response.split(b"\r\n\r\n", 1)[1]
            return json.loads(body_bytes.decode("utf-8"))
    except Exception as e:
        print("[Peer] http_post error: {}".format(e))

    return {}


def http_get(ip, port, path) -> dict:
    """
    Gửi HTTP GET request tới ip:port/path.

    :param ip (str): IP đích.
    :param port (int): Port đích.
    :param path (str): URL path.
    :rtype dict: Response body được parse từ JSON.
    """
    request = (
        "GET {} HTTP/1.1\r\n"
        "Host: {}:{}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).format(path, ip, port).encode("utf-8")

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((ip, port))
        s.sendall(request)

        response = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            response += chunk
        s.close()

        if b"\r\n\r\n" in response:
            body_bytes = response.split(b"\r\n\r\n", 1)[1]
            return json.loads(body_bytes.decode("utf-8"))
    except Exception as e:
        print("[Peer] http_get error: {}".format(e))

    return {}


# ══════════════════════════════════════════════════════════════════
# Tracker interaction
# ══════════════════════════════════════════════════════════════════

def register_to_tracker():
    """Đăng ký peer này lên tracker."""
    print("[Peer] Đăng ký lên tracker {}:{}".format(TRACKER_IP, TRACKER_PORT))
    result = http_post(TRACKER_IP, TRACKER_PORT, "/submit-info", {
        "username": MY_USERNAME,
        "ip": MY_IP,
        "port": MY_PORT,
    })
    print("[Peer] Tracker response: {}".format(result))


def fetch_peer_list() -> dict:
    """Lấy danh sách peers từ tracker."""
    result = http_get(TRACKER_IP, TRACKER_PORT, "/get-list")
    return result.get("peers", {})


# ══════════════════════════════════════════════════════════════════
# API Routes của peer này
# ══════════════════════════════════════════════════════════════════

@app.route('/connect-peer', methods=['POST'])
def connect_peer(headers="guest", body="anonymous"):
    """
    Kết nối tới peer khác.
    Body: {"username": "alice"}
    Lấy IP:port của alice từ tracker rồi lưu vào CONNECTED_PEERS.
    """
    global CONNECTED_PEERS

    try:
        data = json.loads(body)
        target_username = data.get("username", "")
    except Exception:
        response_body = json.dumps({"message": "Invalid JSON"}).encode("utf-8")
        return (
            b"HTTP/1.1 400 Bad Request\r\n"
            b"Content-Type: application/json\r\n"
            + b"Content-Length: " + str(len(response_body)).encode() + b"\r\n"
            + b"\r\n" + response_body
        )

    # Lấy danh sách peers từ tracker
    peers = fetch_peer_list()

    if target_username not in peers:
        response_body = json.dumps({"message": "Peer not found: {}".format(target_username)}).encode("utf-8")
        return (
            b"HTTP/1.1 404 Not Found\r\n"
            b"Content-Type: application/json\r\n"
            + b"Content-Length: " + str(len(response_body)).encode() + b"\r\n"
            + b"\r\n" + response_body
        )

    peer_info = peers[target_username]
    CONNECTED_PEERS[target_username] = peer_info
    print("[Peer] Connected to {} at {}:{}".format(target_username, peer_info["ip"], peer_info["port"]))

    response_body = json.dumps({
        "message": "Connected to {}".format(target_username),
        "peer": peer_info
    }).encode("utf-8")
    return (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: application/json\r\n"
        + b"Content-Length: " + str(len(response_body)).encode() + b"\r\n"
        + b"\r\n" + response_body
    )


@app.route('/send-peer', methods=['POST'])
def send_peer(headers="guest", body="anonymous"):
    """
    Gửi tin nhắn tới 1 peer cụ thể.
    Body: {"to": "alice", "message": "Hello!"}
    """
    try:
        data = json.loads(body)
        to_username = data.get("to", "")
        message     = data.get("message", "")
    except Exception:
        response_body = json.dumps({"message": "Invalid JSON"}).encode("utf-8")
        return (
            b"HTTP/1.1 400 Bad Request\r\n"
            b"Content-Type: application/json\r\n"
            + b"Content-Length: " + str(len(response_body)).encode() + b"\r\n"
            + b"\r\n" + response_body
        )

    if to_username not in CONNECTED_PEERS:
        response_body = json.dumps({"message": "Not connected to {}".format(to_username)}).encode("utf-8")
        return (
            b"HTTP/1.1 404 Not Found\r\n"
            b"Content-Type: application/json\r\n"
            + b"Content-Length: " + str(len(response_body)).encode() + b"\r\n"
            + b"\r\n" + response_body
        )

    peer_info = CONNECTED_PEERS[to_username]
    result = http_post(peer_info["ip"], peer_info["port"], "/receive-msg", {
        "from": MY_USERNAME,
        "message": message,
    })
    print("[Peer] Sent to {}: {}".format(to_username, message))

    response_body = json.dumps({"message": "Sent to {}".format(to_username)}).encode("utf-8")
    return (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: application/json\r\n"
        + b"Content-Length: " + str(len(response_body)).encode() + b"\r\n"
        + b"\r\n" + response_body
    )


@app.route('/broadcast-peer', methods=['POST'])
def broadcast_peer(headers="guest", body="anonymous"):
    """
    Broadcast tin nhắn tới tất cả peers đã kết nối.
    Body: {"message": "Hello everyone!"}
    """
    try:
        data    = json.loads(body)
        message = data.get("message", "")
    except Exception:
        response_body = json.dumps({"message": "Invalid JSON"}).encode("utf-8")
        return (
            b"HTTP/1.1 400 Bad Request\r\n"
            b"Content-Type: application/json\r\n"
            + b"Content-Length: " + str(len(response_body)).encode() + b"\r\n"
            + b"\r\n" + response_body
        )

    results = {}
    for username, peer_info in CONNECTED_PEERS.items():
        result = http_post(peer_info["ip"], peer_info["port"], "/receive-msg", {
            "from": MY_USERNAME,
            "message": message,
        })
        results[username] = result
        print("[Peer] Broadcast to {}: {}".format(username, message))

    response_body = json.dumps({
        "message": "Broadcasted to {} peers".format(len(CONNECTED_PEERS)),
        "results": results
    }).encode("utf-8")
    return (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: application/json\r\n"
        + b"Content-Length: " + str(len(response_body)).encode() + b"\r\n"
        + b"\r\n" + response_body
    )


@app.route('/receive-msg', methods=['POST'])
def receive_msg(headers="guest", body="anonymous"):
    """
    Nhận tin nhắn từ peer khác.
    Body: {"from": "bob", "message": "Hello!"}
    """
    try:
        data    = json.loads(body)
        from_user = data.get("from", "unknown")
        message   = data.get("message", "")
        MESSAGES.append({"from": from_user, "message": message})
        print("[Peer] Message from {}: {}".format(from_user, message))
    except Exception as e:
        print("[Peer] receive-msg error: {}".format(e))

    response_body = json.dumps({"message": "Received"}).encode("utf-8")
    return (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: application/json\r\n"
        + b"Content-Length: " + str(len(response_body)).encode() + b"\r\n"
        + b"\r\n" + response_body
    )


@app.route('/get-messages', methods=['GET'])
def get_messages(headers="guest", body="anonymous"):
    """Trả về lịch sử tin nhắn của peer này."""
    response_body = json.dumps({"messages": MESSAGES}).encode("utf-8")
    return (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: application/json\r\n"
        + b"Content-Length: " + str(len(response_body)).encode() + b"\r\n"
        + b"\r\n" + response_body
    )


# ══════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════

def main():
    global MY_USERNAME, MY_IP, MY_PORT

    parser = argparse.ArgumentParser(description="Peer Chat Node")
    parser.add_argument("--username", required=True, help="Tên peer")
    parser.add_argument("--ip",       default="127.0.0.1")
    parser.add_argument("--port",     type=int, required=True, help="Port peer này lắng nghe")
    args = parser.parse_args()

    MY_USERNAME = args.username
    MY_IP       = args.ip
    MY_PORT     = args.port

    # Đăng ký lên tracker
    register_to_tracker()

    # Chạy peer server
    print("[Peer] {} đang lắng nghe tại {}:{}".format(MY_USERNAME, MY_IP, MY_PORT))
    app.prepare_address(MY_IP, MY_PORT)
    app.run()


if __name__ == "__main__":
    main()