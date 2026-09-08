import { useEffect, useRef, useState } from "react";
import TopBar from "../components/TopBar.jsx";
import MessageBubble from "../components/MessageBubble.jsx";
import ChatInput from "../components/ChatInput.jsx";
import { api } from "../api.js";

export default function ChatPage() {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content:
        "Hai! Saya Network AI Agent. Tanya apa saja soal jaringan, perangkat MikroTik, atau ngobrol santai. 👋",
      steps: [],
    },
  ]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function handleSend(text) {
    setError(null);
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setLoading(true);

    try {
      const result = await api.chat(text);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: result.answer,
          steps: result.steps,
        },
      ]);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleReset() {
    await api.reset();
    setMessages([
      {
        role: "assistant",
        content: "Riwayat percakapan sudah direset. Mulai dari sini ya.",
        steps: [],
      },
    ]);
  }

  return (
    <div className="flex flex-col h-full">
      <TopBar
        title="Chat"
        subtitle="Ngobrol dan minta agent observasi jaringan kamu"
      />

      <div className="flex justify-end mb-3">
        <button
          onClick={handleReset}
          className="text-xs text-white/50 hover:text-white border border-border rounded-lg px-3 py-1.5 hover:bg-white/5 transition"
        >
          🔄 Reset percakapan
        </button>
      </div>

      <div className="flex-1 overflow-y-auto space-y-4 pr-1 pb-3">
        {messages.map((m, i) => (
          <MessageBubble key={i} role={m.role} content={m.content} steps={m.steps} />
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-card border border-border rounded-xl2 px-4 py-3 text-sm text-white/50">
              <span className="animate-pulse">Agent sedang berpikir...</span>
            </div>
          </div>
        )}

        {error && (
          <div className="text-xs px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/20 text-red-300">
            {error}
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <div className="mt-3">
        <ChatInput onSend={handleSend} disabled={loading} />
      </div>
    </div>
  );
}
