"use client";

import { ArrowLeft, ExternalLink, FileText, Loader2, Maximize2, Search, X } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { ImageLightbox } from "@/components/ui/image-lightbox";
import { pageImageUrl } from "@/lib/api";
import type { DocumentRecord, SearchResult } from "@/lib/types";

type CrossDocumentSearchViewProps = {
  leftDoc: DocumentRecord;
  rightDoc: DocumentRecord;
  query: string;
  setQuery: (query: string) => void;
  hybrid: boolean;
  setHybrid: (value: boolean) => void;
  rerank: boolean;
  setRerank: (value: boolean) => void;
  onSearch: () => void;
  isSearching: boolean;
  results: SearchResult[];
  error?: string | null;
  onClose: () => void;
};

export function CrossDocumentSearchView({
  leftDoc,
  rightDoc,
  query,
  setQuery,
  hybrid,
  setHybrid,
  rerank,
  setRerank,
  onSearch,
  isSearching,
  results,
  error,
  onClose,
}: CrossDocumentSearchViewProps) {
  const [leftSelectedId, setLeftSelectedId] = useState<string | null>(null);
  const [rightSelectedId, setRightSelectedId] = useState<string | null>(null);
  const [largePageImage, setLargePageImage] = useState<{ src: string; title: string; docId: string; page: number } | null>(null);

  const leftResults = useMemo(() => results.filter((result) => result.doc_id === leftDoc.doc_id), [leftDoc.doc_id, results]);
  const rightResults = useMemo(() => results.filter((result) => result.doc_id === rightDoc.doc_id), [rightDoc.doc_id, results]);

  useEffect(() => {
    if (!leftResults.length) {
      setLeftSelectedId(null);
    } else if (!leftResults.some((result) => resultKey(result) === leftSelectedId)) {
      setLeftSelectedId(resultKey(leftResults[0]));
    }
    if (!rightResults.length) {
      setRightSelectedId(null);
    } else if (!rightResults.some((result) => resultKey(result) === rightSelectedId)) {
      setRightSelectedId(resultKey(rightResults[0]));
    }
  }, [leftResults, leftSelectedId, rightResults, rightSelectedId]);

  const leftSelected = leftResults.find((result) => resultKey(result) === leftSelectedId) ?? leftResults[0] ?? null;
  const rightSelected = rightResults.find((result) => resultKey(result) === rightSelectedId) ?? rightResults[0] ?? null;
  const canSearch = query.trim().length > 0;

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="shrink-0 rounded-2xl border border-white/10 bg-white/[0.035] p-4">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="mb-1 flex items-center gap-2 text-xs uppercase tracking-[0.22em] text-cyan-200/70">
              <Search size={14} /> Cross-document search
            </p>
            <h2 className="text-lg font-semibold text-slate-100">Side-by-side evidence review</h2>
            <p className="mt-1 truncate text-sm text-slate-400">
              {leftDoc.filename} vs {rightDoc.filename}
            </p>
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
              aria-label="Close cross-document search"
              title="Close cross-document search"
            >
              <X size={17} />
            </button>
          </div>
        </div>

        <div className="grid gap-3 xl:grid-cols-[1fr_auto]">
          <div className="flex min-w-0 gap-2">
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && canSearch && onSearch()}
              placeholder="Search both documents for architecture evidence"
              className="min-w-0 flex-1 rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-slate-200 outline-none focus:border-cyan-300/60"
            />
            <button
              type="button"
              onClick={onSearch}
              disabled={!canSearch || isSearching}
              className="flex items-center gap-2 rounded-2xl bg-white px-4 py-3 font-medium text-slate-950 transition hover:scale-[1.01] disabled:cursor-not-allowed disabled:opacity-40"
            >
              {isSearching && <Loader2 size={16} className="animate-spin" />}
              Search
            </button>
          </div>
          <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-white/10 bg-black/20 px-3 py-2">
            <label className="flex items-center gap-2 text-sm text-slate-400">
              <input
                type="checkbox"
                checked={hybrid}
                onChange={(event) => setHybrid(event.target.checked)}
                className="accent-cyan-300"
              />
              Hybrid
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-400">
              <input
                type="checkbox"
                checked={rerank}
                onChange={(event) => setRerank(event.target.checked)}
                className="accent-violet-400"
              />
              Rerank
            </label>
          </div>
        </div>
        {error && <p className="mt-3 rounded-xl border border-red-400/25 bg-red-500/10 px-3 py-2 text-sm text-red-100">{error}</p>}
      </div>

      <div className="grid min-h-0 flex-1 gap-4 xl:grid-cols-2">
        <DocumentSearchLane
          doc={leftDoc}
          query={query}
          results={leftResults}
          selected={leftSelected}
          onSelect={(result) => setLeftSelectedId(resultKey(result))}
          isSearching={isSearching}
          onOpenPage={(result, page) =>
            setLargePageImage({
              src: pageImageUrl(result.doc_id, page),
              title: `${leftDoc.filename} - page ${page}`,
              docId: result.doc_id,
              page,
            })
          }
        />
        <DocumentSearchLane
          doc={rightDoc}
          query={query}
          results={rightResults}
          selected={rightSelected}
          onSelect={(result) => setRightSelectedId(resultKey(result))}
          isSearching={isSearching}
          onOpenPage={(result, page) =>
            setLargePageImage({
              src: pageImageUrl(result.doc_id, page),
              title: `${rightDoc.filename} - page ${page}`,
              docId: result.doc_id,
              page,
            })
          }
        />
      </div>

      {largePageImage && (
        <ImageLightbox
          src={largePageImage.src}
          alt={largePageImage.title}
          title={largePageImage.title}
          docId={largePageImage.docId}
          pageNum={largePageImage.page}
          query={query}
          onClose={() => setLargePageImage(null)}
        />
      )}
    </div>
  );
}

function DocumentSearchLane({
  doc,
  query,
  results,
  selected,
  onSelect,
  isSearching,
  onOpenPage,
}: {
  doc: DocumentRecord;
  query: string;
  results: SearchResult[];
  selected: SearchResult | null;
  onSelect: (result: SearchResult) => void;
  isSearching: boolean;
  onOpenPage: (result: SearchResult, page: number) => void;
}) {
  const selectedPage = selected?.evidence?.page_number ?? selected?.page_start ?? 0;
  const selectedSection = selected?.evidence?.section_path || selected?.section_path;

  return (
    <section className="grid min-h-0 gap-3 rounded-2xl border border-white/10 bg-white/[0.03] p-3 lg:grid-cols-[minmax(220px,0.58fr)_minmax(0,1.42fr)]">
      <div className="flex min-h-0 flex-col">
        <div className="shrink-0 border-b border-white/10 pb-3">
          <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Document</p>
          <h3 className="mt-1 line-clamp-2 text-sm font-semibold leading-5 text-slate-100">{doc.filename}</h3>
          <p className="mt-1 text-xs text-slate-500">{results.length} result{results.length === 1 ? "" : "s"}</p>
        </div>
        <div className="thin-scrollbar min-h-0 flex-1 space-y-2 overflow-y-auto pt-3">
          {results.length === 0 ? (
            <p className="rounded-xl border border-dashed border-white/10 bg-black/20 px-3 py-6 text-center text-sm text-slate-500">
              {isSearching ? "Searching..." : "No hits for this document yet."}
            </p>
          ) : (
            results.map((result, index) => {
              const isSelected = selected ? resultKey(selected) === resultKey(result) : false;
              return (
                <button
                  key={resultKey(result)}
                  type="button"
                  onClick={() => onSelect(result)}
                  className={`w-full rounded-xl border p-3 text-left transition ${
                    isSelected
                      ? "border-cyan-300/60 bg-cyan-300/10"
                      : "border-white/10 bg-black/20 hover:border-white/25 hover:bg-white/[0.05]"
                  }`}
                >
                  <div className="mb-2 flex items-center justify-between gap-2 text-xs text-slate-500">
                    <span className="font-mono text-cyan-200/80">#{index + 1}</span>
                    <span>page {result.page_start}</span>
                  </div>
                  <p className="line-clamp-3 text-sm leading-5 text-slate-200">
                    <HighlightedText text={result.text} query={query} />
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-slate-500">
                    <span className="rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5">{result.chunk_type}</span>
                    {result.hybrid_score != null && <span>H {result.hybrid_score.toFixed(3)}</span>}
                    {result.rerank_score != null && <span className="text-violet-300">R {result.rerank_score.toFixed(1)}</span>}
                    {result.hybrid_score == null && <span>{result.score.toFixed(3)}</span>}
                  </div>
                </button>
              );
            })
          )}
        </div>
      </div>

      <div className="min-h-0 overflow-hidden rounded-xl border border-white/10 bg-black/25">
        {!selected ? (
          <div className="flex h-full min-h-[260px] items-center justify-center px-6 text-center text-sm text-slate-500">
            Select a result to review this document side.
          </div>
        ) : (
          <div className="flex h-full min-h-0 flex-col">
            <div className="shrink-0 border-b border-white/10 p-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="mb-1 flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-cyan-200/70">
                    <FileText size={13} /> Page {selectedPage || selected.page_start}
                  </p>
                  <p className="text-xs text-slate-400 [overflow-wrap:anywhere]">{selectedSection}</p>
                </div>
                {selectedPage > 0 && (
                  <button
                    type="button"
                    onClick={() => onOpenPage(selected, selectedPage)}
                    className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/[0.04] text-slate-300 transition hover:border-cyan-300/40 hover:text-cyan-100"
                    aria-label={`Open ${doc.filename} page ${selectedPage} larger`}
                    title="Open larger"
                  >
                    <Maximize2 size={15} />
                  </button>
                )}
              </div>
            </div>
            <div className="thin-scrollbar min-h-0 flex-1 overflow-y-auto">
              {selectedPage > 0 && (
                <div className="border-b border-white/10 bg-slate-950/50 p-3">
                  <button
                    type="button"
                    onClick={() => onOpenPage(selected, selectedPage)}
                    className="group relative flex h-[360px] max-h-[52vh] min-h-[280px] w-full items-center justify-center overflow-hidden rounded-xl border border-white/10 bg-slate-950/80 transition hover:border-cyan-300/40"
                    aria-label={`Open ${doc.filename} page ${selectedPage} larger`}
                  >
                    <img
                      src={pageImageUrl(selected.doc_id, selectedPage)}
                      alt={`${doc.filename} page ${selectedPage}`}
                      className="h-full w-full object-contain"
                    />
                    <span className="absolute right-3 top-3 flex items-center gap-2 rounded-lg border border-white/10 bg-slate-950/85 px-2 py-1 text-xs font-medium text-slate-200 opacity-90 shadow-lg transition group-hover:border-cyan-300/35 group-hover:text-cyan-100">
                      <ExternalLink size={13} />
                      Larger
                    </span>
                  </button>
                </div>
              )}
              <div className="p-3">
                <p className="mb-2 text-xs uppercase tracking-[0.2em] text-slate-500">Matched passage</p>
                <div className="mb-4 max-h-[180px] overflow-auto rounded-xl border border-white/10 bg-slate-950/45 p-3 text-sm leading-6 text-slate-200 whitespace-pre-wrap [overflow-wrap:anywhere]">
                  <HighlightedText text={selected.text} query={query} />
                </div>
                {selected.evidence?.nearby_text && (
                  <>
                    <p className="mb-2 text-xs uppercase tracking-[0.2em] text-slate-500">Nearby page text</p>
                    <div className="mb-4 max-h-[260px] overflow-auto rounded-xl border border-cyan-300/15 bg-cyan-300/[0.045] p-3 text-sm leading-6 text-slate-200 whitespace-pre-wrap [overflow-wrap:anywhere]">
                      <HighlightedText text={selected.evidence.nearby_text} query={query} />
                    </div>
                  </>
                )}
                {selectedPage <= 0 && (
                  <p className="rounded-xl border border-dashed border-white/10 bg-black/20 px-3 py-6 text-center text-sm text-slate-500">
                    No page image is available for this result.
                  </p>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

function resultKey(result: SearchResult) {
  return `${result.doc_id}:${result.chunk_id}`;
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
