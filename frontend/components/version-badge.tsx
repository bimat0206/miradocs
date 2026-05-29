"use client";

import { useEffect, useState } from "react";

import { API_BASE } from "../lib/api";
import { formatVersionLabel, type HealthResponse } from "../lib/update-status";

export function VersionBadge() {
  const [version, setVersion] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function loadVersion() {
      try {
        const res = await fetch(`${API_BASE}/api/health`);
        if (!res.ok) return;
        const data = (await res.json()) as HealthResponse;
        if (!cancelled) setVersion(data.version);
      } catch {
        // API may still be starting; keep the badge non-blocking.
      }
    }

    loadVersion();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <span className="inline-flex items-center rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-xs text-slate-400">
      Version {formatVersionLabel(version)}
    </span>
  );
}
