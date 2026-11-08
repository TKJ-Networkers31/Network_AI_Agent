"""
core/ui.py — util tampilan terminal untuk run_chat.py (mode testing).

Port ringan dari agent/core/ui.py::Timer (sistem lama), disederhanakan.
Tujuannya cuma satu: supaya user TAHU AIRA sedang bekerja (bukan diam
total) selama Brain.think() berjalan, lengkap dengan durasi live -
karena tool network (SSH/SNMP) bisa butuh puluhan detik kalau timeout.
"""

import sys
import time
import threading


class Timer:

    _FRAMES = ["|", "/", "-", "\\"]

    def __init__(self, label="Bekerja"):
        self.label = label
        self.running = False
        self.start_time = 0.0
        self.thread = None

    def start(self):
        self.running = True
        self.start_time = time.perf_counter()
        self.thread = threading.Thread(target=self._animate, daemon=True)
        self.thread.start()

    def stop(self, final_label=None):
        self.running = False

        if self.thread:
            self.thread.join(timeout=0.3)

        elapsed = self.elapsed()
        label = final_label or self.label

        self._clear_line()
        print(f"  [{label}] selesai dalam {elapsed:.2f}s")

        return elapsed

    def elapsed(self):
        return time.perf_counter() - self.start_time

    def _clear_line(self):
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()

    def _animate(self):
        index = 0

        while self.running:
            elapsed = self.elapsed()
            frame = self._FRAMES[index % len(self._FRAMES)]

            sys.stdout.write(f"\r  {frame} {self.label}... {elapsed:.1f}s")
            sys.stdout.flush()

            index += 1
            time.sleep(0.15)
