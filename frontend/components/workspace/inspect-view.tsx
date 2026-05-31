"use client";

import { useQuery } from "@tanstack/react-query";
import { FileSearch, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { ImageLightbox } from "@/components/ui/image-lightbox";
import { InsightPanel } from "@/components/ui/insight-panel";
import { TablePreview } from "./table-preview";
import { figureImageUrl, getArtifact, pageImageUrl } from "@/lib/api";
import { statusLabel } from "@/lib/workflow";
import type {
  DocumentRecord,
  FigureArtifact,
  TableArtifact,
} from "@/lib/types";

type StructureArtifact = {
  pages?: Array<{ page: number; section_path?: string; tables?: string[]; figures?: string[] }>;
  sections?: Array<{ section_id: string; title: string; page_start: number; page_end: number; level: number }>;
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
}

export function InspectView({ doc, page, setPage }: InspectViewProps) {
  const [inspectMode, setInspectMode] = useState<"tables" | "figures">("tables");
  const [tableSearch, setTableSearch] = useState("");
  const [figureSearch, setFigureSearch] = useState("");
  const [selectedTableId, setSelectedTableId] = useState<string | null>(null);
  const [selectedFigureId, setSelectedFigureId] = useState<string | null>(null);
  const [pageDraft, setPageDraft] = useState(String(page));
  const [largePageOpen, setLargePageOpen] = useState(false);

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

  const totalPages = structureQuery.data?.pages?.length ?? 1;
  const tables = tablesQuery.data ?? [];
  const figures = figuresQuery.data ?? [];

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
          <h3 className="text-lg font-semibold">Evidence viewer</h3>
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
          onClick={() => setLargePageOpen(true)}
          className="flex-1 min-h-0 flex items-center justify-center rounded-2xl border border-white/10 bg-black/30 p-2 overflow-hidden transition hover:border-cyan-300/40"
          aria-label={`View page ${page} larger`}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={currentPageImage}
            alt={`Page ${page}`}
            className="max-h-full max-w-full object-contain rounded-lg"
          />
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
      {largePageOpen && (
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
