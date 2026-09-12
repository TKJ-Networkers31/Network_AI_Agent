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

FIX (Phase 0 Stabilization):
- Menambahkan Timer live (durasi berjalan) selama Brain.think()
  bekerja, supaya terlihat AIRA sedang proses, bukan diam - penting
  karena tool network (SSH/SNMP) bisa timeout puluhan detik.
- Menangkap KeyboardInterrupt DI SEKITAR brain.think(), bukan hanya
  di sekitar input(). Sebelumnya Ctrl+C saat tool sedang berjalan
  (mis. menunggu SSH timeout) bocor jadi traceback mentah dan
  menghentikan proses secara paksa.
- Menampilkan alasan gagal/berhasil per tool call (bukan cuma
  OK/GAGAL), diambil dari 'result_preview' yang sudah dikirim
  planner tapi sebelumnya tidak pernah ditampilkan.
"""

import json
import sys

from core.logger import setup_logging

# WAJIB dipanggil sebelum Brain/ConversationMemory dipakai, supaya
# semua log (TOOL CALL, LLM REQUEST, dst) tertulis ke
# AIRA_ECOSYSTEM/logs/aira.log - tanpa ini log akan hilang total.
setup_logging()

from core.brain import Brain
from core.memory import ConversationMemory
from core.ui import Timer


def _extract_error_reason(result_preview):
    """
    result_preview adalah JSON string (kadang dipotong dengan
    '...(truncated)' di ujungnya kalau terlalu panjang - lihat
    agents/rei/planner.py::_preview). Coba ambil field 'error' kalau
    ada, supaya user tahu KENAPA tool gagal, bukan cuma tahu gagal.
    """

    if not result_preview:
        return None

    cleaned = result_preview.replace("...(truncated)", "")

    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        return None

    if isinstance(data, dict):
        return data.get("error")

    return None


def _print_step(step):

    step_type = step.get("type")

    if step_type == "tool_call":

        name = step.get("name")
        success = step.get("success")
        duration = step.get("duration")
        status = "OK" if success else "GAGAL"

        print(f"  [tool:{status}] {name} ({duration}s)")

        if not success:
            reason = _extract_error_reason(step.get("result_preview"))
            print(f"      alasan gagal: {reason or '(tidak ada detail error dari tool)'}")

        return

    if step_type == "confirmation_required":
        print(f"  [tool:SKIP] {step.get('name')} - butuh konfirmasi manual, dilewati otomatis di terminal.")
        return

    if step_type == "limit_reached":
        print(f"  [batas tercapai] {step.get('message')}")
        return

    print(f"  [{step_type}] {step}")


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

        timer = Timer("AIRA sedang berpikir")
        timer.start()

        try:
            response = brain.think(user_input)

        except KeyboardInterrupt:
            timer.stop("Dibatalkan oleh user (Ctrl+C)")
            print(
                "\n  (Proses dibatalkan. Catatan: kalau ada tool network "
                "yang sedang menunggu timeout SSH/SNMP di background, "
                "itu tetap berjalan sampai selesai sendiri - hanya "
                "tidak lagi ditunggu di sini.)\n"
            )
            continue

        except Exception as exc:
            timer.stop("Error tak terduga")
            print(f"\n[ERROR TAK TERDUGA] {exc}\n")
            continue

        timer.stop("Selesai")

        if response.error:
            print(f"\n[ERROR] {response.answer}\n")
            continue

        print(f"\nAIRA > {response.answer}\n")

        if response.steps:
            print(f"  --- {len(response.steps)} langkah tool (total {response.duration}s) ---")
            for step in response.steps:
                _print_step(step)
            print()


if __name__ == "__main__":
    sys.exit(main() or 0)