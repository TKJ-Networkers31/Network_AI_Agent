from agent.engine import (
    run,
    SYSTEM_PROMPT,
)

from agent.memory import ConversationMemory
from agent.ui import UI
from agent.providers import (
    get_active_provider,
    list_providers,
    set_active_provider_key,
)


def main():

    _, active_config = get_active_provider()

    UI.banner(
        active_config["label"]
    )

    memory = ConversationMemory(
        system_prompt=SYSTEM_PROMPT
    )

    while True:

        try:

            user_input = input(
                "Agent > "
            ).strip()

        except (
            KeyboardInterrupt,
            EOFError
        ):

            print("\nBye.")
            break

        if not user_input:
            continue

        if user_input.lower() in (
            "exit",
            "quit"
        ):

            print("Bye.")
            break

        if user_input.lower() in (
            "reset",
            "clear",
            "lupa"
        ):

            memory.reset()

            print(
                "  ✓ Riwayat percakapan telah direset."
            )

            continue

        if user_input.lower() in (
            "model",
            "models",
            "ganti model"
        ):

            providers = list_providers()
            keys = list(providers.keys())
            active_key, _ = get_active_provider()

            print()
            print("  Pilih model:")

            for i, key in enumerate(keys, start=1):

                marker = (
                    "  ← aktif"
                    if key == active_key
                    else ""
                )

                print(
                    f"    {i}. {providers[key]['label']}{marker}"
                )

            choice = input(
                "\n  Nomor: "
            ).strip()

            if (
                choice.isdigit()
                and 1 <= int(choice) <= len(keys)
            ):

                selected = keys[int(choice) - 1]
                set_active_provider_key(selected)

                print(
                    f"  ✓ Model diganti ke: "
                    f"{providers[selected]['label']}\n"
                )

            else:

                print(
                    "  Input tidak valid, model tidak diganti.\n"
                )

            continue

        try:

            run(
                user_input,
                memory
            )

        except Exception as exc:

            UI.error(
                str(exc)
            )


if __name__ == "__main__":
    main()