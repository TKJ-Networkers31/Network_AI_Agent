import ToolStep from "./ToolStep.jsx";

export default function MessageBubble({ role, content, steps }) {
  const isUser = role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[75%] ${isUser ? "" : "w-full"}`}>
        {!isUser && steps && steps.length > 0 && (
          <div className="mb-2 space-y-1.5">
            {steps.map((step, i) => (
              <ToolStep key={i} step={step} />
            ))}
          </div>
        )}

        <div
          className={`rounded-xl2 px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap break-words
            ${
              isUser
                ? "bg-accent-gradient text-white"
                : "bg-card border border-border text-white/90"
            }`}
        >
          {content}
        </div>
      </div>
    </div>
  );
}
