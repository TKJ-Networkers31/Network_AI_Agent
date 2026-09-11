"""
run_chat.py — entrypoint terminal sederhana untuk AIRA (khusus testing).

INI BUKAN pengganti web UI (app/) permanen - cuma cara cepat untuk
verifikasi bug fix lewat terminal, tanpa perlu jalankan uvicorn + npm
dev server sekaligus.

CARA PAKAI:
    cd AIRA_ECOSYSTEM
    python run_chat.py

Taruh file ini di: AIRA_ECOSYSTEM/run_chat.py
(sejajar dengan folder core/, agents/, api/, app/)
"""

import sys

from core.logger import setup_logging

# WAJIB dipanggil sebelum Brain/ConversationMemory dipakai, supaya
# semua log (TOOL CALL, LLM REQUEST, dst) tertulis ke
# AIRA_ECOSYSTEM/logs/aira.log - tanpa ini log akan hilang total.
setup_logging()

from core.brain import Brain
from core.memory import ConversationMemory


def main():
    print("=== AIRA (terminal test mode) ===")
    print("Ketik 'exit' untuk keluar, 'reset' untuk reset riwayat.\n")

    memory = ConversationMemory()
    brain = Brain(memory)

    while True:
        try:
            user_input = input("Kamu > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye.")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit"):
            print("Bye.")
            break

        if user_input.lower() == "reset":
            memory.reset()
            print("(riwayat direset)\n")
            continue

        response = brain.think(user_input)

        if response.error:
            print(f"\n[ERROR] {response.answer}\n")
            continue

        print(f"\nAIRA > {response.answer}\n")

        for step in response.steps:
            if step.get("type") == "tool_call":
                status = "OK" if step.get("success") else "GAGAL"
                print(f"  [tool:{status}] {step.get('name')} ({step.get('duration')}s)")


if __name__ == "__main__":
    sys.exit(main() or 0)