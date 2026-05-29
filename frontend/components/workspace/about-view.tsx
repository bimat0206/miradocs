import { Bot, Brain, FileSearch, GitCompareArrows, Search, Sparkles, Tags, Upload, X } from "lucide-react";
import { VersionBadge } from "../version-badge";

const steps = [
  { step: "01", title: "Upload", icon: Upload, desc: "Drop any PDF, DOCX, or PPTX into the Library. MiraDocs parses, extracts tables and figures, and builds a structured knowledge base — all on your machine." },
  { step: "02", title: "Process & Inspect", icon: FileSearch, desc: "Watch the pipeline run in real time. Review extracted page images, quality signals, tables, and figures before anything gets indexed." },
  { step: "03", title: "Search", icon: Search, desc: "Hybrid search combines semantic understanding with keyword precision. Every result is anchored to the exact page it came from." },
  { step: "04", title: "Ask your LLM", icon: Brain, desc: "Connect Claude, ChatGPT, Gemini, or any MCP-compatible AI client. Ask meaningful questions and get answers grounded in real page evidence — not hallucinations." },
];

const features = [
  { label: "Library", icon: Search, desc: "Keyword and tag search across all your documents with paginated, multi-select management." },
  { label: "Tag", icon: Tags, desc: "Organise documents with up to five custom tags — add or edit anytime, without reprocessing." },
  { label: "Inspect", icon: FileSearch, desc: "Jump to any page, preview images at full size, and verify extraction quality before indexing." },
  { label: "Compare", icon: GitCompareArrows, desc: "Side-by-side page evidence for two documents — with keyword overlays and match navigation." },
];

const llmClients = ["Claude", "ChatGPT", "Gemini", "Cursor", "Windsurf", "Codex"];

interface AboutViewProps {
  onClose: () => void;
}

export function AboutView({ onClose }: AboutViewProps) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Header bar */}
      <div className="flex shrink-0 items-center justify-between border-b border-white/10 px-6 py-4">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-cyan-200/60">About</p>
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="text-lg font-semibold text-slate-50">MiraDocs</h2>
            <VersionBadge />
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="flex items-center justify-center rounded-xl border border-white/10 bg-white/[0.04] p-2 text-slate-400 transition hover:border-white/20 hover:text-slate-100"
          aria-label="Close"
        >
          <X size={16} />
        </button>
      </div>

      {/* Scrollable content */}
      <div className="thin-scrollbar flex-1 overflow-y-auto">
        {/* Hero */}
        <div className="relative overflow-hidden border-b border-white/10 px-8 py-12">
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-cyan-500/10 via-transparent to-violet-600/10" />
          <div className="pointer-events-none absolute -right-16 -top-16 h-56 w-56 rounded-full bg-violet-500/10 blur-3xl" />
          <div className="relative max-w-2xl">
            <p className="mb-3 text-xs uppercase tracking-[0.35em] text-violet-300/70">The name</p>
            <h1 className="text-4xl font-semibold leading-tight tracking-tight text-slate-50">
              <span className="bg-gradient-to-r from-cyan-300 to-violet-400 bg-clip-text text-transparent">Mira</span>
              Docs
            </h1>
            <p className="mt-4 text-base leading-7 text-slate-400">
              <span className="font-medium text-slate-200">Mira</span> comes from the Latin <span className="italic text-slate-300">mīrus</span> — meaning wonder, astonishment, something that makes you look twice.
              That's the feeling we're after: the moment a buried insight surfaces from a document you've read a dozen times and still missed.
              <span className="font-medium text-slate-200"> Docs</span> keeps it honest — this is a workspace built around your documents, nothing more.
            </p>
            <p className="mt-3 text-sm leading-7 text-slate-500">
              Together: a tool that finds the wonder hiding inside ordinary files.
            </p>
          </div>
        </div>

        {/* How it works */}
        <div className="border-b border-white/10 p-8">
          <p className="mb-6 text-xs uppercase tracking-[0.35em] text-slate-500">How it works</p>
          <div className="grid gap-4 sm:grid-cols-2">
            {steps.map((s) => {
              const Icon = s.icon;
              return (
                <div key={s.step} className="rounded-3xl border border-white/10 bg-white/[0.03] p-6 transition hover:border-cyan-300/20 hover:bg-white/[0.05]">
                  <div className="mb-4 flex items-center justify-between">
                    <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-300/20 to-violet-500/20 text-cyan-200">
                      <Icon size={16} />
                    </div>
                    <span className="text-2xl font-bold text-white/[0.06]">{s.step}</span>
                  </div>
                  <h3 className="mb-1.5 text-sm font-semibold text-slate-100">{s.title}</h3>
                  <p className="text-xs leading-6 text-slate-400">{s.desc}</p>
                </div>
              );
            })}
          </div>
        </div>

        {/* MCP highlight */}
        <div className="border-b border-white/10 p-8">
          <div className="rounded-3xl border border-violet-400/20 bg-gradient-to-br from-violet-500/10 via-white/[0.02] to-cyan-400/10 p-6">
            <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-violet-400/25 bg-violet-400/10 px-3 py-1.5 text-xs text-violet-300">
              <Sparkles size={11} />
              MCP Integration
            </div>
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-xl font-semibold text-slate-50">Bring your own LLM</h2>
                <p className="mt-2 text-sm leading-7 text-slate-400">
                  Connect any MCP-compatible AI client directly to your indexed documents. Ask meaningful questions and get answers grounded in real page evidence — so every answer comes with a source you can verify.
                </p>
                <div className="mt-4 flex flex-wrap gap-2">
                  {llmClients.map((name) => (
                    <span key={name} className="rounded-full border border-white/10 bg-white/[0.05] px-3 py-1 text-xs text-slate-300">{name}</span>
                  ))}
                </div>
              </div>
              <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl border border-violet-400/25 bg-violet-400/10 text-violet-200">
                <Bot size={28} />
              </div>
            </div>
          </div>
        </div>

        {/* Workspace */}
        <div className="p-8">
          <p className="mb-6 text-xs uppercase tracking-[0.35em] text-slate-500">Workspace</p>
          <div className="grid gap-4 sm:grid-cols-2">
            {features.map((f) => {
              const Icon = f.icon;
              return (
                <div key={f.label} className="rounded-3xl border border-white/10 bg-white/[0.03] p-5 transition hover:border-emerald-300/20 hover:bg-white/[0.05]">
                  <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-xl border border-emerald-300/20 bg-emerald-300/10 text-emerald-200">
                    <Icon size={16} />
                  </div>
                  <h3 className="mb-1 text-sm font-semibold text-slate-100">{f.label}</h3>
                  <p className="text-xs leading-6 text-slate-400">{f.desc}</p>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
