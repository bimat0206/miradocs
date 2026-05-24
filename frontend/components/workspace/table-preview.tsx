"use client";

import { useQuery } from "@tanstack/react-query";

import { artifactFileUrl, getArtifactFileText } from "@/lib/api";
import type { TableArtifact } from "@/lib/types";

interface TablePreviewProps {
  docId: string;
  table: TableArtifact | null;
}

export function TablePreview({ docId, table }: TablePreviewProps) {
  const mdName = table?.file_md ? table.file_md.split("/").pop() : null;
  const csvName = table?.file_csv ? table.file_csv.split("/").pop() : null;

  const previewQuery = useQuery({
    queryKey: ["artifact-file", docId, "tables", mdName ?? csvName],
    queryFn: () => getArtifactFileText(docId, "tables", mdName ?? csvName ?? ""),
    enabled: Boolean(table && (mdName || csvName)),
  });

  if (!table) {
    return (
      <div className="rounded-2xl border border-white/10 bg-black/20 p-4 text-sm text-slate-500">
        No table selected.
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-white/10 bg-black/20 p-4 flex flex-col min-h-[250px] lg:min-h-0 flex-1">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3 shrink-0">
        <div>
          <h4 className="font-medium">{table.table_id}</h4>
          <p className="text-xs text-slate-500">
            Page {table.page} · {table.rows} rows · {table.cols} cols
          </p>
        </div>
        <div className="flex gap-2 text-xs">
          {mdName && (
            <a
              href={artifactFileUrl(docId, "tables", mdName)}
              className="rounded-full border border-white/10 px-3 py-1 text-cyan-200"
            >
              MD
            </a>
          )}
          {csvName && (
            <a
              href={artifactFileUrl(docId, "tables", csvName)}
              className="rounded-full border border-white/10 px-3 py-1 text-cyan-200"
            >
              CSV
            </a>
          )}
        </div>
      </div>
      <pre className="thin-scrollbar flex-1 min-h-0 overflow-auto whitespace-pre-wrap rounded-xl bg-black/35 p-3 text-xs text-cyan-100/85">
        {previewQuery.data ??
          (table.status === "no_grid" ? "No grid data available for this table." : "Loading preview...")}
      </pre>
    </div>
  );
}
