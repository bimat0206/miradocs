"use client";

import { statusTone } from "@/lib/workflow";

export function StatusPill({ status }: { status?: string }) {
  const tone = statusTone(status);
  const classes = {
    good: "border-cyan-300/35 bg-cyan-300/10 text-cyan-100",
    bad: "border-red-300/35 bg-red-300/10 text-red-100",
    warn: "border-amber-300/35 bg-amber-300/10 text-amber-100",
    idle: "border-slate-400/20 bg-slate-400/10 text-slate-300",
  }[tone];
  return (
    <span
      className={`shrink-0 rounded-full border px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] ${classes}`}
    >
      {status ?? "pending"}
    </span>
  );
}
