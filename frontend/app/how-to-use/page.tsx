import {
  ArrowLeft,
  ArrowRight,
  Bot,
  CircleAlert,
  Database,
  FileSearch,
  GitCompareArrows,
  Info,
  Play,
  Search,
  Sparkles,
  Tags,
  Terminal,
  UploadCloud,
  Zap,
} from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "How to use | MiraDocs",
  description: "Operator guide for uploading, processing, tagging, inspecting, indexing, and searching documents.",
};

const workflow = [
  {
    step: "01",
    title: "Upload",
    icon: UploadCloud,
    text: "Drop any PDF, DOCX, or PPTX into the Library. The document is registered instantly and ready to process.",
  },
  {
    step: "02",
    title: "Process",
    icon: Play,
    text: "Run the extraction pipeline and watch real-time progress, ETA, live logs, and run history as each step completes.",
  },
  {
    step: "03",
    title: "Tag",
    icon: Tags,
    text: "Add up to five custom tags to organise your library. Tags are available before and after processing.",
  },
  {
    step: "04",
    title: "Inspect",
    icon: FileSearch,
    text: "Review extracted page images, quality signals, tables, and figures. Jump directly to any page number.",
  },
  {
    step: "05",
    title: "Index",
    icon: Database,
    text: "Index processed chunks into the local vector store, then run Hybrid Search with page-level evidence.",
  },
  {
    step: "06",
    title: "Compare",
    icon: GitCompareArrows,
    text: "Select two processed documents to open a side-by-side evidence view with keyword overlays and match navigation.",
  },
];

const tips = [
  { icon: Info, text: "Tag is available before processing; Inspect and Index unlock after the pipeline completes." },
  { icon: Info, text: "A run with zero tables or figures is still a completed, valid pipeline state." },
  { icon: Info, text: "Switching documents mid-pipeline is safe — progress and logs restore when you return." },
  { icon: Info, text: "Library search matches filename, ID, status, domain, sensitivity, document type, and tags." },
  { icon: Info, text: "Hybrid Search results are document-scoped and include page evidence for source verification." },
  { icon: Info, text: "Cross Search and Compare require exactly two documents selected in the Library." },
];

const MCP_PATH = "/path/to/miradocs";
const MCP_PYTHON = `${MCP_PATH}/.venv/bin/python`;

const mcpConfigs: { label: string; lang: string; code: string }[] = [
  {
    label: "Claude Code",
    lang: ".claude/settings.json",
    code: JSON.stringify({ mcpServers: { miradocs: { type: "stdio", command: MCP_PYTHON, args: ["-m", "src.mcp.server"], cwd: MCP_PATH, env: {} } } }, null, 2),
  },
  {
    label: "Claude Desktop",
    lang: "claude_desktop_config.json",
    code: JSON.stringify({ mcpServers: { miradocs: { command: "bash", args: ["-c", `cd ${MCP_PATH} && .venv/bin/python -m src.mcp.server`] } } }, null, 2),
  },
  {
    label: "Cursor",
    lang: ".cursor/mcp.json",
    code: JSON.stringify({ mcpServers: { miradocs: { command: MCP_PYTHON, args: ["-m", "src.mcp.server"], cwd: MCP_PATH } } }, null, 2),
  },
  {
    label: "Windsurf",
    lang: "~/.codeium/windsurf/mcp_config.json",
    code: JSON.stringify({ mcpServers: { miradocs: { command: MCP_PYTHON, args: ["-m", "src.mcp.server"], cwd: MCP_PATH } } }, null, 2),
  },
  {
    label: "Gemini CLI",
    lang: "~/.gemini/settings.json",
    code: JSON.stringify({ mcpServers: { miradocs: { command: MCP_PYTHON, args: ["-m", "src.mcp.server"], cwd: MCP_PATH, env: {} } } }, null, 2),
  },
  {
    label: "OpenAI Codex CLI",
    lang: "~/.codex/config.toml",
    code: `[mcp_servers.miradocs]\ncommand = "${MCP_PYTHON}"\nargs    = ["-m", "src.mcp.server"]\ncwd     = "${MCP_PATH}"`,
  },
];

const mcpTools = [
  { name: "search_docs", desc: "Semantic / keyword search across indexed documents." },
  { name: "list_documents", desc: "List all documents with status, type, and page count." },
  { name: "get_document_info", desc: "Section structure, quality, and entity summary." },
  { name: "get_page_evidence", desc: "Full text, tables, figures, and image path for a page." },
  { name: "get_page_matches", desc: "Keyword match boxes for PDF page image highlights." },
  { name: "get_section_content", desc: "All chunks and tables within a named section." },
  { name: "get_entities", desc: "AWS services, CIDRs, environments, and governance terms." },
  { name: "get_pipeline_status", desc: "Pipeline steps, active run, events, and run history." },
  { name: "get_index_status", desc: "Chunk/index status and reindex recommendation." },
  { name: "detect_compare_mode", desc: "Suggest the best compare mode for two documents." },
  { name: "list_compare_runs", desc: "List existing compare runs for a document." },
  { name: "get_compare_run", desc: "Read an existing compare run and its findings." },
  { name: "put_cross_search", desc: "Side-by-side Cross Search across two documents." },
  { name: "put_compare", desc: "Create a deterministic compare run for two documents." },
];

const primaryPath = ["Library", "Process", "Tag", "Inspect", "Index", "Search"];

export default function HowToUsePage() {
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
        <div className="relative overflow-hidden border-b border-white/10 px-8 py-14">
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-cyan-500/8 via-transparent to-violet-600/8" />
          <div className="pointer-events-none absolute -left-16 -top-16 h-64 w-64 rounded-full bg-cyan-400/10 blur-3xl" />
          <div className="relative">
            <p className="mb-4 text-xs uppercase tracking-[0.35em] text-cyan-200/60">Operator guide</p>
            <h1 className="text-5xl font-semibold tracking-tight text-slate-50">
              How to use{" "}
              <span className="bg-gradient-to-r from-cyan-300 to-violet-400 bg-clip-text text-transparent">
                MiraDocs
              </span>
            </h1>
            <p className="mt-4 max-w-xl text-base leading-7 text-slate-400">
              Work each document through a clear lifecycle — from upload to AI-powered search — in six straightforward steps.
            </p>

            {/* Primary path flow */}
            <div className="mt-8 flex flex-wrap items-center gap-2">
              {primaryPath.map((label, i) => (
                <div key={label} className="flex items-center gap-2">
                  <span className="rounded-full border border-cyan-300/20 bg-cyan-300/10 px-3 py-1 text-xs font-medium text-cyan-200">
                    {label}
                  </span>
                  {i < primaryPath.length - 1 && (
                    <ArrowRight size={12} className="text-slate-600" />
                  )}
                </div>
              ))}
              <ArrowRight size={12} className="text-slate-600" />
              <span className="rounded-full border border-violet-400/20 bg-violet-400/10 px-3 py-1 text-xs font-medium text-violet-300">
                Ask your LLM
              </span>
            </div>
          </div>
        </div>

        {/* Workflow steps */}
        <div className="border-b border-white/10 p-8">
          <p className="mb-8 text-xs uppercase tracking-[0.35em] text-slate-500">Workflow</p>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {workflow.map((step) => {
              const Icon = step.icon;
              return (
                <div
                  key={step.step}
                  className="group rounded-3xl border border-white/10 bg-white/[0.03] p-6 transition hover:border-cyan-300/20 hover:bg-white/[0.055]"
                >
                  <div className="mb-4 flex items-center justify-between">
                    <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-cyan-300/20 to-violet-500/20 text-cyan-200">
                      <Icon size={18} />
                    </div>
                    <span className="text-3xl font-bold text-white/[0.06]">{step.step}</span>
                  </div>
                  <h3 className="mb-2 font-semibold text-slate-100">{step.title}</h3>
                  <p className="text-sm leading-6 text-slate-400">{step.text}</p>
                </div>
              );
            })}
          </div>
        </div>

        {/* Tips */}
        <div className="border-b border-white/10 p-8">
          <p className="mb-6 text-xs uppercase tracking-[0.35em] text-slate-500">Tips & gotchas</p>
          <div className="grid gap-3 sm:grid-cols-2">
            {tips.map((tip, i) => (
              <div
                key={i}
                className="flex gap-3 rounded-2xl border border-white/10 bg-slate-950/30 p-4"
              >
                <Info size={14} className="mt-0.5 shrink-0 text-cyan-400/60" />
                <p className="text-sm leading-6 text-slate-300">{tip.text}</p>
              </div>
            ))}
          </div>
        </div>

        {/* MCP Integration */}
        <div className="p-8">
          {/* MCP header */}
          <div className="mb-8 rounded-3xl border border-violet-400/20 bg-gradient-to-r from-violet-500/10 to-cyan-400/10 p-6">
            <div className="flex items-start gap-4">
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-violet-400/25 bg-violet-400/10 text-violet-200">
                <Bot size={20} />
              </div>
              <div>
                <div className="mb-1 flex items-center gap-2">
                  <h2 className="text-lg font-semibold text-slate-50">MCP Integration</h2>
                  <span className="inline-flex items-center gap-1 rounded-full border border-violet-400/20 bg-violet-400/10 px-2 py-0.5 text-xs text-violet-300">
                    <Sparkles size={10} />
                    AI-powered
                  </span>
                </div>
                <p className="text-sm leading-6 text-slate-400">
                  Connect any MCP-compatible AI client to your indexed documents and ask meaningful questions grounded in real page evidence. Update{" "}
                  <code className="rounded bg-white/[0.07] px-1.5 py-0.5 text-xs text-cyan-200">/path/to/miradocs</code>{" "}
                  to your local checkout path.
                </p>
              </div>
            </div>
          </div>

          <div className="grid gap-8 lg:grid-cols-[1.1fr_0.9fr]">
            {/* Config blocks */}
            <div className="space-y-3">
              <p className="text-xs uppercase tracking-[0.28em] text-slate-500">Client configuration</p>
              {mcpConfigs.map((cfg) => (
                <details
                  key={cfg.label}
                  className="group rounded-2xl border border-white/10 bg-slate-950/40 open:border-violet-400/20"
                >
                  <summary className="flex cursor-pointer select-none items-center justify-between px-4 py-3 text-sm font-medium text-slate-200 group-open:text-violet-200">
                    <div className="flex items-center gap-2">
                      <Terminal size={13} className="text-slate-500 group-open:text-violet-400" />
                      {cfg.label}
                    </div>
                    <code className="ml-3 truncate text-xs text-slate-500">{cfg.lang}</code>
                  </summary>
                  <div className="border-t border-white/10 p-1">
                    <pre className="overflow-x-auto rounded-xl bg-black/40 p-4 text-xs leading-6 text-slate-300">
                      <code>{cfg.code}</code>
                    </pre>
                  </div>
                </details>
              ))}

              {/* Windows note */}
              <div className="flex gap-3 rounded-2xl border border-yellow-400/20 bg-yellow-400/5 px-4 py-3">
                <CircleAlert size={14} className="mt-0.5 shrink-0 text-yellow-400/70" />
                <p className="text-xs leading-6 text-yellow-200/80">
                  <span className="font-semibold text-yellow-200">Windows:</span> replace{" "}
                  <code className="text-yellow-100">command</code> with{" "}
                  <code className="text-yellow-100">.venv\Scripts\python.exe</code> and use backslashes in{" "}
                  <code className="text-yellow-100">cwd</code>, or use a WSL path.
                </p>
              </div>

              {/* Transport note */}
              <div className="flex gap-3 rounded-2xl border border-cyan-300/15 bg-cyan-300/5 px-4 py-3">
                <Zap size={14} className="mt-0.5 shrink-0 text-cyan-400/70" />
                <p className="text-xs leading-6 text-cyan-200/80">
                  MiraDocs uses <span className="font-semibold text-cyan-200">stdio transport</span> — your AI client spawns it per-connection. No port, no background process.
                </p>
              </div>
            </div>

            {/* MCP Tools */}
            <div className="space-y-3">
              <p className="text-xs uppercase tracking-[0.28em] text-slate-500">Available tools</p>
              <div className="grid gap-2">
                {mcpTools.map((tool) => (
                  <div
                    key={tool.name}
                    className="rounded-2xl border border-white/10 bg-slate-950/30 px-4 py-3 transition hover:border-violet-400/20"
                  >
                    <code className="text-xs font-semibold text-violet-300">{tool.name}</code>
                    <p className="mt-0.5 text-xs leading-5 text-slate-400">{tool.desc}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

      </section>
    </main>
  );
}
