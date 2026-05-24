"use client";

import { Layers3, Play } from "lucide-react";
import type { ReactNode } from "react";

import type { DocumentRecord } from "@/lib/types";
import type { pipelineProgress } from "@/lib/workflow";

interface WorkspaceHeaderProps {
  doc: DocumentRecord | null | undefined;
  progress: ReturnType<typeof pipelineProgress>;
  onRun: () => void;
  isRunning: boolean;
  canRun: boolean;
  leadingAction?: ReactNode;
}

export function WorkspaceHeader({
  doc,
  progress,
  onRun,
  isRunning,
  canRun,
  leadingAction,
}: WorkspaceHeaderProps) {
  const complete = progress.total > 0 && progress.completed === progress.total;
  const actionLabel = isRunning ? "Running" : complete ? "Run again" : "Run pipeline";

  return (
    <header className="shrink-0 border-b border-white/10 p-6">
      <div className="flex flex-col gap-5 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex min-w-0 flex-1 flex-col gap-4 sm:flex-row sm:items-start">
          {leadingAction}
          <div className="min-w-0 flex-1">
            <p className="mb-2 flex items-center gap-2 text-xs uppercase tracking-[0.35em] text-cyan-200/70">
              <Layers3 size={14} />
              Document command center
            </p>
            <h2 className="max-w-full text-3xl font-semibold leading-tight tracking-tight text-slate-50 [overflow-wrap:anywhere]">
              {doc?.filename ?? "Select or upload a document"}
            </h2>
            {doc && (
              <div className="mt-2 space-y-2">
                <p className="text-sm text-slate-400 [overflow-wrap:anywhere]">
                  {doc.doc_id} · {doc.document_type} · {doc.domain} · {doc.sensitivity}
                </p>
                {(doc.tags ?? []).length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {(doc.tags ?? []).map((tag) => (
                      <span
                        key={tag}
                        className="max-w-full truncate rounded-full border border-cyan-300/25 bg-cyan-300/10 px-2.5 py-1 text-xs text-cyan-100"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap items-center justify-end gap-3">
          <button
            disabled={!doc || isRunning || !canRun}
            onClick={onRun}
            className="flex items-center gap-2 rounded-2xl bg-white px-4 py-3 font-medium text-slate-950 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Play size={17} />
            {actionLabel}
          </button>
        </div>
      </div>
    </header>
  );
}
