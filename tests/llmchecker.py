import os
import socket
import time
import threading
import requests
from config.conf_manager import cfg, setup_logging

setup_logging()

class LLMGatewayChecker:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.server_ip = cfg.llm_gateway.server_ip
        self.server_mac = cfg.llm_gateway.server_mac
        self.wakeup_port = cfg.llm_gateway.wakeup_port

    def _tcp_check(self):
        try:
            with socket.create_connection((self.server_ip, self.wakeup_port), timeout=1):
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            return False

    def _send_wol(self):
        print(f"[LLMGatewayChecker] AI PC unreachable, sending WOL to {self.server_mac}")
        mac_clean = self.server_mac.replace(":", "").replace("-", "")
        if len(mac_clean) != 12:
            raise ValueError(f"Invalid MAC address: {self.server_mac}")

        mac_bytes = bytes.fromhex(mac_clean)
        magic_packet = b'\xff' * 6 + mac_bytes * 16

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.sendto(magic_packet, ('<broadcast>', 9))

        print(f"[LLMGatewayChecker] Magic packet sent to {self.server_mac}")

    def _notify_wol_success(self):
        try:
            requests.post(f"http://{cfg.llm_gateway.server_ip}:{cfg.llm_gateway.port}/wol-ack", timeout=5)
            print("[LLMGatewayChecker] /tmp/wol created on AI PC.")
        except requests.RequestException as e:
            print(f"[LLMGatewayChecker] Failed to notify wol-ack: {e}")

    def _wait_for_wakeup(self):
        start_time = time.time()
        while time.time() - start_time < 60:
            if self._tcp_check():
                return True
            time.sleep(1)
        return False

    def fake_call(self):
        print(f"[LLMGatewayChecker] Sending fake call to LLM Gateway... {f"http://{cfg.llm_gateway.server_ip}:{cfg.llm_gateway.port}/health"}")
        requests.get(f"http://{cfg.llm_gateway.server_ip}:{cfg.llm_gateway.port}/health")
        return

    def request(self):
        if self._tcp_check():
            print("[LLMGatewayChecker] AI PC reachable, sending request directly...")
            return self.fake_call()

        print("[LLMGatewayChecker] AI PC unreachable, sending WOL...")
        self._send_wol()

        if not self._wait_for_wakeup():
            raise TimeoutError("AI PC not responding after WOL.")

        self._notify_wol_success()
        return self.fake_call()

llm_client = LLMGatewayChecker()
llm_client.request()
