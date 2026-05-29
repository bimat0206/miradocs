import { ArrowLeft, Bot, Brain, FileSearch, GitCompareArrows, Lock, Search, Sparkles, Tags, Upload } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { VersionBadge } from "../../components/version-badge";

export const metadata: Metadata = {
  title: "About | MiraDocs",
  description: "MiraDocs — local-first document intelligence with MCP integration. Connect your LLM and get grounded, page-cited answers from any PDF, DOCX, or PPTX.",
};

const steps = [
  {
    step: "01",
    title: "Upload",
    icon: Upload,
    desc: "Drop any PDF, DOCX, or PPTX into the Library. MiraDocs parses, extracts tables and figures, and builds a structured knowledge base — all on your machine.",
  },
  {
    step: "02",
    title: "Process & Inspect",
    icon: FileSearch,
    desc: "Watch the pipeline run in real time. Review extracted page images, quality signals, tables, and figures before anything gets indexed.",
  },
  {
    step: "03",
    title: "Search",
    icon: Search,
    desc: "Hybrid search combines semantic understanding with keyword precision. Every result is anchored to the exact page it came from.",
  },
  {
    step: "04",
    title: "Ask your LLM",
    icon: Brain,
    desc: "Connect Claude, ChatGPT, Gemini, or any MCP-compatible AI client. Ask meaningful questions and get answers grounded in real page evidence — not hallucinations.",
  },
];

const features = [
  { label: "Library", icon: Search, desc: "Keyword and tag search across all your documents with paginated, multi-select management." },
  { label: "Tag", icon: Tags, desc: "Organise documents with up to five custom tags — add or edit anytime, without reprocessing." },
  { label: "Inspect", icon: FileSearch, desc: "Jump to any page, preview images at full size, and verify extraction quality before indexing." },
  { label: "Compare", icon: GitCompareArrows, desc: "Side-by-side page evidence for two documents — with keyword overlays and match navigation." },
];

const llmClients = ["Claude", "ChatGPT", "Gemini", "Cursor", "Windsurf", "Codex"];

export default function AboutPage() {
  return (
    <main className="min-h-screen p-5 text-slate-100">
      <section className="min-h-[calc(100vh-2.5rem)] w-full overflow-hidden rounded-[28px] glass gradient-border">

        {/* Nav */}
        <div className="border-b border-white/10 px-6 py-4">
          <Link
            href="/"
            className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-sm text-slate-300 transition hover:border-cyan-300/45 hover:text-cyan-100"
          >
            <ArrowLeft size={16} />
            Back to workspace
          </Link>
        </div>

        {/* Hero */}
        <div className="relative overflow-hidden border-b border-white/10 px-8 py-16">
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-cyan-500/10 via-transparent to-violet-600/10" />
          <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-violet-500/10 blur-3xl" />
          <div className="relative max-w-2xl">
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-cyan-300/20 bg-cyan-300/10 px-3 py-1.5 text-xs text-cyan-200">
              <Lock size={11} />
              100% local · no cloud · no data leaves your machine
            </div>
            <div className="mb-4">
              <VersionBadge />
            </div>
            <h1 className="text-5xl font-semibold leading-tight tracking-tight text-slate-50">
              Your documents.<br />
              <span className="bg-gradient-to-r from-cyan-300 to-violet-400 bg-clip-text text-transparent">
                Instantly searchable.
              </span>
            </h1>
            <p className="mt-5 text-lg leading-8 text-slate-400">
              Digging through a 200-page PDF to find one fact wastes hours. MiraDocs turns any document into a searchable, evidence-backed knowledge base — then lets your AI ask the questions for you.
            </p>
          </div>
        </div>

        {/* How it works */}
        <div className="border-b border-white/10 p-8">
          <p className="mb-8 text-xs uppercase tracking-[0.35em] text-slate-500">How it works</p>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {steps.map((s) => {
              const Icon = s.icon;
              return (
                <div
                  key={s.step}
                  className="group relative rounded-3xl border border-white/10 bg-white/[0.03] p-6 transition hover:border-cyan-300/25 hover:bg-white/[0.055]"
                >
                  <div className="mb-4 flex items-center justify-between">
                    <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-cyan-300/20 to-violet-500/20 text-cyan-200">
                      <Icon size={18} />
                    </div>
                    <span className="text-3xl font-bold text-white/[0.06]">{s.step}</span>
                  </div>
                  <h3 className="mb-2 font-semibold text-slate-100">{s.title}</h3>
                  <p className="text-sm leading-6 text-slate-400">{s.desc}</p>
                </div>
              );
            })}
          </div>
        </div>

        {/* MCP / LLM highlight */}
        <div className="border-b border-white/10 p-8">
          <div className="rounded-3xl border border-violet-400/20 bg-gradient-to-br from-violet-500/10 via-white/[0.02] to-cyan-400/10 p-8">
            <div className="grid gap-8 lg:grid-cols-[1fr_auto]">
              <div>
                <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-violet-400/25 bg-violet-400/10 px-3 py-1.5 text-xs text-violet-300">
                  <Sparkles size={11} />
                  MCP Integration
                </div>
                <h2 className="text-2xl font-semibold text-slate-50">Bring your own LLM</h2>
                <p className="mt-3 max-w-lg text-sm leading-7 text-slate-400">
                  Connect any MCP-compatible AI client directly to your indexed documents. Ask meaningful questions and get answers grounded in real page evidence. MiraDocs acts as the memory and retrieval layer your AI doesn't have — so every answer comes with a source you can verify.
                </p>
                <div className="mt-5 flex flex-wrap gap-2">
                  {llmClients.map((name) => (
                    <span
                      key={name}
                      className="rounded-full border border-white/10 bg-white/[0.05] px-3 py-1 text-xs text-slate-300"
                    >
                      {name}
                    </span>
                  ))}
                </div>
              </div>
              <div className="flex items-center justify-center lg:justify-end">
                <div className="flex h-20 w-20 items-center justify-center rounded-3xl border border-violet-400/25 bg-violet-400/10 text-violet-200">
                  <Bot size={36} />
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Workspace areas */}
        <div className="p-8">
          <p className="mb-8 text-xs uppercase tracking-[0.35em] text-slate-500">Workspace</p>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {features.map((f) => {
              const Icon = f.icon;
              return (
                <div
                  key={f.label}
                  className="rounded-3xl border border-white/10 bg-white/[0.03] p-6 transition hover:border-emerald-300/20 hover:bg-white/[0.05]"
                >
                  <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-2xl border border-emerald-300/20 bg-emerald-300/10 text-emerald-200">
                    <Icon size={18} />
                  </div>
                  <h3 className="mb-2 font-semibold text-slate-100">{f.label}</h3>
                  <p className="text-sm leading-6 text-slate-400">{f.desc}</p>
                </div>
              );
            })}
          </div>
        </div>

      </section>
    </main>
  );
}
