"use client";

import { useEffect, useState, useCallback } from "react";
import { API_BASE } from "../lib/api";
import {
  formatUpdateAvailableMessage,
  formatUpdateProgressMessage,
  formatVersionLabel,
  isTerminalUpdateStatus,
  type HealthResponse,
  type UpdateStatusResponse,
  type VersionCheckResponse,
} from "../lib/update-status";

type UpdateState = "idle" | "available" | "updating" | "success" | "failed";

export function UpdateNotification() {
  const [state, setState] = useState<UpdateState>("idle");
  const [localVersion, setLocalVersion] = useState("");
  const [remoteVersion, setRemoteVersion] = useState("");
  const [message, setMessage] = useState("");

  // Check for updates on mount
  useEffect(() => {
    const check = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/version-check`);
        if (!res.ok) return;
        const data = (await res.json()) as VersionCheckResponse;
        setLocalVersion(data.local_version);
        setRemoteVersion(data.remote_version);
        if (data.update_available) {
          setMessage(formatUpdateAvailableMessage(data.local_version, data.remote_version));
          setState("available");
        }
      } catch { /* offline or API not ready */ }
    };
    check();
  }, []);

  // Poll update status after triggering update.
  const pollUpdateStatus = useCallback(() => {
    let attempts = 0;
    const maxAttempts = 60; // 3s * 60 = 3 min max wait
    const interval = setInterval(async () => {
      attempts++;
      if (attempts > maxAttempts) {
        clearInterval(interval);
        setState("failed");
        setMessage("Update timed out. Check logs.");
        return;
      }
      try {
        const res = await fetch(`${API_BASE}/api/update-status`);
        if (res.ok) {
          const data = (await res.json()) as UpdateStatusResponse;
          if (data.status === "updating") {
            setMessage(formatUpdateProgressMessage(localVersion, remoteVersion, data.message));
            return;
          }
          if (isTerminalUpdateStatus(data.status)) {
            clearInterval(interval);
            setState(data.status);
            setMessage(data.status === "success"
              ? `Updated to ${formatVersionLabel(data.version || remoteVersion)}`
              : data.message || "Update failed. Check logs.");
            if (data.status === "success") {
              setTimeout(() => window.location.reload(), 2000);
            }
          }
        } else {
          const healthRes = await fetch(`${API_BASE}/api/health`);
          if (healthRes.ok) {
            const health = (await healthRes.json()) as HealthResponse;
            setMessage(formatUpdateProgressMessage(localVersion, remoteVersion, `API healthy on ${formatVersionLabel(health.version)}`));
          }
        }
      } catch { /* still restarting */ }
    }, 3000);
  }, [localVersion, remoteVersion]);

  const handleUpdate = async () => {
    setState("updating");
    setMessage(formatUpdateProgressMessage(localVersion, remoteVersion, "app will restart shortly."));
    try {
      await fetch(`${API_BASE}/api/update`, { method: "POST" });
    } catch { /* expected — server may die before responding */ }
    setTimeout(pollUpdateStatus, 5000);
  };

  const handleDismiss = () => setState("idle");

  if (state === "idle") return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-xl shadow-2xl p-6 max-w-sm w-full mx-4 space-y-4">
        {state === "available" && (
          <>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center">
                <svg className="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
              </div>
              <div>
                <h3 className="font-semibold text-gray-900">New version available</h3>
                <p className="text-sm text-gray-500">v{remoteVersion} is ready to install</p>
              </div>
            </div>
            <p className="text-sm text-gray-600">
              {message}
            </p>
            <div className="flex gap-3 pt-2">
              <button
                onClick={handleUpdate}
                className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors"
              >
                Yes, update now
              </button>
              <button
                onClick={handleDismiss}
                className="flex-1 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg font-medium hover:bg-gray-200 transition-colors"
              >
                Not now
              </button>
            </div>
          </>
        )}

        {state === "updating" && (
          <div className="text-center space-y-3 py-2">
            <div className="w-10 h-10 mx-auto rounded-full border-4 border-blue-200 border-t-blue-600 animate-spin" />
            <p className="text-sm text-gray-600">{message}</p>
          </div>
        )}

        {state === "success" && (
          <div className="text-center space-y-3 py-2">
            <div className="w-10 h-10 mx-auto rounded-full bg-green-100 flex items-center justify-center">
              <svg className="w-5 h-5 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <p className="text-sm font-medium text-green-700">{message}</p>
            <p className="text-xs text-gray-500">Reloading...</p>
          </div>
        )}

        {state === "failed" && (
          <div className="text-center space-y-3 py-2">
            <div className="w-10 h-10 mx-auto rounded-full bg-red-100 flex items-center justify-center">
              <svg className="w-5 h-5 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <p className="text-sm font-medium text-red-700">{message}</p>
            <button
              onClick={handleDismiss}
              className="mt-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm hover:bg-gray-200"
            >
              Dismiss
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
