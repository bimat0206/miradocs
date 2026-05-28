"use client";

import { Database, FileArchive, FileText, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { ImageLightbox } from "@/components/ui/image-lightbox";
import { StatusPill } from "@/components/ui/status-pill";
import { API_BASE, pageImageUrl } from "@/lib/api";
import type { DocumentRecord, IndexStatus, SearchResult } from "@/lib/types";

interface IndexViewProps {
  doc: DocumentRecord | null;
  indexStatus: IndexStatus | null;
  onIndex: () => void;
  isIndexing: boolean;
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  searchHybrid: boolean;
  setSearchHybrid: (value: boolean) => void;
  searchRerank: boolean;
  setSearchRerank: (value: boolean) => void;
  onSearch: () => void;
  isSearching: boolean;
  results: SearchResult[];
}

export function IndexView({
  doc,
  indexStatus,
  onIndex,
  isIndexing,
  searchQuery,
  setSearchQuery,
  searchHybrid,
  setSearchHybrid,
  searchRerank,
  setSearchRerank,
  onSearch,
  isSearching,
  results,
}: IndexViewProps) {
  const [selectedResultId, setSelectedResultId] = useState<string | null>(null);
  const [largePageImage, setLargePageImage] = useState<{ src: string; title: string } | null>(null);

  useEffect(() => {
    if (results.length === 0) {
      setSelectedResultId(null);
      return;
    }
    if (!results.some((result) => resultKey(result) === selectedResultId)) {
      setSelectedResultId(resultKey(results[0]));
    }
  }, [results, selectedResultId]);

  const selectedResult = useMemo(
    () => results.find((result) => resultKey(result) === selectedResultId) ?? results[0] ?? null,
    [results, selectedResultId],
  );
  const selectedPage = selectedResult?.evidence?.page_number ?? selectedResult?.page_start ?? 0;
  const canSearch = searchQuery.trim().length > 0;

  if (!doc) return <EmptyState title="No document selected" />;
  const canIndex = Boolean(indexStatus?.chunks_available);

  return (
    <div className="grid gap-5 xl:grid-cols-[0.85fr_1.15fr] lg:h-full lg:min-h-0 min-h-[500px]">
      <section className="flex flex-col gap-5 min-h-0">
        <div className="rounded-3xl border border-white/10 bg-white/[0.035] p-5 shrink-0">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h3 className="flex items-center gap-2 text-lg font-semibold">
              <Database size={18} /> Index Status
            </h3>
            <StatusPill status={indexStatus?.indexed ? "success" : indexStatus?.index_step?.status ?? "pending"} />
          </div>
          
<div className="grid grid-cols-2 gap-6 border-y border-white/10 py-4">
            <div>
              <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Chunks</p>
              <p className="mt-1 text-3xl font-semibold">{indexStatus?.chunks_count ?? 0}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Indexed</p>
              <p className="mt-1 text-3xl font-semibold">
                {indexStatus?.last_index_result?.indexed ?? (indexStatus?.indexed ? "yes" : "no")}
              </p>
            </div>
          </div>
          <div className="mt-4 space-y-2 text-sm text-slate-400">
            <p>
              Last indexed:{" "}
              <span className="text-slate-200">
                {indexStatus?.last_indexed_at
                  ? new Date(indexStatus.last_indexed_at).toLocaleString()
                  : "never"}
              </span>
            </p>
            <p>
              Adapter:{" "}
              <span className="text-slate-200">
                {String(indexStatus?.adapter?.collection ?? "qdrant")} ·{" "}
                {String(indexStatus?.adapter?.status ?? "unknown")}
              </span>
            </p>
            {indexStatus?.reindex_recommended && (
              <p className="text-amber-200">Chunks changed after last index. Re-index recommended.</p>
            )}
            {!indexStatus?.chunks_available && (
              <p className="text-amber-200">Run pipeline to trigger automatic indexing.</p>
            )}
          </div>
          <button
            disabled={!canIndex || isIndexing}
            onClick={onIndex}
            className="mt-4 flex w-full items-center justify-center gap-2 rounded-2xl border border-cyan-500/30 hover:border-cyan-400 hover:bg-cyan-500/5 px-4 py-3 font-medium text-cyan-300 disabled:cursor-not-allowed disabled:opacity-40 transition-all hover:scale-[1.01]"
          >
            <Database size={18} />
            {isIndexing ? "Indexing..." : indexStatus?.indexed ? "Manual Re-index" : "Manual Indexing"}
          </button>
        </div>

        <div className="rounded-3xl border border-white/10 bg-white/[0.035] p-5 flex flex-col min-h-0 flex-1">
          <h3 className="mb-4 text-lg font-semibold shrink-0">Export artifacts</h3>
          <div className="thin-scrollbar grid gap-3 overflow-y-auto pr-1 max-h-[300px] lg:max-h-none flex-1">
            {[
              "manifest",
              "structure",
              "quality",
              "chunks",
              "entities",
              "relations",
              "markdown",
              "tables",
              "figures",
            ].map((artifact) => (
              <a
                key={artifact}
                href={`${API_BASE}/api/documents/${doc.doc_id}/artifacts/${artifact}`}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-between rounded-2xl border border-white/10 bg-white/[0.03] p-3 text-sm text-slate-300 transition hover:bg-white/5 hover:border-white/20"
              >
                <span className="flex items-center gap-2">
                  <FileArchive size={16} /> {artifact}
                </span>
                <span className="text-cyan-200 font-medium">Open</span>
              </a>
            ))}
          </div>
        </div>
      </section>

      <section className="rounded-3xl border border-white/10 bg-slate-950/40 p-5 flex flex-col min-h-0">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3 shrink-0">
          <div>
            <h3 className="flex items-center gap-2 text-lg font-semibold">
              <Search size={18} /> Hybrid Search
            </h3>
            <p className="mt-1 text-sm text-slate-500">Current document evidence search</p>
          </div>
        </div>
        <div className="mb-3 grid gap-3 shrink-0 2xl:grid-cols-[1fr_auto]">
          <p className="rounded-2xl border border-white/10 bg-white/[0.035] px-3 py-2 text-sm text-slate-300">
            {doc.filename}
          </p>
          <div className="flex flex-wrap gap-3 rounded-2xl border border-white/10 bg-white/[0.035] px-3 py-2">
            <label className="flex items-center gap-2 text-sm text-slate-400 cursor-pointer">
              <input
                type="checkbox"
                checked={searchHybrid}
                onChange={(e) => setSearchHybrid(e.target.checked)}
                className="accent-cyan-300"
              />
              Hybrid
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-400 cursor-pointer">
              <input
                type="checkbox"
                checked={searchRerank}
                onChange={(e) => setSearchRerank(e.target.checked)}
                className="accent-violet-400"
              />
              Rerank
            </label>
          </div>
        </div>
        <div className="flex gap-2 shrink-0 mb-5">
          <input
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            onKeyDown={(e) => e.key === "Enter" && canSearch && onSearch()}
            placeholder="Search inside this document"
            className="flex-1 rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 outline-none focus:border-cyan-300/60 text-slate-200"
          />
          <button
            disabled={!canSearch || isSearching}
            onClick={onSearch}
            className="rounded-2xl bg-white px-4 py-3 font-medium text-slate-950 disabled:opacity-40 transition hover:scale-[1.01] cursor-pointer"
          >
            {isSearching ? "Searching" : "Search"}
          </button>
        </div>
        <div className="grid flex-1 min-h-0 gap-4 xl:grid-cols-[minmax(250px,0.82fr)_minmax(0,1.18fr)]">
          <div className="thin-scrollbar min-h-[240px] space-y-2 overflow-y-auto pr-1">
          {results.length === 0 ? (
            <p className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-8 text-center text-sm text-slate-500">
              {isSearching ? "Loading results..." : "No search results yet."}
            </p>
          ) : (
            results.map((result, index) => {
              const key = resultKey(result);
              const isSelected = selectedResult ? resultKey(selectedResult) === key : false;
              return (
              <button
                key={key}
                onClick={() => setSelectedResultId(key)}
                className={`w-full rounded-2xl border p-3 text-left transition ${
                  isSelected
                    ? "border-cyan-300/60 bg-cyan-300/10"
                    : "border-white/10 bg-white/[0.03] hover:border-white/25 hover:bg-white/[0.06]"
                }`}
              >
                <div className="mb-2 flex items-center justify-between gap-3 text-xs text-slate-500">
                  <span className="font-mono text-cyan-200/80">#{index + 1}</span>
                  <span>page {result.page_start}</span>
                </div>
                <p className="mb-2 truncate text-xs font-medium text-cyan-100">
                  {result.source_file || doc.filename}
                </p>
                <p className="line-clamp-3 text-sm leading-5 text-slate-200">{result.text}</p>
                <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
                  <span className="rounded-full border border-white/10 bg-black/20 px-2 py-0.5">
                    {result.chunk_type}
                  </span>
                  {result.hybrid_score != null && <span>H {result.hybrid_score.toFixed(3)}</span>}
                  {result.rerank_score != null && <span className="text-violet-300">R {result.rerank_score.toFixed(1)}</span>}
                  {result.hybrid_score == null && <span>{result.score.toFixed(3)}</span>}
                </div>
              </button>
              );
            })
          )}
          </div>

          <div className="min-h-[360px] overflow-hidden rounded-2xl border border-white/10 bg-black/25">
            {!selectedResult ? (
              <div className="flex h-full min-h-[320px] items-center justify-center px-6 text-center text-sm text-slate-500">
                Select a search result to inspect page content.
              </div>
            ) : (
              <div className="flex h-full min-h-0 flex-col">
                <div className="shrink-0 border-b border-white/10 p-4">
                  <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="mb-1 flex items-center gap-2 text-xs uppercase tracking-[0.22em] text-cyan-200/70">
                        <FileText size={14} /> Page content
                      </p>
                      <h4 className="text-lg font-semibold text-slate-50">
                        Page {selectedPage || selectedResult.page_start}
                      </h4>
                      <p className="mt-1 truncate text-sm text-cyan-100">
                        {selectedResult.source_file || doc.filename}
                      </p>
                    </div>
                    <div className="flex flex-wrap justify-end gap-2 text-xs">
                      <span className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-slate-300">
                        {selectedResult.chunk_type}
                      </span>
                      {selectedResult.hybrid_score != null && (
                        <span className="rounded-full border border-cyan-300/20 bg-cyan-300/10 px-2.5 py-1 text-cyan-100">
                          Hybrid {selectedResult.hybrid_score.toFixed(3)}
                        </span>
                      )}
                      {selectedResult.rerank_score != null && (
                        <span className="rounded-full border border-violet-300/20 bg-violet-300/10 px-2.5 py-1 text-violet-100">
                          Rerank {selectedResult.rerank_score.toFixed(1)}
                        </span>
                      )}
                    </div>
                  </div>
                  <p className="text-xs text-slate-400 [overflow-wrap:anywhere]">
                    {selectedResult.evidence?.section_path || selectedResult.section_path}
                  </p>
                </div>

                <div className="thin-scrollbar grid flex-1 min-h-0 gap-4 overflow-y-auto p-4 2xl:grid-cols-[minmax(0,1fr)_220px]">
                  <div className="space-y-4">
                    <div>
                      <p className="mb-2 text-xs uppercase tracking-[0.2em] text-slate-500">
                        Matched passage
                      </p>
                      <div className="max-h-[220px] overflow-auto rounded-xl border border-white/10 bg-slate-950/45 p-4 text-sm leading-6 text-slate-200 whitespace-pre-wrap [overflow-wrap:anywhere]">
                        {selectedResult.text}
                      </div>
                    </div>

                    {selectedResult.why_relevant && (
                      <div>
                        <p className="mb-2 text-xs uppercase tracking-[0.2em] text-slate-500">
                          Graph context
                        </p>
                        <div className="rounded-xl border border-violet-400/20 bg-violet-400/[0.06] p-3 text-xs leading-5 text-violet-200">
                          {selectedResult.why_relevant}
                        </div>
                      </div>
                    )}

                    {selectedResult.evidence?.nearby_text && (
                      <div>
                        <p className="mb-2 text-xs uppercase tracking-[0.2em] text-slate-500">
                          Nearby page text
                        </p>
                        <div className="max-h-[300px] overflow-auto rounded-xl border border-cyan-300/15 bg-cyan-300/[0.045] p-4 text-sm leading-6 text-slate-200 whitespace-pre-wrap [overflow-wrap:anywhere]">
                          {selectedResult.evidence.nearby_text}
                        </div>
                      </div>
                    )}

                    {(selectedResult.evidence?.caption || selectedResult.evidence?.ocr_text || selectedResult.evidence?.figure_number) && (
                      <div className="rounded-xl border border-white/10 bg-white/[0.035] p-4 text-sm text-slate-300">
                        {selectedResult.evidence?.figure_number && (
                          <p className="text-cyan-200">{selectedResult.evidence.figure_number}</p>
                        )}
                        {selectedResult.evidence?.caption && (
                          <p className="mt-2">{selectedResult.evidence.caption}</p>
                        )}
                        {selectedResult.evidence?.ocr_text && (
                          <p className="mt-2 text-xs leading-5 text-slate-400">{selectedResult.evidence.ocr_text}</p>
                        )}
                      </div>
                    )}
                  </div>

                  {selectedPage > 0 && (
                    <div className="2xl:sticky 2xl:top-0">
                      <p className="mb-2 text-xs uppercase tracking-[0.2em] text-slate-500">
                        Page image
                      </p>
                      <button
                        type="button"
                        onClick={() =>
                          setLargePageImage({
                            src: pageImageUrl(selectedResult.doc_id || doc.doc_id, selectedPage),
                            title: `${selectedResult.source_file || doc.filename} - page ${selectedPage}`,
                          })
                        }
                        className="block w-full rounded-xl transition hover:ring-2 hover:ring-cyan-300/35"
                        aria-label={`View page ${selectedPage} larger`}
                      >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={pageImageUrl(selectedResult.doc_id || doc.doc_id, selectedPage)}
                        alt={`${selectedResult.source_file || doc.filename} page ${selectedPage}`}
                        className="max-h-[320px] w-full rounded-xl border border-white/10 bg-black/30 object-contain"
                      />
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </section>
      {largePageImage && (
        <ImageLightbox
          src={largePageImage.src}
          alt={largePageImage.title}
          title={largePageImage.title}
          onClose={() => setLargePageImage(null)}
        />
      )}
    </div>
  );
}

function resultKey(result: SearchResult) {
  return `${result.doc_id}:${result.chunk_id}`;
}
