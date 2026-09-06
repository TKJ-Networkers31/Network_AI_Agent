from agent.logger import logger


class ConversationMemory:
    """
    Menyimpan riwayat percakapan (messages) selama satu sesi
    agar agent bisa mengingat konteks antar giliran (multi-turn).

    Trimming sederhana diterapkan supaya context window ke LLM
    tidak membengkak tanpa batas seiring panjangnya sesi.
    """

    def __init__(
        self,
        system_prompt,
        max_history_messages=30
    ):

        self.system_prompt = system_prompt
        self.max_history_messages = max_history_messages

        self.history = []

    def reset(self):

        self.history = []

        logger.info(
            "MEMORY RESET | riwayat percakapan dikosongkan."
        )

    def add_user(self, content):

        self.history.append({
            "role": "user",
            "content": content
        })

    def add_message(self, message):
        """
        message: dict lengkap dari respons LLM
        (bisa berisi role=assistant, content, tool_calls, dll)
        """

        self.history.append(
            message
        )

    def add_tool_result(self, content):

        self.history.append({
            "role": "tool",
            "content": content
        })

    def get_messages(self):
        """
        Mengembalikan messages lengkap (system prompt + history)
        yang siap dikirim ke LLM. History di-trim dari yang
        paling lama jika sudah melewati batas.
        """

        self._trim()

        return (
            [
                {
                    "role": "system",
                    "content": self.system_prompt
                }
            ]
            + self.history
        )

    def _trim(self):

        if len(self.history) <= self.max_history_messages:
            return

        overflow = (
            len(self.history)
            - self.max_history_messages
        )

        removed = self.history[:overflow]

        self.history = self.history[overflow:]

        logger.info(
            f"MEMORY TRIM | menghapus {len(removed)} "
            f"pesan lama dari riwayat."
        )