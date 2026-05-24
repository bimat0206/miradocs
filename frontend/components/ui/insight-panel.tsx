"use client";

import type { ReactNode } from "react";

interface InsightPanelProps {
  icon: ReactNode;
  title: string;
  children: ReactNode;
}

export function InsightPanel({ icon, title, children }: InsightPanelProps) {
  return (
    <div className="rounded-3xl border border-white/10 bg-white/[0.035] p-5">
      <h3 className="mb-4 flex items-center gap-2 text-lg font-semibold">
        {icon}
        {title}
      </h3>
      {children}
    </div>
  );
}
