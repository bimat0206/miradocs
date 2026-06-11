import { describe, expect, it } from "vitest";
import {
  formatUpdateAvailableMessage,
  formatUpdateProgressMessage,
  formatVersionLabel,
  getUpdatedAppUrl,
  isTerminalUpdateStatus,
} from "./update-status";

describe("update status helpers", () => {
  it("formats unknown and known version labels", () => {
    expect(formatVersionLabel("1.2.0")).toBe("v1.2.0");
    expect(formatVersionLabel("")).toBe("unknown version");
  });

  it("describes the local and remote versions for an available update", () => {
    expect(formatUpdateAvailableMessage("1.0.0", "1.1.0")).toBe(
      "Current v1.0.0 -> available v1.1.0"
    );
  });

  it("tracks the target version while the update is running", () => {
    expect(formatUpdateProgressMessage("1.0.0", "1.1.0", "Restarting services...")).toBe(
      "Updating v1.0.0 -> v1.1.0: Restarting services..."
    );
  });

  it("identifies terminal update states", () => {
    expect(isTerminalUpdateStatus("success")).toBe(true);
    expect(isTerminalUpdateStatus("failed")).toBe(true);
    expect(isTerminalUpdateStatus("updating")).toBe(false);
    expect(isTerminalUpdateStatus("idle")).toBe(false);
  });

  it("builds a cache-busting URL for the updated app", () => {
    expect(getUpdatedAppUrl("http://localhost:3000/workspace?tab=inspect&miradocs_updated=old", "1.8.1", 42)).toBe(
      "http://localhost:3000/workspace?tab=inspect&miradocs_updated=1.8.1&reload=42"
    );
  });
});
