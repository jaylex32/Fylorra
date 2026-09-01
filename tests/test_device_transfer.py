"""Device transfer: encryption, peer identity pinning, and per-file overhead."""

from __future__ import annotations

import hashlib
import os
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

from core.device_transfer import DeviceTransferService


class _Settings:
    """Minimal settings stand-in backed by a temp folder."""

    def __init__(self, folder: Path):
        self.app_folder = Path(folder)
        self.app_folder.mkdir(parents=True, exist_ok=True)
        self._values: dict = {}

    def get_setting(self, key, default=None):
        return self._values.get(key, default)

    def set_setting(self, key, value):
        self._values[key] = value


def _sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class DeviceTransferTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="fylorra_dt_test_")
        self.root = Path(self._tmp.name)
        self._services: list[DeviceTransferService] = []

    def tearDown(self):
        for svc in self._services:
            try:
                svc.stop()
            except Exception:
                pass
        self._tmp.cleanup()

    def _service(self, name: str, *, receiving: bool = False, port: int = 0) -> DeviceTransferService:
        svc = DeviceTransferService(_Settings(self.root / name))
        inbox = self.root / (name + "_inbox")
        inbox.mkdir(parents=True, exist_ok=True)
        svc.update_config(inbox_dir=str(inbox), port=port, enabled=receiving)
        if receiving:
            svc.start()
        self._services.append(svc)
        return svc

    def _make_files(self, name: str, count: int, size: int) -> list[str]:
        folder = self.root / name
        folder.mkdir(parents=True, exist_ok=True)
        paths = []
        for i in range(count):
            p = folder / ("f%d.bin" % i)
            p.write_bytes(os.urandom(size))
            stale = time.time() - 3600
            os.utime(p, (stale, stale))
            paths.append(str(p))
        return paths

    def test_round_trip_delivers_files_intact(self):
        receiver = self._service("recv", receiving=True)
        sender = self._service("send")
        paths = self._make_files("src", 4, 64 * 1024)

        result = sender.send_paths(
            host="127.0.0.1",
            port=int(receiver.config["port"]),
            access_code=str(receiver.config["access_code"]),
            paths=paths,
        )

        self.assertEqual(result["sent"], 4)
        self.assertEqual(result["failed"], [])
        inbox = Path(receiver.config["inbox_dir"])
        for p in paths:
            self.assertEqual(_sha(inbox / Path(p).name), _sha(p))

    def test_traffic_is_encrypted_on_the_wire(self):
        """The access code and file bytes must not be readable in transit."""
        receiver = self._service("recv", receiving=True)
        self.assertTrue(receiver.status()["encrypted"], "receiver did not enable TLS")

        marker = b"FYLORRA_PLAINTEXT_CANARY"
        folder = self.root / "canary"
        folder.mkdir(parents=True, exist_ok=True)
        payload = folder / "canary.bin"
        payload.write_bytes(marker * 2048)
        stale = time.time() - 3600
        os.utime(payload, (stale, stale))

        captured = bytearray()
        target = int(receiver.config["port"])
        listener = socket.socket()
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(5)
        proxy_port = listener.getsockname()[1]

        def pump(a, b, record):
            try:
                while True:
                    chunk = a.recv(65536)
                    if not chunk:
                        break
                    if record:
                        captured.extend(chunk)
                    b.sendall(chunk)
            except Exception:
                pass
            finally:
                for sock in (a, b):
                    try:
                        sock.close()
                    except Exception:
                        pass

        def accept_loop():
            while True:
                try:
                    downstream, _ = listener.accept()
                except Exception:
                    return
                try:
                    upstream = socket.create_connection(("127.0.0.1", target))
                except Exception:
                    downstream.close()
                    continue
                threading.Thread(target=pump, args=(downstream, upstream, True), daemon=True).start()
                threading.Thread(target=pump, args=(upstream, downstream, False), daemon=True).start()

        threading.Thread(target=accept_loop, daemon=True).start()
        code = str(receiver.config["access_code"])
        try:
            sender = self._service("send")
            result = sender.send_paths(
                host="127.0.0.1", port=proxy_port, access_code=code, paths=[str(payload)]
            )
            self.assertEqual(result["sent"], 1)
        finally:
            listener.close()

        wire = bytes(captured)
        self.assertTrue(wire, "captured no traffic")
        self.assertNotIn(code.encode(), wire, "access code travelled in cleartext")
        self.assertNotIn(marker, wire, "file contents travelled in cleartext")

    def test_changed_peer_identity_is_refused_until_forgotten(self):
        original = self._service("recv_a", receiving=True)
        port = int(original.config["port"])
        sender = self._service("send")
        paths = self._make_files("src", 1, 4096)

        first = sender.send_paths(
            host="127.0.0.1",
            port=port,
            access_code=str(original.config["access_code"]),
            paths=paths,
        )
        self.assertEqual(first["sent"], 1)
        self.assertTrue(sender.peer_fingerprint("127.0.0.1", port))
        original.stop()

        # A different device answering on the same address must not be accepted.
        impostor = self._service("recv_b", receiving=True, port=port)
        blocked = sender.send_paths(
            host="127.0.0.1",
            port=port,
            access_code=str(impostor.config["access_code"]),
            paths=paths,
        )
        self.assertEqual(blocked["sent"], 0)
        self.assertTrue(blocked["failed"])

        # Forgetting the old identity is the deliberate way to accept the new one.
        sender.forget_peer_fingerprint("127.0.0.1", port)
        accepted = sender.send_paths(
            host="127.0.0.1",
            port=port,
            access_code=str(impostor.config["access_code"]),
            paths=paths,
        )
        self.assertEqual(accepted["sent"], 1)

    def test_wrong_access_code_reports_the_reason(self):
        receiver = self._service("recv", receiving=True)
        sender = self._service("send")
        # Large enough that an early rejection used to surface only as a dropped socket.
        paths = self._make_files("src", 1, 4 * 1024 * 1024)

        result = sender.send_paths(
            host="127.0.0.1",
            port=int(receiver.config["port"]),
            access_code="definitely-not-the-code",
            paths=paths,
        )
        self.assertEqual(result["sent"], 0)
        self.assertTrue(result["failed"])
        self.assertIn("access code", result["failed"][0].lower())

    def test_stability_check_does_not_stall_once_per_file(self):
        """The pre-send stability window is shared, not paid per file."""
        sender = self._service("send")
        paths = self._make_files("src", 40, 1024)
        files = sender.iter_transfer_files(paths)
        snapshot = sender._stat_snapshot(files)

        started = time.perf_counter()
        for item in files:
            self.assertTrue(sender._file_is_stable_since(item.path, snapshot))
        elapsed = time.perf_counter() - started

        # Per-file waiting would be 40 * 0.35s = 14s; a shared window is near zero.
        self.assertLess(elapsed, 3.0, "stability checks took %.2fs" % elapsed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
