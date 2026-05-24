"use client";

interface EmptyStateProps {
  title: string;
}

export function EmptyState({ title }: EmptyStateProps) {
  return (
    <div className="rounded-3xl border border-white/10 bg-white/[0.035] p-8 text-center text-slate-400">
      {title}
    </div>
  );
}
