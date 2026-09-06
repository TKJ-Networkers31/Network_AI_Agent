import sys
import time
import threading


class Timer:

    def __init__(self, label="Working"):
        self.label = label
        self.running = False
        self.start_time = 0
        self.thread = None

    def start(self):
        self.running = True
        self.start_time = time.perf_counter()

        self.thread = threading.Thread(
            target=self._animate,
            daemon=True
        )

        self.thread.start()

    def stop(self, final_label=None):
        self.running = False

        if self.thread:
            self.thread.join(timeout=0.2)

        elapsed = self.elapsed()

        label = final_label or self.label

        self._clear()

        print(
            f"  ✓ {label:<30} {elapsed:.2f}s"
        )

        return elapsed

    def elapsed(self):
        return time.perf_counter() - self.start_time

    def _clear(self):
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()

    def _animate(self):

        frames = [
            "◐",
            "◓",
            "◑",
            "◒"
        ]

        index = 0

        while self.running:

            elapsed = self.elapsed()

            text = (
                f"\r  {frames[index]} "
                f"{self.label:<28} "
                f"{elapsed:.2f}s"
            )

            sys.stdout.write(text)
            sys.stdout.flush()

            index = (index + 1) % len(frames)

            time.sleep(0.12)


class UI:

    @staticmethod
    def banner(model):

        print()
        print("╔══════════════════════════════════════════════╗")
        print("║              NETWORK AI AGENT                ║")
        print("║              Zero-Touch Tools                ║")
        print("╚══════════════════════════════════════════════╝")
        print()
        print(f"  Model : {model}")
        print("  Mode  : Interactive")
        print()
        print("  Ketik 'exit' untuk keluar.")
        print()

    @staticmethod
    def user(text):
        print(f"\nAgent > {text}")

    @staticmethod
    def phase(text):
        print(f"\n  ◐ {text}")

    @staticmethod
    def tool(name, category, status=True):

        symbol = "✓" if status else "✗"

        print(
            f"    {symbol} "
            f"{category:<10} → {name}"
        )

    @staticmethod
    def result(text):

        print()
        print("  ┌─ RESULT ────────────────────────────────")

        for line in text.splitlines():
            print(f"  │ {line}")

        print("  └─────────────────────────────────────────")

    @staticmethod
    def error(text):

        print()
        print(f"  ✗ ERROR: {text}")

    @staticmethod
    def summary(
        total_time,
        tool_count
    ):

        print()
        print(
            f"  Tools digunakan : {tool_count}"
        )

        print(
            f"  Total waktu     : {total_time:.2f}s"
        )

        print()