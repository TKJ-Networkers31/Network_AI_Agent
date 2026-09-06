from agent.engine import (
    run,
    MODEL,
)

from agent.ui import UI


def main():

    UI.banner(
        MODEL
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

        try:

            run(
                user_input
            )

        except Exception as exc:

            UI.error(
                str(exc)
            )


if __name__ == "__main__":
    main()