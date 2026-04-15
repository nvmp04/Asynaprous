#
# Copyright (C) 2026 pdnguyen of HCMC University of Technology VNU-HCM.
# All rights reserved.
# This file is part of the CO3093/CO3094 course,
# and is released under the "MIT License Agreement". Please see the LICENSE
# file that should have been included as part of this package.
#
# AsynapRous release
#
# The authors hereby grant to Licensee personal permission to use
# and modify the Licensed Source Code for the sole purpose of studying
# while attending the course
#


"""
app.sampleapp
~~~~~~~~~~~~~~~~~

"""

import sys
import os
import importlib.util
import json
import time
import uuid
from   daemon import AsynapRous
import socket as _socket

app = AsynapRous()

SESSIONS = {}

@app.route("/echo", methods=["POST"])
def echo(headers="guest", body="anonymous"):
    print("[SampleApp] received body {}".format(body))

    try:
        message = json.loads(body)
        data = {"received": message }
        # Convert to JSON string
        json_str = json.dumps(data)
        return (json_str.encode("utf-8"))
    except json.JSONDecodeError:
        data = {"error": "Invalid JSON"}
        # Convert to JSON string
        json_str = json.dumps(data)
        return (json_str.encode("utf-8"))

@app.route('/protected', methods=['GET'])
def protected(headers="guest", body="anonymous"):
    """Route bảo vệ bằng cookie session."""
    # Lấy cookie từ headers
    cookie_header = headers.get('cookie', '') if isinstance(headers, dict) else ''
    cookies = {}
    for pair in cookie_header.split(';'):
        pair = pair.strip()
        if '=' in pair:
            k, v = pair.split('=', 1)
            cookies[k.strip()] = v.strip()

    session_id = cookies.get('session_id', '')

    if session_id not in SESSIONS:
        response_body = json.dumps({"message": "Unauthorized - please login first"}).encode("utf-8")
        return (
            b"HTTP/1.1 401 Unauthorized\r\n"
            b"Content-Type: application/json\r\n"
            + b"Content-Length: " + str(len(response_body)).encode() + b"\r\n"
            + b"\r\n"
            + response_body
        )

    username = SESSIONS[session_id]
    response_body = json.dumps({"message": "Welcome {}! You are authenticated.".format(username)}).encode("utf-8")
    return (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: application/json\r\n"
        + b"Content-Length: " + str(len(response_body)).encode() + b"\r\n"
        + b"\r\n"
        + response_body
    )
@app.route('/hello', methods=['PUT'])
async def hello(headers, body):
    """
    Handle greeting via PUT request.

    This route prints a greeting message to the console using the provided headers
    and body.

    :param headers (str): The request headers or user identifier.
    :param body (str): The request body or message payload.
    """
    print("[SampleApp] ['PUT'] **ASYNC** Hello in {} to {}".format(headers, body))
    data =  {"id": 1, "name": "Alice", "email": "alice@example.com"}

    # Convert to JSON string
    json_str = json.dumps(data)
    return (json_str.encode("utf-8"))

  

PEERS           = {}  # {username: {"ip":..., "port":...}} — chỉ tracker dùng
CONNECTED_PEERS = {}  # {username: {"ip":..., "port":...}} — peer dùng
CHANNELS        = {}  # {"user1:user2": [{"from":..., "message":...}]}

TRACKER_IP   = "127.0.0.1"
TRACKER_PORT = 2026
VALID_USERS = {
    "admin": "password",
    "user1": "password",
    "user2": "password",
    "user3": "password",
}
def get_current_user(headers):
    cookie_header = headers.get('cookie', '') if isinstance(headers, dict) else ''
    cookies_raw = []
    for pair in cookie_header.split(';'):
        pair = pair.strip()
        if '=' in pair:
            k, v = pair.split('=', 1)
            if k.strip() == 'session_id':
                cookies_raw.append(v.strip())
    
    print("[Debug] session_ids found: {}".format(cookies_raw))
    print("[Debug] SESSIONS: {}".format(SESSIONS))
    
    for session_id in cookies_raw:
        user = SESSIONS.get(session_id)
        if user:
            return user
    return None


def channel_key(user_a, user_b):
    """Key channel nhất quán cho 2 user."""
    return ":".join(sorted([user_a, user_b]))


def http_post(ip, port, path, data):
    """Gửi HTTP POST tới peer khác."""
    print("[http_post] Gửi tới {}:{}{} data={}".format(ip, port, path, data))
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
        s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        s.settimeout(5)
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
            return json.loads(response.split(b"\r\n\r\n", 1)[1].decode("utf-8"))
    except Exception as e:
        print("[Peer] http_post error: {}".format(e))
    return {}


def http_get(ip, port, path):
    """Gửi HTTP GET tới tracker."""
    request = (
        "GET {} HTTP/1.1\r\n"
        "Host: {}:{}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).format(path, ip, port).encode("utf-8")
    try:
        s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        s.settimeout(5)
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
            return json.loads(response.split(b"\r\n\r\n", 1)[1].decode("utf-8"))
    except Exception as e:
        print("[Peer] http_get error: {}".format(e))
    return {}

def make_response(status, body_dict):
    """Helper tạo HTTP response chuẩn."""
    body = json.dumps(body_dict).encode("utf-8")
    status_text = {
        200: "OK",
        400: "Bad Request",
        401: "Unauthorized",
        404: "Not Found",
        500: "Internal Server Error"
    }.get(status, "OK")
    return (
        "HTTP/1.1 {} {}\r\n".format(status, status_text).encode() +
        b"Content-Type: application/json\r\n" +
        b"Content-Length: " + str(len(body)).encode() + b"\r\n" +
        b"\r\n" + body
    )

@app.route('/login', methods=['POST'])
def login(headers="guest", body="anonymous"):
    """Đăng nhập, trả về cookie session."""
    try:
        data = json.loads(body)
        username = data.get("username", "")
        password = data.get("password", "")
    except Exception:
        username, password = "", ""
        for pair in body.strip().split('&'):
            if '=' in pair:
                k, v = pair.split('=', 1)
                if k == 'username': username = v
                if k == 'password': password = v

    if VALID_USERS.get(username) != password:
        return make_response(401, {"message": "Invalid credentials"})

    session_id = uuid.uuid4().hex
    SESSIONS[session_id] = username
    print("[App] Login OK - user={}".format(username))

    body_bytes = json.dumps({"message": "Login successful", "username": username}).encode("utf-8")
    return (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: application/json\r\n"
        + b"Set-Cookie: session_id=" + session_id.encode() + b"; HttpOnly; Path=/\r\n"
        + b"Content-Length: " + str(len(body_bytes)).encode() + b"\r\n"
        + b"\r\n" + body_bytes
    )


@app.route('/submit-info', methods=['POST'])
def submit_info(headers="guest", body="anonymous"):
    """Peer đăng ký IP:port lên tracker."""
    try:
        data = json.loads(body)
        username = data.get("username", "")
        ip = data.get("ip", "")
        port = data.get("port", 0)
        PEERS[username] = {"ip": ip, "port": port}
        print("[App] Registered: {} at {}:{}".format(username, ip, port))
        return make_response(200, {"message": "Registered successfully"})
    except Exception as e:
        return make_response(500, {"message": str(e)})


@app.route('/get-list', methods=['GET'])
def get_list(headers="guest", body="anonymous"):
    """Trả về danh sách peers."""
    return make_response(200, {"peers": PEERS})


@app.route('/connect-peer', methods=['POST'])
def connect_peer(headers="guest", body="anonymous"):
    """
    Kết nối tới peer khác.
    Body: {"username": "user2"}
    """
    current_user = get_current_user(headers)
    if not current_user:
        return make_response(401, {"message": "Unauthorized"})

    try:
        data = json.loads(body)
        target = data.get("username", "")
    except Exception:
        return make_response(400, {"message": "Invalid JSON"})

    # Lấy danh sách từ tracker
    result = http_get(TRACKER_IP, TRACKER_PORT, "/get-list")
    peers = result.get("peers", {})

    if target not in peers:
        return make_response(404, {"message": "Peer not found: {}".format(target)})

    CONNECTED_PEERS[target] = peers[target]

    # Tạo channel
    key = channel_key(current_user, target)
    if key not in CHANNELS:
        CHANNELS[key] = []

    print("[App] {} connected to {} — channel: {}".format(current_user, target, key))
    return make_response(200, {"message": "Connected to {}".format(target), "channel": key})


@app.route('/send-peer', methods=['POST'])
def send_peer(headers="guest", body="anonymous"):
    """
    Gửi tin nhắn tới 1 peer.
    Body: {"to": "user2", "message": "Hello!"}
    """
    current_user = get_current_user(headers)
    if not current_user:
        return make_response(401, {"message": "Unauthorized"})

    try:
        data = json.loads(body)
        to_user = data.get("to", "")
        message = data.get("message", "")
    except Exception:
        return make_response(400, {"message": "Invalid JSON"})

    if to_user not in CONNECTED_PEERS:
        return make_response(404, {"message": "Not connected to {}".format(to_user)})

    peer = CONNECTED_PEERS[to_user]

    # Gửi tới peer kia
    http_post(peer["ip"], peer["port"], "/receive-msg", {
        "from": current_user,
        "to": to_user,
        "message": message
    })

    # Lưu vào channel của peer này
    key = channel_key(current_user, to_user)
    if key not in CHANNELS:
        CHANNELS[key] = []
    CHANNELS[key].append({"from": current_user, "message": message})

    print("[App] {} → {}: {}".format(current_user, to_user, message))
    return make_response(200, {"message": "Sent to {}".format(to_user)})


@app.route('/broadcast-peer', methods=['POST'])
def broadcast_peer(headers="guest", body="anonymous"):
    """
    Broadcast tới tất cả peers đã kết nối.
    Body: {"message": "Hello everyone!"}
    """
    current_user = get_current_user(headers)
    if not current_user:
        return make_response(401, {"message": "Unauthorized"})

    try:
        data = json.loads(body)
        message = data.get("message", "")
    except Exception:
        return make_response(400, {"message": "Invalid JSON"})

    for username, peer in CONNECTED_PEERS.items():
        http_post(peer["ip"], peer["port"], "/receive-msg", {
            "from": current_user,
            "to": username,
            "message": message
        })
        key = channel_key(current_user, username)
        if key not in CHANNELS:
            CHANNELS[key] = []
        CHANNELS[key].append({"from": current_user, "message": message})
        print("[App] Broadcast {} → {}: {}".format(current_user, username, message))

    return make_response(200, {"message": "Broadcasted to {} peers".format(len(CONNECTED_PEERS))})


@app.route('/receive-msg', methods=['POST'])
def receive_msg(headers="guest", body="anonymous"):
    """Nhận tin nhắn từ peer khác — được gọi bởi peer gửi."""
    try:
        data = json.loads(body)
        from_user = data.get("from", "unknown")
        to_user   = data.get("to", "")
        message   = data.get("message", "")

        key = channel_key(from_user, to_user)
        if key not in CHANNELS:
            CHANNELS[key] = []
        CHANNELS[key].append({"from": from_user, "message": message})
        print("[App] Received {} → {}: {}".format(from_user, to_user, message))
    except Exception as e:
        print("[App] receive-msg error: {}".format(e))

    return make_response(200, {"message": "Received"})


@app.route('/get-channels', methods=['GET'])
def get_channels(headers="guest", body="anonymous"):
    """Lấy danh sách channels của user hiện tại."""
    current_user = get_current_user(headers)
    if not current_user:
        return make_response(401, {"message": "Unauthorized"})

    my_channels = [key for key in CHANNELS if current_user in key.split(":")]
    return make_response(200, {"channels": my_channels})


@app.route('/get-messages', methods=['POST'])
def get_messages(headers="guest", body="anonymous"):
    """
    Lấy tin nhắn của 1 channel.
    Body: {"with": "user2"}
    """
    current_user = get_current_user(headers)
    if not current_user:
        return make_response(401, {"message": "Unauthorized"})

    try:
        data = json.loads(body)
        with_user = data.get("with", "")
    except Exception:
        return make_response(400, {"message": "Invalid JSON"})

    key = channel_key(current_user, with_user)
    messages = CHANNELS.get(key, [])
    return make_response(200, {"channel": key, "messages": messages})


def create_sampleapp(ip, port):
    app.prepare_address(ip, port)
    app.run()