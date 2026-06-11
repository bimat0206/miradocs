export type VersionCheckResponse = {
  update_available: boolean;
  local_version: string;
  remote_version: string;
};

export type UpdateStatus = "idle" | "updating" | "success" | "failed";

export type UpdateStatusResponse = {
  status: UpdateStatus;
  message?: string;
  version?: string;
};

export type HealthResponse = {
  status: string;
  version: string;
};

export function formatVersionLabel(version?: string | null) {
  const normalized = version?.trim();
  return normalized ? `v${normalized}` : "unknown version";
}

export function formatUpdateAvailableMessage(localVersion: string, remoteVersion: string) {
  return `Current ${formatVersionLabel(localVersion)} -> available ${formatVersionLabel(remoteVersion)}`;
}

export function formatUpdateProgressMessage(localVersion: string, remoteVersion: string, statusMessage?: string) {
  const base = `Updating ${formatVersionLabel(localVersion)} -> ${formatVersionLabel(remoteVersion)}`;
  return statusMessage ? `${base}: ${statusMessage}` : base;
}

export function isTerminalUpdateStatus(status: UpdateStatus) {
  return status === "success" || status === "failed";
}

export function getUpdatedAppUrl(currentHref: string, version?: string | null, now = Date.now()) {
  const url = new URL(currentHref);
  const normalizedVersion = version?.trim() || "unknown";
  url.searchParams.set("miradocs_updated", normalizedVersion);
  url.searchParams.set("reload", String(now));
  return url.toString();
}
