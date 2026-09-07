import queue
import threading

from agent.core.engine import (
    run,
    SYSTEM_PROMPT,
)

from agent.core.memory import ConversationMemory
from agent.core.ui import UI
from agent.utils.time_utils import format_datetime_id
from agent.core.providers import (
    get_active_provider,
    list_providers,
    set_active_provider_key,
    get_openrouter_credits,
)
from agent.voice.voice_io import VoiceIO
from agent.voice import tts as tts_module


def _stdin_reader(input_queue, stop_event):
    """
    Baca stdin di thread terpisah supaya bisa berjalan bersamaan
    dengan voice listener - keduanya push ke queue yang sama,
    main loop tinggal ambil siapa yang lebih dulu selesai.
    """

    while not stop_event.is_set():

        try:
            line = input(
                "Agent > "
            ).strip()

        except (KeyboardInterrupt, EOFError):

            input_queue.put(("__exit__", None))
            break

        if line:
            input_queue.put(("text", line))


def main(start_with_voice=False):

    _, active_config = get_active_provider()

    UI.banner(
        active_config["label"]
    )

    memory = ConversationMemory(
        system_prompt=SYSTEM_PROMPT
    )

    input_queue = queue.Queue()
    stop_event = threading.Event()

    def on_transcript(text):
        input_queue.put(("voice", text))

    voice_io = VoiceIO(on_transcript)

    stdin_thread = threading.Thread(
        target=_stdin_reader,
        args=(input_queue, stop_event),
        daemon=True
    )

    stdin_thread.start()

    if start_with_voice:

        voice_io.start()

        print(
            "  🎙 Mode suara aktif dari awal. Ngomong kapan saja, "
            "atau tetap bisa ketik.\n"
        )

    while True:

        source, user_input = input_queue.get()

        if source == "__exit__":
            print("\nBye.")
            voice_io.stop()
            stop_event.set()
            break

        user_input = (user_input or "").strip()

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit"):

            print("Bye.")
            voice_io.stop()
            stop_event.set()
            break

        if user_input.lower() in ("reset", "clear", "lupa"):

            memory.reset()
            print("  ✓ Riwayat percakapan telah direset.")
            continue

        if user_input.lower() in ("waktu", "jam", "tanggal"):

            print()
            print(f"  Waktu saat ini: {format_datetime_id()}")
            print()
            continue

        if user_input.lower() in ("token", "sisa token", "cek token", "saldo"):

            print()

            line = memory.token_tracker.summary_line()
            print(f"  {line}" if line else "  Belum ada token terpakai di sesi ini.")

            active_key, active_config = get_active_provider()

            if active_config["type"] == "openai":

                credit_info = get_openrouter_credits(active_config)

                if credit_info.get("success"):
                    total = credit_info.get("total_credits")
                    used = credit_info.get("total_usage")
                    remaining = credit_info.get("remaining")

                    if remaining is not None:
                        print(
                            f"  Saldo OpenRouter : {used:.4f} / {total:.4f} "
                            f"terpakai (sisa: {remaining:.4f})"
                        )
                    else:
                        print(f"  Saldo OpenRouter : total={total}, usage={used}")

                else:
                    print(f"  Gagal cek saldo OpenRouter: {credit_info.get('error')}")

            else:
                print("  (Provider aktif model lokal Ollama - tidak ada saldo API.)")

            print()
            continue

        # ------------------------------------------------------
        # TOGGLE VOICE MODE
        # ------------------------------------------------------

        if user_input.lower() in ("suara on", "voice on", "aktifkan suara"):

            voice_io.start()
            print("  🎙 Mode suara diaktifkan.")
            continue

        if user_input.lower() in ("suara off", "voice off", "matikan suara"):

            voice_io.stop()
            print("  🔇 Mode suara dimatikan.")
            continue

        if user_input.lower() in ("model", "models", "ganti model"):

            providers = list_providers()
            keys = list(providers.keys())
            active_key, _ = get_active_provider()

            print()
            print("  Pilih model:")

            for i, key in enumerate(keys, start=1):

                marker = "  ← aktif" if key == active_key else ""

                print(f"    {i}. {providers[key]['label']}{marker}")

            choice = input("\n  Nomor: ").strip()

            if choice.isdigit() and 1 <= int(choice) <= len(keys):

                selected = keys[int(choice) - 1]
                set_active_provider_key(selected)

                print(f"  ✓ Model diganti ke: {providers[selected]['label']}\n")

            else:
                print("  Input tidak valid, model tidak diganti.\n")

            continue

        # ------------------------------------------------------
        # NORMAL CHAT (dari teks atau suara, sama-sama lewat run())
        # ------------------------------------------------------

        try:

            answer = run(
                user_input,
                memory
            )

            # Kalau input datang dari suara (atau voice mode aktif),
            # baca balik jawabannya lewat Kokoro. Mic di-pause dulu
            # supaya nggak menangkap suara Kokoro sendiri (barge-in).
            if voice_io.is_active() and answer:

                tts_module.speak(
                    answer,
                    on_start=voice_io.pause_mic,
                    on_end=voice_io.resume_mic,
                )

        except Exception as exc:

            UI.error(str(exc))


if __name__ == "__main__":
    main()