import { create } from "zustand";
import type { WorkflowTab } from "./workflow";

type WorkspaceState = {
  selectedDocId: string | null;
  selectedDocIds: string[];
  activeTab: WorkflowTab;
  setSelectedDocId: (docId: string | null) => void;
  setSelectedDocIds: (docIds: string[]) => void;
  setActiveTab: (tab: WorkflowTab) => void;
};

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  selectedDocId: null,
  selectedDocIds: [],
  activeTab: "Process",
  setSelectedDocId: (selectedDocId) => set({ selectedDocId }),
  setSelectedDocIds: (selectedDocIds) => set({ selectedDocIds }),
  setActiveTab: (activeTab) => set({ activeTab }),
}));
