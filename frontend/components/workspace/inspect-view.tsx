"use client";

import { useQuery } from "@tanstack/react-query";
import { FileSearch, ListTree, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { ImageLightbox } from "@/components/ui/image-lightbox";
import { InsightPanel } from "@/components/ui/insight-panel";
import { TablePreview } from "./table-preview";
import { figureImageUrl, getArtifact, pageImageUrl, getDocumentVersion } from "@/lib/api";
import { statusLabel } from "@/lib/workflow";
import type {
  DocumentRecord,
  FigureArtifact,
  TableArtifact,
} from "@/lib/types";

type StructureArtifact = {
  pages?: Array<{ page: number; section_path?: string; tables?: string[]; figures?: string[] }>;
  sections?: Array<{
    section_id: string;
    section_path?: string;
    title: string;
    page_start: number;
    page_end: number;
    level: number;
  }>;
};

type QualityArtifact = {
  status?: string;
  summary?: Record<string, number | string | unknown[]>;
  warnings?: Array<{ level?: string; page?: number; message: string }>;
};


interface InspectViewProps {
  doc: DocumentRecord | null;
  page: number;
  setPage: (page: number) => void;
  onSelectDocId?: (docId: string) => void;
}

export function InspectView({ doc, page, setPage, onSelectDocId }: InspectViewProps) {
  const [inspectMode, setInspectMode] = useState<"tables" | "figures">("tables");
  const [tableSearch, setTableSearch] = useState("");
  const [figureSearch, setFigureSearch] = useState("");
  const [sectionSearch, setSectionSearch] = useState("");
  const [selectedTableId, setSelectedTableId] = useState<string | null>(null);
  const [selectedFigureId, setSelectedFigureId] = useState<string | null>(null);
  const [pageDraft, setPageDraft] = useState(String(page));
  const [largePageOpen, setLargePageOpen] = useState(false);
  const [pageImageMissing, setPageImageMissing] = useState(false);

  const versionQuery = useQuery({
    queryKey: ["document-version", doc?.doc_id],
    queryFn: () => getDocumentVersion(doc!.doc_id),
    enabled: Boolean(doc),
  });

  const structureQuery = useQuery({
    queryKey: ["artifact", doc?.doc_id, "structure"],
    queryFn: () => getArtifact<StructureArtifact>(doc!.doc_id, "structure"),
    enabled: Boolean(doc),
  });

  const qualityQuery = useQuery({
    queryKey: ["artifact", doc?.doc_id, "quality"],
    queryFn: () => getArtifact<QualityArtifact>(doc!.doc_id, "quality"),
    enabled: Boolean(doc),
  });

  const tablesQuery = useQuery({
    queryKey: ["artifact", doc?.doc_id, "tables"],
    queryFn: () => getArtifact<TableArtifact[]>(doc!.doc_id, "tables"),
    enabled: Boolean(doc),
  });

  const figuresQuery = useQuery({
    queryKey: ["artifact", doc?.doc_id, "figures"],
    queryFn: () => getArtifact<FigureArtifact[]>(doc!.doc_id, "figures"),
    enabled: Boolean(doc),
  });

  const structurePageCount = structureQuery.data?.pages?.length ?? 0;
  const totalPages = Math.max(
    1,
    structurePageCount || doc?.page_count || 1,
  );
  const tables = tablesQuery.data ?? [];
  const figures = figuresQuery.data ?? [];
  const sections = structureQuery.data?.sections ?? [];
  const currentSection = useMemo(() => {
    const matches = sections.filter((section) => {
      const start = section.page_start || 0;
      const end = section.page_end || start;
      return page >= start && page <= end;
    });
    return matches.sort((a, b) => (b.level || 0) - (a.level || 0))[0] ?? null;
  }, [page, sections]);
  const filteredSections = useMemo(() => {
    const query = sectionSearch.trim().toLowerCase();
    if (!query) return sections;
    return sections.filter((section) => {
      const haystack = [
        section.title,
        section.section_path,
        `page ${section.page_start}`,
        `p${section.page_start}`,
      ].join(" ").toLowerCase();
      return haystack.includes(query);
    });
  }, [sectionSearch, sections]);

  const filteredTables = tables.filter((table) => {
    const query = tableSearch.toLowerCase();
    return (
      !query ||
      table.table_id.toLowerCase().includes(query) ||
      String(table.page).includes(query) ||
      (table.status ?? "").toLowerCase().includes(query)
    );
  });

  const filteredFigures = figures.filter((figure) => {
    const query = figureSearch.toLowerCase();
    return (
      !query ||
      figure.figure_id.toLowerCase().includes(query) ||
      String(figure.page).includes(query) ||
      (figure.caption ?? "").toLowerCase().includes(query)
    );
  });

  const selectedTable =
    tables.find((table) => table.table_id === selectedTableId) ?? filteredTables[0] ?? null;
  const selectedFigure =
    figures.find((figure) => figure.figure_id === selectedFigureId) ?? filteredFigures[0] ?? null;

  useEffect(() => {
    setPageDraft(String(page));
  }, [page]);

  useEffect(() => {
    setPageImageMissing(false);
  }, [doc?.doc_id, page]);

  useEffect(() => {
    const loading = structureQuery.isLoading || !doc?.page_count;
    if (!loading && page > totalPages) {
      setPage(totalPages);
    }
  }, [page, setPage, totalPages, structureQuery.isLoading, doc?.page_count]);

  if (!doc) return <EmptyState title="No document selected" />;
  const currentPageImage = pageImageUrl(doc.doc_id, page);
  const goToPage = () => {
    const nextPage = Number.parseInt(pageDraft, 10);
    if (!Number.isFinite(nextPage)) return;
    setPage(Math.min(totalPages, Math.max(1, nextPage)));
  };

  return (
    <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr] lg:h-full lg:min-h-0 min-h-[600px]">
      {/* Evidence Viewer Container */}
      <section className="rounded-3xl border border-white/10 bg-white/[0.035] p-5 flex flex-col lg:h-full lg:min-h-0 min-h-[400px]">
        <div className="mb-4 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2">
            <h3 className="text-lg font-semibold">Evidence viewer</h3>
            {versionQuery.data?.group?.versions && versionQuery.data.group.versions.length > 1 && (
              <select
                value={doc.doc_id}
                onChange={(e) => onSelectDocId?.(e.target.value)}
                className="h-8 rounded-lg border border-white/10 bg-slate-950 px-2 text-xs text-slate-200 outline-none focus:border-cyan-300/60"
              >
                {versionQuery.data.group.versions.map((v) => (
                  <option key={v.doc_id} value={v.doc_id}>
                    {v.version_label} (v{v.version_number})
                  </option>
                ))}
              </select>
            )}
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <button
              onClick={() => {
                const nextPage = Math.max(1, page - 1);
                setPage(nextPage);
                setPageDraft(String(nextPage));
              }}
              className="rounded-xl border border-white/10 px-3 py-1 text-sm transition hover:bg-white/5"
            >
              Prev
            </button>
            <form
              className="flex items-center gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                goToPage();
              }}
            >
              <input
                value={pageDraft}
                onChange={(event) => setPageDraft(event.target.value)}
                onBlur={goToPage}
                inputMode="numeric"
                aria-label="Page number"
                className="h-8 w-16 rounded-xl border border-white/10 bg-white/[0.04] px-2 text-center text-sm text-slate-200 outline-none focus:border-cyan-300/60"
              />
              <span className="text-sm text-slate-500">/ {totalPages}</span>
              <button
                type="submit"
                className="rounded-xl border border-white/10 px-3 py-1 text-sm transition hover:bg-white/5"
              >
                Go
              </button>
            </form>
            <button
              onClick={() => {
                const nextPage = Math.min(totalPages, page + 1);
                setPage(nextPage);
                setPageDraft(String(nextPage));
              }}
              className="rounded-xl border border-white/10 px-3 py-1 text-sm transition hover:bg-white/5"
            >
              Next
            </button>
          </div>
        </div>
        <button
          type="button"
          onClick={() => {
            if (!pageImageMissing) setLargePageOpen(true);
          }}
          className="flex-1 min-h-0 flex items-center justify-center rounded-2xl border border-white/10 bg-black/30 p-2 overflow-hidden transition hover:border-cyan-300/40"
          aria-label={`View page ${page} larger`}
        >
          {pageImageMissing ? (
            <div className="flex h-full min-h-[260px] w-full flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-white/15 bg-white/[0.03] px-6 text-center">
              <p className="text-sm font-medium text-slate-300">Page preview unavailable</p>
              <p className="text-xs text-slate-500">Page {page} image has not been generated.</p>
            </div>
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={currentPageImage}
              alt={`Page ${page}`}
              onError={() => setPageImageMissing(true)}
              className="max-h-full max-w-full object-contain rounded-lg"
            />
          )}
        </button>
      </section>

      {/* Details & Extracted Items Container */}
      <section className="flex flex-col gap-5 lg:h-full lg:min-h-0 overflow-y-auto">
        <InsightPanel icon={<ShieldCheck size={18} />} title="Quality">
          <p className="mb-3 text-sm text-slate-400">
            Status: <span className="text-cyan-200">{qualityQuery.data?.status ? statusLabel(qualityQuery.data.status) : "not available"}</span>
          </p>
          <div className="grid grid-cols-2 gap-3">
            {Object.entries(qualityQuery.data?.summary ?? {})
              .slice(0, 6)
              .map(([key, value]) => (
                <div key={key} className="rounded-2xl bg-white/[0.04] p-3">
                  <p className="text-xs text-slate-500">{key}</p>
                  <p className="text-lg font-semibold">
                    {Array.isArray(value) ? value.length : String(value)}
                  </p>
                </div>
              ))}
          </div>
        </InsightPanel>

        <section className="rounded-3xl border border-white/10 bg-white/[0.035] p-5">
          <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <h3 className="flex items-center gap-2 text-lg font-semibold">
                <ListTree size={18} className="text-cyan-200" />
                Section tree
              </h3>
              <p className="mt-1 text-xs text-slate-500">
                {sections.length ? `${sections.length} sections parsed from ${totalPages} pages` : "No parsed sections available"}
              </p>
            </div>
            {currentSection && (
              <button
                type="button"
                onClick={() => setPage(Math.max(1, currentSection.page_start || 1))}
                className="max-w-full rounded-xl border border-cyan-300/25 bg-cyan-300/10 px-3 py-2 text-left text-xs text-cyan-100 transition hover:border-cyan-300/50 sm:max-w-[260px]"
                title={currentSection.section_path || currentSection.title}
              >
                <span className="block text-[10px] uppercase tracking-[0.18em] text-cyan-200/70">Current</span>
                <span className="block truncate font-medium">{currentSection.title}</span>
              </button>
            )}
          </div>

          <input
            value={sectionSearch}
            onChange={(event) => setSectionSearch(event.target.value)}
            placeholder="Filter sections or pages"
            className="mb-3 w-full rounded-2xl border border-white/10 bg-white/[0.04] px-3 py-2 text-sm outline-none focus:border-cyan-300/60"
          />

          {structureQuery.isLoading ? (
            <div className="rounded-2xl border border-white/10 bg-black/20 p-4 text-sm text-slate-400">
              Loading parsed sections...
            </div>
          ) : filteredSections.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-white/15 bg-white/[0.02] p-4 text-sm text-slate-400">
              {sections.length ? "No sections match the current filter." : "Run the parse step to generate document sections."}
            </div>
          ) : (
            <div className="thin-scrollbar max-h-[280px] space-y-1 overflow-y-auto pr-1">
              {filteredSections.map((section) => {
                const start = Math.max(1, section.page_start || 1);
                const end = Math.max(start, section.page_end || start);
                const active = page >= start && page <= end;
                const level = Math.min(Math.max(section.level || 1, 1), 5);
                return (
                  <button
                    key={section.section_id}
                    type="button"
                    onClick={() => {
                      setPage(start);
                      setPageDraft(String(start));
                    }}
                    title={section.section_path || section.title}
                    className={`grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-xl border px-3 py-2 text-left transition ${
                      active
                        ? "border-cyan-300/45 bg-cyan-300/10 text-cyan-50"
                        : "border-transparent bg-transparent text-slate-300 hover:border-white/10 hover:bg-white/[0.04]"
                    }`}
                    style={{ paddingLeft: `${12 + (level - 1) * 14}px` }}
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium">{section.title || "Untitled section"}</span>
                      {section.section_path && section.section_path !== section.title && (
                        <span className="mt-0.5 block truncate text-[11px] text-slate-500">{section.section_path}</span>
                      )}
                    </span>
                    <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                      active ? "bg-cyan-300/15 text-cyan-100" : "bg-white/[0.05] text-slate-500"
                    }`}>
                      {start === end ? `p.${start}` : `p.${start}-${end}`}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </section>

        <section className="rounded-3xl border border-white/10 bg-white/[0.035] p-5 flex flex-col min-h-0">
          <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between shrink-0">
            <h3 className="flex items-center gap-2 text-lg font-semibold">
              <FileSearch size={18} /> Tables & figures
            </h3>
            <div className="grid grid-cols-2 rounded-full border border-white/10 bg-white/[0.04] p-1 text-sm">
              {(["tables", "figures"] as const).map((mode) => (
                <button
                  key={mode}
                  onClick={() => setInspectMode(mode)}
                  className={`rounded-full px-3 py-1.5 transition ${
                    inspectMode === mode
                      ? "bg-gradient-to-r from-cyan-300 to-violet-500 text-slate-950"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {mode === "tables" ? `Tables ${tables.length}` : `Figures ${figures.length}`}
                </button>
              ))}
            </div>
          </div>

          {inspectMode === "tables" ? (
            <div className="grid gap-4 xl:grid-cols-[0.8fr_1.2fr] min-h-0">
              <div className="flex flex-col min-h-0">
                <input
                  value={tableSearch}
                  onChange={(event) => setTableSearch(event.target.value)}
                  placeholder="Filter by page, id, status"
                  className="mb-3 w-full rounded-2xl border border-white/10 bg-white/[0.04] px-3 py-2 text-sm outline-none focus:border-cyan-300/60 shrink-0"
                />
                <div className="thin-scrollbar space-y-2 overflow-y-auto max-h-[300px] lg:max-h-[260px] pr-1">
                  {filteredTables.map((table) => (
                    <button
                      key={table.table_id}
                      onClick={() => {
                        setSelectedTableId(table.table_id);
                        setPage(Math.max(1, table.page || 1));
                      }}
                      className={`w-full rounded-2xl border p-3 text-left text-sm transition ${
                        selectedTable?.table_id === table.table_id
                          ? "border-cyan-300/50 bg-cyan-300/10"
                          : "border-white/10 bg-white/[0.03] hover:bg-white/[0.06]"
                      }`}
                    >
                      <div className="flex justify-between gap-3">
                        <span className="truncate font-medium">{table.table_id}</span>
                        <span className="text-slate-500">p.{table.page}</span>
                      </div>
                      <p className="mt-1 text-xs text-slate-400">
                        {table.rows} rows · {table.cols} cols · {table.status ?? "unknown"}
                      </p>
                    </button>
                  ))}
                </div>
              </div>
              <TablePreview docId={doc.doc_id} table={selectedTable} />
            </div>
          ) : (
            <div className="flex flex-col min-h-0">
              <input
                value={figureSearch}
                onChange={(event) => setFigureSearch(event.target.value)}
                placeholder="Filter by page, id, caption"
                className="mb-3 w-full rounded-2xl border border-white/10 bg-white/[0.04] px-3 py-2 text-sm outline-none focus:border-cyan-300/60 shrink-0"
              />
              <div className="thin-scrollbar grid gap-3 overflow-y-auto md:grid-cols-2 max-h-[480px] lg:max-h-[340px] pr-1">
                {filteredFigures.map((figure) => (
                  <button
                    key={figure.figure_id}
                    onClick={() => {
                      setSelectedFigureId(figure.figure_id);
                      setPage(Math.max(1, figure.page || 1));
                    }}
                    className={`rounded-2xl border p-3 text-left transition ${
                      selectedFigure?.figure_id === figure.figure_id
                        ? "border-cyan-300/50 bg-cyan-300/10"
                        : "border-white/10 bg-white/[0.03] hover:bg-white/[0.06]"
                    }`}
                  >
                    <div className="mb-2 flex items-center justify-between gap-3 text-sm">
                      <span className="truncate font-medium">{figure.figure_id}</span>
                      <span className="text-slate-500">p.{figure.page}</span>
                    </div>
                    {figure.image_path && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={figureImageUrl(doc.doc_id, figure.figure_id)}
                        alt={figure.figure_id}
                        className="mb-2 h-32 w-full rounded-xl border border-white/10 object-contain bg-black/20"
                      />
                    )}
                    <p className="line-clamp-2 text-xs text-slate-400">
                      {figure.caption ||
                        (figure.has_bbox ? "Detected figure with source bounds" : "Detected figure")}
                    </p>
                  </button>
                ))}
              </div>
            </div>
          )}
        </section>
      </section>
      {largePageOpen && !pageImageMissing && (
        <ImageLightbox
          src={currentPageImage}
          alt={`Page ${page}`}
          title={`Page ${page}`}
          onClose={() => setLargePageOpen(false)}
        />
      )}
    </div>
  );
}
