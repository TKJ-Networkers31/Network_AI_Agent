"""
Pelacak token per sesi percakapan.

Kenapa dipisah dari agent/memory.py: ConversationMemory fokus ke
riwayat percakapan yang DIKIRIM ke LLM, sedangkan token usage
adalah metadata yang DATANG SETELAH respons provider selesai.
Tanggung jawabnya beda, jadi dipisah biar rapi.

Catatan penting:
- Ollama (lokal) tidak punya konsep "kuota tersisa" - cuma
  melaporkan berapa token dipakai per request (prompt_eval_count,
  eval_count). Untuk provider lokal, tracker ini cuma info panjang
  percakapan.
- Provider eksternal (OpenRouter) melaporkan usage per request
  lewat field 'usage' di response chat/completions. Untuk SALDO/
  KUOTA tersisa, itu bukan bagian dari response chat - harus dicek
  lewat endpoint terpisah (lihat get_openrouter_credits di
  agent/providers.py).
"""


class TokenTracker:

    def __init__(self):
        self.reset()

    def reset(self):

        self.session_prompt_tokens = 0
        self.session_completion_tokens = 0
        self.session_total_tokens = 0
        self.last_usage = None

    def add(self, usage):
        """
        usage: dict berisi 'prompt_tokens', 'completion_tokens',
        'total_tokens'. Boleh None/kosong kalau provider tidak
        melaporkan usage sama sekali (misal request gagal).
        """

        if not usage:
            return

        prompt = usage.get("prompt_tokens") or 0
        completion = usage.get("completion_tokens") or 0
        total = usage.get("total_tokens") or (prompt + completion)

        self.session_prompt_tokens += prompt
        self.session_completion_tokens += completion
        self.session_total_tokens += total

        self.last_usage = {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
        }

    def summary_line(self):
        """
        Baris ringkas untuk ditampilkan di UI.summary() setelah
        tiap jawaban. Return None kalau belum ada token tercatat
        (misal provider tidak melaporkan usage sama sekali).
        """

        if self.session_total_tokens == 0:
            return None

        last = ""

        if self.last_usage:
            last = (
                f" (giliran ini: {self.last_usage['total_tokens']} token)"
            )

        return (
            f"Token sesi: {self.session_total_tokens} total "
            f"(prompt: {self.session_prompt_tokens}, "
            f"completion: {self.session_completion_tokens}){last}"
        )