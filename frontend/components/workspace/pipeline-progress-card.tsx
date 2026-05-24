"use client";

import { formatDuration, type pipelineProgress } from "@/lib/workflow";

interface PipelineProgressCardProps {
  progress: ReturnType<typeof pipelineProgress>;
  runtime: { elapsed_seconds?: number | null; eta_seconds?: number | null; label?: string | null };
  isRunning: boolean;
}

export function PipelineProgressCard({ progress, runtime, isRunning }: PipelineProgressCardProps) {
  const complete = progress.total > 0 && progress.completed === progress.total;
  const stateLabel = isRunning ? "Running" : complete ? "Complete" : progress.completed > 0 ? "Ready" : "Not started";

  return (
    <section className="w-full rounded-3xl border border-cyan-200/15 bg-white/[0.045] p-5 shadow-[0_20px_80px_rgba(6,182,212,0.08)] shrink-0">
      <div className="mb-4 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.28em] text-cyan-200/70">Pipeline progress</p>
          <p className="mt-2 text-sm text-slate-400">{runtime.label ?? stateLabel}</p>
        </div>
        <div className="sm:text-right">
          <p className="text-5xl font-semibold leading-none text-slate-50">{progress.percent}%</p>
          <p className="mt-1 text-xs text-slate-500">{progress.completed}/{progress.total || 0} steps complete</p>
        </div>
      </div>
      <div className="h-3 overflow-hidden rounded-full bg-white/10">
        <div
          className={`h-full rounded-full ${
            isRunning
              ? "bg-gradient-to-r from-cyan-300 via-sky-300 to-violet-500"
              : "bg-gradient-to-r from-cyan-300 to-violet-500"
          }`}
          style={{ width: `${progress.percent}%` }}
        />
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
        <div className="rounded-2xl bg-black/20 p-3">
          <p className="text-slate-500">Status</p>
          <p className="font-medium text-slate-200">{stateLabel}</p>
        </div>
        <div className="rounded-2xl bg-black/20 p-3">
          <p className="text-slate-500">Elapsed</p>
          <p className="font-medium text-slate-200">{formatDuration(runtime.elapsed_seconds)}</p>
        </div>
        <div className="rounded-2xl bg-black/20 p-3">
          <p className="text-slate-500">ETA</p>
          <p className="font-medium text-slate-200">{formatDuration(runtime.eta_seconds)}</p>
        </div>
        <div className="rounded-2xl bg-black/20 p-3">
          <p className="text-slate-500">Steps</p>
          <p className="font-medium text-slate-200">
            {progress.completed}/{progress.total || 0}
          </p>
        </div>
      </div>
    </section>
  );
}
