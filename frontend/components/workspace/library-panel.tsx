"use client";

import {
  BookOpen,
  ChevronLeft,
  ChevronRight,
  Download,
  GitCompareArrows,
  Info,
  Library,
  PanelLeftClose,
  Search,
  Sparkles,
  Trash2,
  UploadCloud,
} from "lucide-react";
import { type RefObject, useEffect, useMemo, useState } from "react";

import { StatusPill } from "@/components/ui/status-pill";
import { exportWorkspaceUrl, importWorkspace, type ImportResult } from "@/lib/api";
import type { DocumentRecord } from "@/lib/types";

const DOCS_PER_PAGE = 8;

interface LibraryPanelProps {
  documents: DocumentRecord[];
  selectedDocId: string | null;
  selectedDocIds: string[];
  setSelectedDocIds: (value: string[]) => void;
  fileInput: RefObject<HTMLInputElement | null>;
  onUpload: (file: File) => void;
  onSelect: (docId: string) => void;
  isUploading: boolean;
  onDeleteMultiple: (docIds: string[]) => void;
  onCompare: () => void;
  onCrossSearch: () => void;
  onOpenAbout: () => void;
  onOpenGuide: () => void;
  onToggle: () => void;
  onImportComplete?: () => void;
}

export function LibraryPanel({
  documents,
  selectedDocId,
  selectedDocIds,
  setSelectedDocIds,
  fileInput,
  onUpload,
  onSelect,
  isUploading,
  onDeleteMultiple,
  onCompare,
  onCrossSearch,
  onOpenAbout,
  onOpenGuide,
  onToggle,
  onImportComplete,
}: LibraryPanelProps) {
  const hasSelection = selectedDocIds.length > 0;
  const canCompare = selectedDocIds.length === 2;
  const [query, setQuery] = useState("");

  // Export / Import state
  const [importState, setImportState] = useState<
    | { phase: "idle" }
    | { phase: "importing" }
    | { phase: "done"; result: ImportResult }
    | { phase: "error"; message: string }
  >({ phase: "idle" });

  function handleExport() {
    const url = hasSelection
      ? exportWorkspaceUrl(selectedDocIds)
      : exportWorkspaceUrl();
    const a = document.createElement("a");
    a.href = url;
    a.download = "";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  async function handleImportFile(file: File) {
    setImportState({ phase: "importing" });
    try {
      const result = await importWorkspace(file, true);
      setImportState({ phase: "done", result });
      onImportComplete?.();
    } catch (err) {
      setImportState({ phase: "error", message: err instanceof Error ? err.message : String(err) });
    }
  }
  const [page, setPage] = useState(1);
  const filteredDocuments = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return documents;
    return documents.filter((doc) => {
      const searchable = [
        doc.filename,
        doc.doc_id,
        doc.document_type,
        doc.domain,
        doc.sensitivity,
        doc.status,
        ...(doc.tags ?? []),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return searchable.includes(needle);
    });
  }, [documents, query]);
  const pageCount = Math.max(1, Math.ceil(filteredDocuments.length / DOCS_PER_PAGE));
  const currentPage = Math.min(page, pageCount);
  const pageDocuments = filteredDocuments.slice(
    (currentPage - 1) * DOCS_PER_PAGE,
    currentPage * DOCS_PER_PAGE,
  );

  useEffect(() => {
    setPage(1);
  }, [query, documents.length]);

  return (
    <aside className="lg:h-full rounded-[28px] glass flex flex-col overflow-hidden min-h-[500px] lg:min-h-0">
      <div className="shrink-0 border-b border-white/10 p-6">
        <div className="mb-6 flex items-center gap-3">
          <div className="rounded-2xl bg-gradient-to-br from-cyan-300 to-violet-500 p-3 text-slate-950">
            <Sparkles size={22} />
          </div>
          <div className="flex min-w-0 flex-1 items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="text-xs uppercase tracking-[0.35em] text-cyan-200/70">MiraDocs</p>
              <h1 className="text-2xl font-semibold tracking-tight">Workspace</h1>
            </div>
            <button
              type="button"
              onClick={onToggle}
              title="Hide library panel"
              className="mt-0.5 flex shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/[0.04] p-2 text-slate-400 transition hover:border-cyan-300/40 hover:bg-white/[0.08] hover:text-cyan-200"
              aria-label="Hide library panel"
            >
              <PanelLeftClose size={16} />
            </button>
          </div>
        </div>
        <input
          ref={fileInput}
          type="file"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) onUpload(file);
          }}
        />
        <button
          onClick={() => fileInput.current?.click()}
          className="flex w-full items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-cyan-300 to-violet-500 px-4 py-3 font-medium text-slate-950 transition hover:scale-[1.01]"
        >
          <UploadCloud size={18} />
          {isUploading ? "Uploading..." : "Upload document"}
        </button>
      </div>
      <div className="thin-scrollbar flex-1 min-h-0 overflow-y-auto p-3 max-h-[400px] lg:max-h-none">
        <div className="mb-3 px-3">
          <div className="mb-3 flex items-center justify-between gap-3">
            <span className="flex items-center gap-2 text-xs uppercase tracking-[0.25em] text-slate-500">
              <Library size={14} />
              Library
            </span>
            <span className="text-[11px] text-slate-500">{filteredDocuments.length} docs</span>
          </div>
          <div className="flex items-center gap-2 rounded-2xl border border-white/10 bg-white/[0.04] px-3 py-2 focus-within:border-cyan-300/60">
            <Search size={15} className="shrink-0 text-slate-500" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search docs or tags"
              className="min-w-0 flex-1 bg-transparent text-sm text-slate-200 outline-none placeholder:text-slate-600"
            />
          </div>
          {hasSelection && (
            <div className="mt-3 rounded-2xl border border-white/10 bg-white/[0.035] p-3">
              <div className="mb-3 flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Selection actions</p>
                  <p className="mt-1 text-sm font-medium text-slate-200">
                    {selectedDocIds.length} selected
                  </p>
                </div>
                {!canCompare && (
                  <p className="max-w-[150px] text-right text-[11px] leading-4 text-slate-500">
                    Select exactly 2 docs for Cross Search or Compare.
                  </p>
                )}
              </div>
              {canCompare && (
                <div className="mb-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                  <button
                    type="button"
                    onClick={onCrossSearch}
                    className="flex min-h-10 items-center justify-center gap-2 rounded-xl border border-cyan-300/35 bg-cyan-300/10 px-3 py-2 text-sm font-semibold text-cyan-100 transition hover:border-cyan-300/60 hover:bg-cyan-300/15 active:scale-[0.98]"
                    aria-label="Search selected documents side by side"
                  >
                    <Search size={15} />
                    Cross Search
                  </button>
                  <button
                    type="button"
                    onClick={onCompare}
                    className="flex min-h-10 items-center justify-center gap-2 rounded-xl border border-emerald-300/35 bg-emerald-300/10 px-3 py-2 text-sm font-semibold text-emerald-100 transition hover:border-emerald-300/60 hover:bg-emerald-300/15 active:scale-[0.98]"
                    aria-label="Compare selected documents"
                  >
                    <GitCompareArrows size={15} />
                    Compare
                  </button>
                </div>
              )}
              <button
                type="button"
                onClick={() => onDeleteMultiple(selectedDocIds)}
                className="flex min-h-10 w-full items-center justify-center gap-2 rounded-xl border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm font-semibold text-red-300 transition hover:border-red-500/60 hover:bg-red-500/20 hover:text-red-200 active:scale-[0.98]"
                aria-label={`Delete ${selectedDocIds.length} selected document${selectedDocIds.length > 1 ? "s" : ""}`}
              >
                <Trash2 size={15} />
                Delete selected
              </button>
            </div>
          )}
          <div className="mt-2 flex items-center justify-between text-[11px] text-slate-500">
            <span>{documents.length} total</span>
            <span>
              Page {currentPage}/{pageCount}
            </span>
          </div>
        </div>
        {pageDocuments.length === 0 ? (
          <p className="mx-3 rounded-2xl border border-white/10 bg-white/[0.03] p-4 text-sm text-slate-500">
            No documents match your search.
          </p>
        ) : pageDocuments.map((doc) => {
          const isChecked = selectedDocIds.includes(doc.doc_id);
          return (
            <button
              key={doc.doc_id}
              onClick={() => onSelect(doc.doc_id)}
              className={`mb-2 w-full rounded-2xl border p-4 text-left transition ${
                doc.doc_id === selectedDocId
                  ? "border-cyan-300/60 bg-cyan-300/10"
                  : "border-white/10 bg-white/[0.03] hover:border-white/25 hover:bg-white/[0.06]"
              }`}
            >
              <div className="mb-3 flex items-start justify-between gap-3">
                <div className="flex items-center gap-2.5 min-w-0 flex-1">
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onClick={(e) => e.stopPropagation()}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setSelectedDocIds([...selectedDocIds, doc.doc_id]);
                      } else {
                        setSelectedDocIds(selectedDocIds.filter((id) => id !== doc.doc_id));
                      }
                    }}
                    className="h-4 w-4 shrink-0 rounded border-white/20 bg-black/40 text-cyan-500 focus:ring-cyan-400 focus:ring-opacity-25 accent-cyan-300"
                    aria-label={`Select ${doc.filename} for multi-document analysis`}
                  />
                  <p className="min-w-0 line-clamp-2 text-sm font-medium leading-5 text-slate-100 [overflow-wrap:anywhere]">
                    {doc.filename}
                  </p>
                </div>
                <StatusPill status={doc.status} />
              </div>
              {(doc.tags ?? []).length > 0 && (
                <div className="mb-3 flex flex-wrap gap-1.5 pl-6">
                  {(doc.tags ?? []).slice(0, 4).map((tag) => (
                    <span
                      key={tag}
                      className="max-w-full truncate rounded-full border border-cyan-300/25 bg-cyan-300/10 px-2 py-0.5 text-[11px] text-cyan-100"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}
              <div className="flex items-center justify-between text-xs text-slate-400 pl-6">
                <span>{doc.domain}</span>
                <span>{doc.pipeline?.percent ?? 0}%</span>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10 ml-6">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-cyan-300 to-violet-500"
                  style={{ width: `${doc.pipeline?.percent ?? 0}%` }}
                />
              </div>
            </button>
          );
        })}
        {filteredDocuments.length > DOCS_PER_PAGE && (
          <div className="sticky bottom-0 mt-3 flex items-center justify-between gap-2 border-t border-white/10 bg-slate-950/95 px-3 py-3 backdrop-blur">
            <button
              type="button"
              onClick={() => setPage(Math.max(1, currentPage - 1))}
              disabled={currentPage === 1}
              className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/10 bg-white/[0.04] text-slate-300 transition hover:border-cyan-300/40 hover:text-cyan-100 disabled:cursor-not-allowed disabled:opacity-35"
              aria-label="Previous library page"
            >
              <ChevronLeft size={16} />
            </button>
            <div className="flex min-w-0 flex-1 items-center justify-center gap-1">
              {Array.from({ length: pageCount }, (_, index) => index + 1)
                .filter((pageNumber) => {
                  return (
                    pageNumber === 1 ||
                    pageNumber === pageCount ||
                    Math.abs(pageNumber - currentPage) <= 1
                  );
                })
                .map((pageNumber, index, pages) => {
                  const previous = pages[index - 1];
                  return (
                    <div key={pageNumber} className="flex items-center gap-1">
                      {previous && pageNumber - previous > 1 && (
                        <span className="px-1 text-xs text-slate-600">...</span>
                      )}
                      <button
                        type="button"
                        onClick={() => setPage(pageNumber)}
                        className={`h-8 min-w-8 rounded-lg px-2 text-xs font-medium transition ${
                          pageNumber === currentPage
                            ? "bg-cyan-300 text-slate-950"
                            : "border border-white/10 bg-white/[0.04] text-slate-400 hover:border-cyan-300/40 hover:text-cyan-100"
                        }`}
                      >
                        {pageNumber}
                      </button>
                    </div>
                  );
                })}
            </div>
            <button
              type="button"
              onClick={() => setPage(Math.min(pageCount, currentPage + 1))}
              disabled={currentPage === pageCount}
              className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/10 bg-white/[0.04] text-slate-300 transition hover:border-cyan-300/40 hover:text-cyan-100 disabled:cursor-not-allowed disabled:opacity-35"
              aria-label="Next library page"
            >
              <ChevronRight size={16} />
            </button>
          </div>
        )}
      </div>
      <div className="shrink-0 border-t border-white/10 p-3 space-y-2">
        {/* Export / Import */}
        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={handleExport}
            title={hasSelection ? `Export ${selectedDocIds.length} selected doc(s)` : "Export all documents"}
            className="flex items-center justify-center gap-2 rounded-xl border border-cyan-300/25 bg-cyan-300/[0.06] px-3 py-2 text-xs font-medium text-cyan-200 transition hover:border-cyan-300/50 hover:bg-cyan-300/10 hover:text-cyan-100"
          >
            <Download size={13} />
            {hasSelection ? `Export (${selectedDocIds.length})` : "Export all"}
          </button>
          <label
            aria-disabled={importState.phase === "importing"}
            className={`flex cursor-pointer items-center justify-center gap-2 rounded-xl border border-violet-300/25 bg-violet-300/[0.06] px-3 py-2 text-xs font-medium text-violet-200 transition hover:border-violet-300/50 hover:bg-violet-300/10 hover:text-violet-100 ${importState.phase === "importing" ? "cursor-not-allowed opacity-50 pointer-events-none" : ""}`}
          >
            <UploadCloud size={13} />
            {importState.phase === "importing" ? "Importing…" : "Import"}
            <input
              type="file"
              accept=".zip"
              className="sr-only"
              disabled={importState.phase === "importing"}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) {
                  handleImportFile(f);
                  e.target.value = "";
                }
              }}
            />
          </label>
        </div>

        {/* Import feedback */}
        {importState.phase === "done" && (
          <div className="rounded-xl border border-emerald-400/30 bg-emerald-400/10 px-3 py-2 text-xs text-emerald-200">
            <p className="font-semibold">Import complete</p>
            <p className="mt-0.5 text-emerald-300/80">
              {importState.result.imported_docs} imported · {importState.result.skipped_docs} skipped
            </p>
            <button
              type="button"
              onClick={() => setImportState({ phase: "idle" })}
              className="mt-1 text-[11px] text-emerald-400/70 underline hover:text-emerald-300"
            >
              Dismiss
            </button>
          </div>
        )}
        {importState.phase === "error" && (
          <div className="rounded-xl border border-red-400/30 bg-red-400/10 px-3 py-2 text-xs text-red-200">
            <p className="font-semibold">Import failed</p>
            <p className="mt-0.5 line-clamp-3 text-red-300/80">{importState.message}</p>
            <button
              type="button"
              onClick={() => setImportState({ phase: "idle" })}
              className="mt-1 text-[11px] text-red-400/70 underline hover:text-red-300"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Guide / About */}
        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={onOpenGuide}
            className="flex items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-xs font-medium text-slate-300 transition hover:border-cyan-300/45 hover:text-cyan-100"
          >
            <BookOpen size={14} />
            How to use
          </button>
          <button
            type="button"
            onClick={onOpenAbout}
            className="flex items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-xs font-medium text-slate-300 transition hover:border-violet-300/45 hover:text-violet-100"
          >
            <Info size={14} />
            About
          </button>
        </div>
      </div>
    </aside>
  );
}
