"use client";

import { ArrowLeft, ArrowLeftRight, ArrowRight, CheckCircle2, ExternalLink, Filter, GitCompareArrows, Loader2, Maximize2, X } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";

import { ImageLightbox } from "@/components/ui/image-lightbox";
import { pageImageUrl } from "@/lib/api";
import type {
  CompareEvidence,
  CompareFinding,
  CompareMode,
  CompareModeDetection,
  CompareResult,
  DocumentRecord,
} from "@/lib/types";

const COMPARE_MODES: Array<{ value: CompareMode; label: string }> = [
  { value: "auto", label: "Auto detect" },
  { value: "hld_lld", label: "HLD vs LLD" },
  { value: "requirements_design", label: "Requirements vs Design" },
  { value: "requirements_test", label: "Requirements vs Test" },
  { value: "policy_architecture", label: "Policy vs Architecture" },
  { value: "sow_design", label: "SOW vs Design" },
  { value: "version_diff", label: "Version diff" },
  { value: "generic_diff", label: "Generic diff" },
];

const severityStyles: Record<string, string> = {
  high: "border-red-300/45 bg-red-500/10 text-red-100",
  medium: "border-amber-300/45 bg-amber-500/10 text-amber-100",
  low: "border-cyan-300/35 bg-cyan-500/10 text-cyan-100",
};

const DIFF_TERM_STOPWORDS = new Set([
  "and", "are", "but", "for", "from", "has", "have", "into", "its", "not", "the", "this", "that", "with",
  "source", "target", "evidence", "document", "page", "section", "missing", "extra", "different", "differs",
]);

type CompareViewProps = {
  sourceDoc: DocumentRecord;
  targetDoc: DocumentRecord;
  detection: CompareModeDetection | null;
  mode: CompareMode;
  setMode: (mode: CompareMode) => void;
  onDetect: () => void;
  onRun: () => void;
  onSwap: () => void;
  onClose: () => void;
  isDetecting: boolean;
  isRunning: boolean;
  result: CompareResult | null;
  error?: string | null;
};

export function CompareView({
  sourceDoc,
  targetDoc,
  detection,
  mode,
  setMode,
  onDetect,
  onRun,
  onSwap,
  onClose,
  isDetecting,
  isRunning,
  result,
  error,
}: CompareViewProps) {
  const [severityFilter, setSeverityFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [selectedFindingId, setSelectedFindingId] = useState<string | null>(null);
  const [lightbox, setLightbox] = useState<{ src: string; title: string; docId: string; page: number; query: string } | null>(null);

  const findings = result?.findings ?? [];
  const types = useMemo(() => Array.from(new Set(findings.map((finding) => finding.type))).sort(), [findings]);
  const filteredFindings = useMemo(() => {
    return findings.filter((finding) => {
      const severityMatch = severityFilter === "all" || finding.severity === severityFilter;
      const typeMatch = typeFilter === "all" || finding.type === typeFilter;
      return severityMatch && typeMatch;
    });
  }, [findings, severityFilter, typeFilter]);
  const selectedFinding = useMemo(() => {
    return filteredFindings.find((finding) => finding.finding_id === selectedFindingId) ?? filteredFindings[0] ?? null;
  }, [filteredFindings, selectedFindingId]);
  const summary = result?.summary ?? result?.run.summary ?? {};
  const selectedModeLabel = COMPARE_MODES.find((item) => item.value === mode)?.label ?? mode;
  const detectedModeLabel = COMPARE_MODES.find((item) => item.value === detection?.detected_mode)?.label ?? detection?.detected_mode;
  const selectedDiffQuery = useMemo(() => selectedFinding ? diffQueryForFinding(selectedFinding) : "", [selectedFinding]);

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="shrink-0 rounded-2xl border border-white/10 bg-white/[0.035] p-4">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-emerald-300/30 bg-emerald-300/10 text-emerald-100">
              <GitCompareArrows size={20} />
            </span>
            <div className="min-w-0">
              <h2 className="text-lg font-semibold text-slate-100">Compare</h2>
              <p className="mt-0.5 truncate text-sm text-slate-400">
                {sourceDoc.filename} vs {targetDoc.filename}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="flex h-10 items-center gap-2 rounded-xl border border-cyan-300/25 bg-cyan-300/10 px-3 text-sm font-medium text-cyan-100 transition hover:border-cyan-300/55 hover:bg-cyan-300/15"
            >
              <ArrowLeft size={16} />
              Back to workspace
            </button>
            <button
              type="button"
              onClick={onClose}
              className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-white/[0.04] text-slate-300 transition hover:border-cyan-300/40 hover:text-cyan-100"
              aria-label="Close compare"
              title="Close compare"
            >
              <X size={17} />
            </button>
          </div>
        </div>

        <div className="grid gap-3 lg:grid-cols-[1fr_auto_1fr]">
          <DocumentCompareCard label="Source" doc={sourceDoc} />
          <div className="flex items-center justify-center">
            <button
              type="button"
              onClick={onSwap}
              disabled={isDetecting || isRunning}
              title="Swap source and target"
              className="group flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-white/[0.04] text-slate-400 transition hover:border-emerald-300/50 hover:bg-emerald-300/10 hover:text-emerald-100 disabled:cursor-not-allowed disabled:opacity-50"
              aria-label="Swap source and target documents"
            >
              <ArrowLeftRight size={17} className="lg:hidden" />
              <ArrowRight size={17} className="hidden transition group-hover:translate-x-0.5 lg:block" />
            </button>
          </div>
          <DocumentCompareCard label="Target" doc={targetDoc} />
        </div>

        <div className="mt-4 grid gap-3 xl:grid-cols-[minmax(220px,320px)_1fr_auto]">
          <label className="block">
            <span className="mb-1.5 block text-xs font-medium uppercase tracking-[0.2em] text-slate-500">Mode</span>
            <select
              value={mode}
              onChange={(event) => setMode(event.target.value as CompareMode)}
              className="h-11 w-full rounded-xl border border-white/10 bg-slate-950/80 px-3 text-sm text-slate-100 outline-none transition focus:border-emerald-300/60"
            >
              {COMPARE_MODES.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <div className="rounded-xl border border-white/10 bg-black/20 px-3 py-2">
            <div className="flex flex-wrap items-center gap-2 text-sm text-slate-300">
              {isDetecting ? (
                <>
                  <Loader2 size={15} className="animate-spin text-emerald-200" />
                  Detecting compare mode
                </>
              ) : detection ? (
                <>
                  <CheckCircle2 size={15} className="text-emerald-200" />
                  Suggested: <span className="font-medium text-emerald-100">{detectedModeLabel}</span>
                  <span className="text-slate-500">({Math.round(detection.confidence * 100)}%)</span>
                </>
              ) : (
                <span className="text-slate-500">Select exactly two processed documents to compare.</span>
              )}
            </div>
            {detection?.reasons?.length ? (
              <p className="mt-1 text-xs text-slate-500">{detection.reasons.join(", ")}</p>
            ) : null}
          </div>
          <div className="flex items-end gap-2">
            <button
              type="button"
              onClick={onDetect}
              disabled={isDetecting}
              className="h-11 rounded-xl border border-white/10 bg-white/[0.04] px-4 text-sm font-medium text-slate-200 transition hover:border-emerald-300/40 hover:text-emerald-100 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Detect
            </button>
            <button
              type="button"
              onClick={onRun}
              disabled={isRunning}
              className="flex h-11 items-center gap-2 rounded-xl bg-emerald-300 px-4 text-sm font-semibold text-slate-950 transition hover:bg-emerald-200 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isRunning && <Loader2 size={15} className="animate-spin" />}
              Run {selectedModeLabel}
            </button>
          </div>
        </div>
        {error && <p className="mt-3 rounded-xl border border-red-400/25 bg-red-500/10 px-3 py-2 text-sm text-red-100">{error}</p>}
      </div>

      <div className="grid min-h-0 flex-1 gap-4 xl:grid-cols-[minmax(360px,0.92fr)_1.08fr]">
        <div className="flex min-h-0 flex-col rounded-2xl border border-white/10 bg-white/[0.03]">
          <div className="shrink-0 border-b border-white/10 p-4">
            <div className="mb-3 grid grid-cols-3 gap-2">
              {(["high", "medium", "low"] as const).map((severity) => (
                <button
                  key={severity}
                  type="button"
                  onClick={() => setSeverityFilter(severityFilter === severity ? "all" : severity)}
                  className={`rounded-xl border px-3 py-2 text-left transition ${
                    severityFilter === severity ? severityStyles[severity] : "border-white/10 bg-black/20 text-slate-400 hover:border-white/20"
                  }`}
                >
                  <span className="block text-lg font-semibold">{summary.by_severity?.[severity] ?? 0}</span>
                  <span className="text-xs capitalize">{severity}</span>
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <Filter size={15} className="text-slate-500" />
              <select
                value={typeFilter}
                onChange={(event) => setTypeFilter(event.target.value)}
                className="h-9 min-w-0 flex-1 rounded-xl border border-white/10 bg-slate-950/80 px-3 text-sm text-slate-200 outline-none focus:border-emerald-300/50"
              >
                <option value="all">All finding types</option>
                {types.map((type) => (
                  <option key={type} value={type}>
                    {type.replaceAll("_", " ")}
                  </option>
                ))}
              </select>
              <span className="text-xs text-slate-500">{filteredFindings.length}/{summary.total ?? findings.length}</span>
            </div>
          </div>
          <div className="thin-scrollbar min-h-0 flex-1 overflow-y-auto p-3">
            {filteredFindings.length === 0 ? (
              <div className="rounded-xl border border-dashed border-white/10 bg-black/20 p-5 text-sm text-slate-500">
                {result ? "No findings match the current filters." : "Run compare to see section, entity, value, topic, and table differences."}
              </div>
            ) : (
              filteredFindings.map((finding) => (
                <button
                  key={finding.finding_id}
                  type="button"
                  onClick={() => setSelectedFindingId(finding.finding_id)}
                  className={`mb-2 w-full rounded-xl border p-3 text-left transition ${
                    selectedFinding?.finding_id === finding.finding_id
                      ? "border-emerald-300/50 bg-emerald-300/10"
                      : "border-white/10 bg-black/20 hover:border-white/25 hover:bg-white/[0.05]"
                  }`}
                >
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <span className={`rounded-full border px-2 py-0.5 text-[11px] font-medium capitalize ${severityStyles[finding.severity]}`}>
                      {finding.severity}
                    </span>
                    <span className="rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 text-[11px] text-slate-400">
                      {finding.type.replaceAll("_", " ")}
                    </span>
                  </div>
                  <p className="text-sm font-medium leading-5 text-slate-100">{finding.title}</p>
                  <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">{finding.description}</p>
                </button>
              ))
            )}
          </div>
        </div>

        <div className="min-h-0 rounded-2xl border border-white/10 bg-white/[0.03]">
          {selectedFinding ? (
            <div className="flex h-full min-h-0 flex-col">
              <div className="shrink-0 border-b border-white/10 p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Side-by-side diff evidence</p>
                <h3 className="mt-1 text-base font-semibold text-slate-100">{selectedFinding.title}</h3>
                <p className="mt-1 text-sm leading-6 text-slate-400">{selectedFinding.description}</p>
                {selectedDiffQuery && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {selectedDiffQuery.split(" ").slice(0, 8).map((term) => (
                      <span key={term} className="rounded-full border border-amber-300/20 bg-amber-300/10 px-2 py-0.5 text-[11px] text-amber-100">
                        {term}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <div className="grid min-h-0 flex-1 gap-3 p-3 lg:grid-cols-2">
                <EvidenceColumn
                  title="Source evidence"
                  doc={sourceDoc}
                  evidence={selectedFinding.source_evidence}
                  diffQuery={selectedDiffQuery}
                  onOpenPage={(evidence) =>
                    setLightbox({
                      src: pageImageUrl(evidence.doc_id, evidence.page),
                      title: `${sourceDoc.filename} - page ${evidence.page}`,
                      docId: evidence.doc_id,
                      page: evidence.page,
                      query: selectedDiffQuery,
                    })
                  }
                />
                <EvidenceColumn
                  title="Target evidence"
                  doc={targetDoc}
                  evidence={selectedFinding.target_evidence}
                  diffQuery={selectedDiffQuery}
                  onOpenPage={(evidence) =>
                    setLightbox({
                      src: pageImageUrl(evidence.doc_id, evidence.page),
                      title: `${targetDoc.filename} - page ${evidence.page}`,
                      docId: evidence.doc_id,
                      page: evidence.page,
                      query: selectedDiffQuery,
                    })
                  }
                />
              </div>
            </div>
          ) : (
            <div className="flex h-full items-center justify-center p-6 text-center text-sm text-slate-500">
              Select a finding to inspect source and target evidence.
            </div>
          )}
        </div>
      </div>

      {lightbox && (
        <ImageLightbox
          src={lightbox.src}
          alt={lightbox.title}
          title={lightbox.title}
          docId={lightbox.docId}
          pageNum={lightbox.page}
          query={lightbox.query}
          onClose={() => setLightbox(null)}
        />
      )}
    </div>
  );
}

function DocumentCompareCard({ label, doc }: { label: string; doc: DocumentRecord }) {
  return (
    <div className="min-w-0 rounded-xl border border-white/10 bg-black/20 p-3">
      <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">{label}</p>
      <p className="mt-1 truncate text-sm font-medium text-slate-100">{doc.filename}</p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        <span className="rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 text-[11px] text-slate-400">{doc.document_type}</span>
        {(doc.tags ?? []).slice(0, 3).map((tag) => (
          <span key={tag} className="rounded-full border border-emerald-300/20 bg-emerald-300/10 px-2 py-0.5 text-[11px] text-emerald-100">
            {tag}
          </span>
        ))}
      </div>
    </div>
  );
}

function EvidenceColumn({
  title,
  doc,
  evidence,
  diffQuery,
  onOpenPage,
}: {
  title: string;
  doc: DocumentRecord;
  evidence: CompareEvidence[];
  diffQuery: string;
  onOpenPage: (evidence: CompareEvidence) => void;
}) {
  const primaryEvidence = evidence.find((item) => item.page > 0) ?? evidence[0] ?? null;
  return (
    <div className="thin-scrollbar min-h-0 overflow-y-auto rounded-xl border border-white/10 bg-black/20">
      <div className="sticky top-0 z-10 border-b border-white/10 bg-slate-950/90 p-3 backdrop-blur">
        <p className="truncate text-sm font-medium text-slate-100">{title}</p>
        <p className="mt-0.5 truncate text-xs text-slate-500">{doc.filename}</p>
      </div>
      {evidence.length === 0 ? (
        <div className="p-3">
          <p className="rounded-xl border border-dashed border-white/10 p-4 text-sm text-slate-500">No direct evidence for {doc.filename}.</p>
        </div>
      ) : (
        <>
          {primaryEvidence && (
            <div className="border-b border-white/10 bg-slate-950/45 p-3">
              <div className="mb-2 flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate text-xs font-medium text-slate-300">{primaryEvidence.section_path || primaryEvidence.table_id || doc.filename}</p>
                  <p className="text-[11px] text-slate-500">Page {primaryEvidence.page}</p>
                </div>
                <button
                  type="button"
                  onClick={() => onOpenPage(primaryEvidence)}
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/[0.04] text-slate-300 transition hover:border-emerald-300/40 hover:text-emerald-100"
                  aria-label={`Open ${doc.filename} page ${primaryEvidence.page}`}
                  title="Open evidence image viewer"
                >
                  <Maximize2 size={14} />
                </button>
              </div>
              <button
                type="button"
                onClick={() => onOpenPage(primaryEvidence)}
                className="group relative flex h-[340px] max-h-[48vh] min-h-[260px] w-full items-center justify-center overflow-hidden rounded-xl border border-white/10 bg-slate-950/80 transition hover:border-emerald-300/45"
                aria-label={`Open ${doc.filename} page ${primaryEvidence.page} evidence image`}
              >
                <img
                  src={pageImageUrl(primaryEvidence.doc_id, primaryEvidence.page)}
                  alt={`${doc.filename} page ${primaryEvidence.page}`}
                  className="h-full w-full object-contain"
                />
                <span className="absolute right-3 top-3 flex items-center gap-2 rounded-lg border border-white/10 bg-slate-950/85 px-2 py-1 text-xs font-medium text-slate-200 opacity-90 shadow-lg transition group-hover:border-emerald-300/35 group-hover:text-emerald-100">
                  <ExternalLink size={13} />
                  Larger
                </span>
              </button>
            </div>
          )}
          <div className="space-y-3 p-3">
            {evidence.map((item, index) => (
              <div key={`${item.doc_id}-${item.page}-${index}`} className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-xs font-medium text-slate-300">{item.section_path || item.table_id || doc.filename}</p>
                    <p className="text-[11px] text-slate-500">Page {item.page}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => onOpenPage(item)}
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/[0.04] text-slate-300 transition hover:border-emerald-300/40 hover:text-emerald-100"
                    aria-label={`Open ${doc.filename} page ${item.page}`}
                  >
                    <ExternalLink size={14} />
                  </button>
                </div>
                <p className="whitespace-pre-wrap text-xs leading-5 text-slate-400">
                  <HighlightedText text={item.text || "Evidence page reference only."} query={diffQuery} />
                </p>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function diffQueryForFinding(finding: CompareFinding) {
  const text = [
    finding.title,
    finding.description,
    ...finding.source_evidence.map((item) => item.text),
    ...finding.target_evidence.map((item) => item.text),
  ].join(" ");
  const terms: string[] = [];
  for (const match of text.matchAll(/[A-Za-z0-9][A-Za-z0-9./:-]{2,}/g)) {
    const term = match[0].toLowerCase().replace(/^[^a-z0-9]+|[^a-z0-9]+$/g, "");
    if (!term || DIFF_TERM_STOPWORDS.has(term) || terms.includes(term)) continue;
    terms.push(term);
    if (terms.length === 12) break;
  }
  return terms.join(" ");
}

function HighlightedText({ text, query }: { text: string; query: string }) {
  return <>{highlightQueryTerms(text, query)}</>;
}

function highlightQueryTerms(text: string, query: string): ReactNode[] | string {
  const terms = Array.from(
    new Set(
      query
        .split(/\s+/)
        .map((term) => term.trim())
        .filter((term) => term.length >= 2)
        .map((term) => term.toLowerCase()),
    ),
  );
  if (!text || terms.length === 0) return text;

  const pattern = new RegExp(`(${terms.map(escapeRegExp).join("|")})`, "gi");
  return text.split(pattern).map((part, index) =>
    terms.includes(part.toLowerCase()) ? (
      <mark key={`${part}-${index}`} className="rounded bg-amber-300/25 px-0.5 text-amber-100 ring-1 ring-amber-300/25">
        {part}
      </mark>
    ) : (
      part
    ),
  );
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
