from agent.logger import logger


class ConversationMemory:
    """
    Menyimpan riwayat percakapan (messages) selama satu sesi
    agar agent bisa mengingat konteks antar giliran (multi-turn).

    Trimming diterapkan supaya context window ke LLM tidak
    membengkak tanpa batas seiring panjangnya sesi, dengan
    menjaga agar potongan tidak jatuh di tengah rangkaian
    assistant(tool_calls) -> tool result yang bisa merusak
    format pesan yang dikirim ke LLM.
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

        cut_index = self._find_safe_cut_index(overflow)

        removed = self.history[:cut_index]
        self.history = self.history[cut_index:]

        if removed:
            logger.info(
                f"MEMORY TRIM | menghapus {len(removed)} "
                f"pesan lama dari riwayat."
            )

    def _find_safe_cut_index(self, start_index):
        """
        Mencari titik potong yang aman, yaitu tepat sebelum
        sebuah pesan role="user". Ini mencegah history hasil
        trim dimulai dengan pesan role="tool" tanpa didahului
        assistant message yang memuat tool_calls terkait,
        yang bisa membuat format pesan tidak valid untuk LLM.

        Jika tidak ditemukan boundary yang aman sampai akhir
        list, maka seluruh history dianggap tidak aman untuk
        dipertahankan sebagian, sehingga dikosongkan total.
        """

        cut_index = start_index

        while cut_index < len(self.history):

            if self.history[cut_index].get("role") == "user":
                return cut_index

            cut_index += 1

        return len(self.history)