from agent.engine import (
    run,
    MODEL,
    SYSTEM_PROMPT,
)

from agent.memory import ConversationMemory
from agent.ui import UI


def main():

    UI.banner(
        MODEL
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