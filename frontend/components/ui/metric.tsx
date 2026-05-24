"use client";

interface MetricProps {
  label: string;
  value: number | string;
}

export function Metric({ label, value }: MetricProps) {
  return (
    <div className="rounded-3xl border border-white/10 bg-white/[0.035] p-5">
      <p className="text-xs uppercase tracking-[0.25em] text-slate-500">{label}</p>
      <p className="mt-2 text-3xl font-semibold">{value}</p>
    </div>
  );
}
