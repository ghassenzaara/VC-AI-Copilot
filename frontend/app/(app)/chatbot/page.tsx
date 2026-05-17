"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useUser } from "@clerk/nextjs";
import {
  ArrowUp,
  Paperclip,
  Sparkles,
  Plus,
  MessageSquare,
  Search,
  X,
  FileText,
  ImageIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface Attachment {
  id: string;
  name: string;
  size: number;
  type: string;
  previewUrl?: string;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  ts: number;
  attachments?: Attachment[];
}

const ACCEPTED_TYPES =
  "image/png,image/jpeg,image/webp,image/gif,application/pdf,.doc,.docx,.txt,.md,text/plain,text/markdown";

const MAX_FILE_SIZE = 20 * 1024 * 1024; // 20 MB

function formatBytes(b: number): string {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(0)} KB`;
  return `${(b / (1024 * 1024)).toFixed(1)} MB`;
}

const SUGGESTIONS = [
  {
    title: "Summarize my pipeline",
    subtitle: "Top deals this week, grouped by momentum",
  },
  {
    title: "Find similar startups",
    subtitle: "Companies that cluster together in the market map",
  },
  {
    title: "Surface risks",
    subtitle: "Any open concerns in deals near IC review?",
  },
  {
    title: "Draft a memo",
    subtitle: "One-page IC memo for the deal you pick",
  },
];

// The chat backend is not wired yet. Every prompt returns the same explanation
// so it's transparent to the user that this surface is awaiting integration.
function notWiredReply(): string {
  return (
    "Chat isn't connected to your data yet.\n\n" +
    "Once we wire it up, this is where you'll be able to ask questions across " +
    "your interactions (Granola, Affinity, Slack, Gmail), pull summaries from " +
    "the extraction pipeline, and surface deals that share clusters in the " +
    "market map.\n\n" +
    "For now, head to /startups, /dashboard or /market-maps to see real data."
  );
}

// No mock history. Real history will be persisted server-side later.
const HISTORY: { id: string; title: string; time: string }[] = [];

export default function ChatbotPage() {
  const { user } = useUser();
  const firstName = user?.firstName ?? null;

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [historyQuery, setHistoryQuery] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  const started = messages.length > 0;

  // Revoke object URLs when the component unmounts or attachments change
  useEffect(() => {
    return () => {
      attachments.forEach((a) => {
        if (a.previewUrl) URL.revokeObjectURL(a.previewUrl);
      });
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    const next: Attachment[] = [];
    for (const f of Array.from(files)) {
      if (f.size > MAX_FILE_SIZE) {
        // Silently skip oversize files — a real impl would surface a toast.
        continue;
      }
      next.push({
        id: `${f.name}-${f.size}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        name: f.name,
        size: f.size,
        type: f.type,
        previewUrl: f.type.startsWith("image/")
          ? URL.createObjectURL(f)
          : undefined,
      });
    }
    setAttachments((prev) => [...prev, ...next]);
  }

  function removeAttachment(id: string) {
    setAttachments((prev) => {
      const found = prev.find((a) => a.id === id);
      if (found?.previewUrl) URL.revokeObjectURL(found.previewUrl);
      return prev.filter((a) => a.id !== id);
    });
  }

  const filteredHistory = HISTORY.filter((h) =>
    h.title.toLowerCase().includes(historyQuery.trim().toLowerCase()),
  );

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, pending]);

  function send(text: string) {
    const trimmed = text.trim();
    if ((!trimmed && attachments.length === 0) || pending) return;

    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: "user",
      text: trimmed,
      ts: Date.now(),
      attachments: attachments.length ? attachments : undefined,
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setAttachments([]);
    setPending(true);

    const replyText = notWiredReply();

    window.setTimeout(() => {
      const reply: ChatMessage = {
        id: `a-${Date.now()}`,
        role: "assistant",
        text: replyText,
        ts: Date.now(),
      };
      setMessages((prev) => [...prev, reply]);
      setPending(false);
    }, 700);
  }

  function startFresh() {
    attachments.forEach((a) => {
      if (a.previewUrl) URL.revokeObjectURL(a.previewUrl);
    });
    setMessages([]);
    setInput("");
    setAttachments([]);
  }

  return (
    <div className="h-[calc(100vh-7rem)] flex gap-6">
      {/* Sidebar — chat history */}
      <aside className="hidden lg:flex flex-col w-64 shrink-0">
        <div className="card p-3 flex-1 flex flex-col">
          <button
            onClick={startFresh}
            className="btn-outline w-full justify-start"
          >
            <Plus size={14} />
            New chat
          </button>

          <div className="mt-4 flex items-center gap-2 bg-bg-subtle border border-line rounded-full px-3 py-1.5 text-sm">
            <Search size={12} className="text-ink-faint" />
            <input
              value={historyQuery}
              onChange={(e) => setHistoryQuery(e.target.value)}
              placeholder="Search history"
              className="bg-transparent flex-1 outline-none text-xs text-ink placeholder:text-ink-faint"
            />
            {historyQuery && (
              <button
                onClick={() => setHistoryQuery("")}
                className="text-ink-faint hover:text-ink"
                aria-label="Clear search"
              >
                <X size={12} />
              </button>
            )}
          </div>

          <div className="mt-4 text-[10px] uppercase tracking-wider text-ink-faint px-2">
            Recent
          </div>
          <div className="mt-1 space-y-1 overflow-y-auto">
            {filteredHistory.length === 0 ? (
              <div className="px-2 py-3 text-xs text-ink-faint">
                No matches.
              </div>
            ) : (
              filteredHistory.map((h) => (
                <button
                  key={h.id}
                  className="w-full text-left px-2 py-2 rounded-lg hover:bg-bg-subtle transition"
                >
                  <div className="flex items-center gap-2">
                    <MessageSquare size={12} className="text-ink-faint shrink-0" />
                    <div className="text-sm text-ink truncate">{h.title}</div>
                  </div>
                  <div className="text-[11px] text-ink-faint mt-0.5 ml-5">
                    {h.time}
                  </div>
                </button>
              ))
            )}
          </div>
        </div>
      </aside>

      {/* Main column */}
      <div className="flex-1 flex flex-col min-w-0">
        <AnimatePresence mode="wait">
          {!started ? (
            // ---------- Empty state: centered hero ----------
            <motion.div
              key="hero"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.25 }}
              className="flex-1 flex flex-col items-center justify-center px-4"
            >
              <motion.div
                layoutId="chat-input-shell"
                transition={{ type: "spring", stiffness: 280, damping: 32 }}
                className="w-full max-w-2xl"
              >
                <div className="text-center mb-8">
                  <div className="inline-flex items-center gap-1.5 pill bg-bg-card border border-line text-ink-muted">
                    <Sparkles size={12} className="text-ink-muted" />
                    Vista Copilot
                  </div>
                  <h1 className="mt-4 text-3xl md:text-4xl font-semibold tracking-tight text-ink">
                    {firstName ? `Hey ${firstName},` : "Hey there,"} what should
                    we dig into?
                  </h1>
                  <p className="mt-2 text-sm text-ink-muted">
                    Ask anything across your interactions, deals and market
                    maps.
                  </p>
                </div>

                <ChatInput
                  value={input}
                  onChange={setInput}
                  onSubmit={() => send(input)}
                  onFiles={handleFiles}
                  attachments={attachments}
                  onRemoveAttachment={removeAttachment}
                  large
                />

                <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s.title}
                      onClick={() => send(s.title)}
                      className="text-left card p-3.5 hover:border-ink/20 transition"
                    >
                      <div className="text-sm font-medium text-ink">
                        {s.title}
                      </div>
                      <div className="text-xs text-ink-muted mt-0.5">
                        {s.subtitle}
                      </div>
                    </button>
                  ))}
                </div>
              </motion.div>
            </motion.div>
          ) : (
            // ---------- Full chat ----------
            <motion.div
              key="chat"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.2 }}
              className="flex-1 flex flex-col card overflow-hidden"
            >
              <div className="px-5 py-3 border-b border-line flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Sparkles size={14} className="text-ink-muted" />
                  <div className="text-sm font-medium">Vista Copilot</div>
                </div>
                <button onClick={startFresh} className="btn-ghost">
                  <Plus size={14} />
                  New chat
                </button>
              </div>

              <div
                ref={scrollRef}
                className="flex-1 overflow-y-auto px-6 py-6 space-y-4"
              >
                {messages.map((m) => (
                  <MessageBubble key={m.id} msg={m} />
                ))}
                {pending && <TypingIndicator />}
              </div>

              <motion.div
                layoutId="chat-input-shell"
                transition={{ type: "spring", stiffness: 280, damping: 32 }}
                className="px-5 py-4 border-t border-line bg-bg-card"
              >
                <ChatInput
                  value={input}
                  onChange={setInput}
                  onSubmit={() => send(input)}
                  onFiles={handleFiles}
                  attachments={attachments}
                  onRemoveAttachment={removeAttachment}
                />
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

function ChatInput({
  value,
  onChange,
  onSubmit,
  onFiles,
  attachments,
  onRemoveAttachment,
  large = false,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  onFiles: (files: FileList | null) => void;
  attachments: Attachment[];
  onRemoveAttachment: (id: string) => void;
  large?: boolean;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const canSend = value.trim().length > 0 || attachments.length > 0;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (canSend) onSubmit();
      }}
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        onFiles(e.dataTransfer.files);
      }}
      className={cn(
        "bg-bg-card border rounded-2xl shadow-card transition",
        dragOver ? "border-ink/40 bg-bg-subtle" : "border-line",
        large ? "p-3.5" : "p-2.5",
      )}
    >
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept={ACCEPTED_TYPES}
        className="hidden"
        onChange={(e) => {
          onFiles(e.target.files);
          // Reset so the same file can be re-selected later
          if (fileInputRef.current) fileInputRef.current.value = "";
        }}
      />

      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2.5">
          {attachments.map((a) => (
            <AttachmentChip
              key={a.id}
              attachment={a}
              onRemove={() => onRemoveAttachment(a.id)}
            />
          ))}
        </div>
      )}

      <div className="flex items-end gap-2">
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          className="text-ink-muted hover:text-ink p-1.5 rounded-lg hover:bg-bg-subtle transition"
          aria-label="Attach file"
          title="Attach images, PDFs, or docs"
        >
          <Paperclip size={16} />
        </button>
        <textarea
          rows={large ? 2 : 1}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (canSend) onSubmit();
            }
          }}
          placeholder={
            dragOver
              ? "Drop your files here…"
              : large
                ? "Ask about a deal, a sector, or a specific founder…"
                : "Reply…"
          }
          className={cn(
            "flex-1 bg-transparent resize-none outline-none text-ink placeholder:text-ink-faint",
            large ? "text-base px-1 py-1" : "text-sm px-1 py-1.5",
          )}
        />
        <button
          type="submit"
          disabled={!canSend}
          className={cn(
            "rounded-xl bg-ink text-white flex items-center justify-center transition",
            large ? "h-10 w-10" : "h-9 w-9",
            !canSend && "opacity-30 cursor-not-allowed",
          )}
          aria-label="Send"
        >
          <ArrowUp size={16} strokeWidth={2.5} />
        </button>
      </div>
    </form>
  );
}

function AttachmentChip({
  attachment,
  onRemove,
}: {
  attachment: Attachment;
  onRemove: () => void;
}) {
  const isImage = attachment.type.startsWith("image/");
  return (
    <div className="group flex items-center gap-2 bg-bg-subtle border border-line rounded-lg pl-1.5 pr-2 py-1.5 max-w-[240px]">
      {isImage && attachment.previewUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={attachment.previewUrl}
          alt=""
          className="h-7 w-7 rounded object-cover shrink-0"
        />
      ) : (
        <div className="h-7 w-7 rounded bg-bg-card border border-line flex items-center justify-center shrink-0">
          {isImage ? (
            <ImageIcon size={12} className="text-ink-muted" />
          ) : (
            <FileText size={12} className="text-ink-muted" />
          )}
        </div>
      )}
      <div className="min-w-0 flex-1">
        <div className="text-xs text-ink truncate font-medium">
          {attachment.name}
        </div>
        <div className="text-[10px] text-ink-faint">
          {formatBytes(attachment.size)}
        </div>
      </div>
      <button
        type="button"
        onClick={onRemove}
        className="text-ink-faint hover:text-ink p-0.5 rounded shrink-0"
        aria-label={`Remove ${attachment.name}`}
      >
        <X size={12} />
      </button>
    </div>
  );
}

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18 }}
      className={cn("flex", isUser ? "justify-end" : "justify-start")}
    >
      <div
        className={cn(
          "max-w-[78%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap",
          isUser
            ? "bg-ink text-white rounded-br-md"
            : "bg-bg-subtle border border-line text-ink rounded-bl-md",
        )}
      >
        {msg.attachments && msg.attachments.length > 0 && (
          <div
            className={cn(
              "flex flex-wrap gap-1.5",
              msg.text && "mb-2",
            )}
          >
            {msg.attachments.map((a) => {
              const isImage = a.type.startsWith("image/");
              return (
                <div
                  key={a.id}
                  className={cn(
                    "flex items-center gap-2 rounded-lg px-2 py-1.5 max-w-[220px]",
                    isUser
                      ? "bg-white/10 border border-white/15"
                      : "bg-bg-card border border-line",
                  )}
                >
                  {isImage && a.previewUrl ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={a.previewUrl}
                      alt=""
                      className="h-7 w-7 rounded object-cover shrink-0"
                    />
                  ) : (
                    <div
                      className={cn(
                        "h-7 w-7 rounded flex items-center justify-center shrink-0",
                        isUser
                          ? "bg-white/10"
                          : "bg-bg-subtle border border-line",
                      )}
                    >
                      {isImage ? (
                        <ImageIcon
                          size={12}
                          className={
                            isUser ? "text-white/70" : "text-ink-muted"
                          }
                        />
                      ) : (
                        <FileText
                          size={12}
                          className={
                            isUser ? "text-white/70" : "text-ink-muted"
                          }
                        />
                      )}
                    </div>
                  )}
                  <div className="min-w-0">
                    <div
                      className={cn(
                        "text-xs font-medium truncate",
                        isUser ? "text-white" : "text-ink",
                      )}
                    >
                      {a.name}
                    </div>
                    <div
                      className={cn(
                        "text-[10px]",
                        isUser ? "text-white/60" : "text-ink-faint",
                      )}
                    >
                      {formatBytes(a.size)}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
        {msg.text}
      </div>
    </motion.div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="bg-bg-subtle border border-line rounded-2xl rounded-bl-md px-4 py-3 inline-flex items-center gap-1">
        <span className="h-1.5 w-1.5 rounded-full bg-ink-faint animate-bounce [animation-delay:-0.3s]" />
        <span className="h-1.5 w-1.5 rounded-full bg-ink-faint animate-bounce [animation-delay:-0.15s]" />
        <span className="h-1.5 w-1.5 rounded-full bg-ink-faint animate-bounce" />
      </div>
    </div>
  );
}
