import type { AnalysisResult } from "./types";

export type FileTreeItem = { name: string; path: string; isFolder: boolean; children: FileTreeItem[] };

export function buildFileTree(nodes: AnalysisResult["nodes"]): FileTreeItem[] {
  const root: FileTreeItem = { name: "", path: "", isFolder: true, children: [] };
  for (const file of nodes) {
    const parts = file.path.split("/").filter(Boolean);
    let current = root;
    let currentPath = "";
    parts.forEach((part, index) => {
      currentPath = currentPath ? currentPath + "/" + part : part;
      const isFolder = index < parts.length - 1;
      let item = current.children.find((child) => child.name === part);
      if (!item) {
        item = { name: part, path: currentPath, isFolder, children: [] };
        current.children.push(item);
      }
      current = item;
    });
  }
  const sortItems = (items: FileTreeItem[]) => {
    items.sort((a, b) => a.isFolder !== b.isFolder ? (a.isFolder ? -1 : 1) : a.name.localeCompare(b.name));
    items.forEach((item) => sortItems(item.children));
  };
  sortItems(root.children);
  return root.children;
}

export function hasTreeMatch(item: FileTreeItem, query: string): boolean {
  if (!query || item.path.toLowerCase().includes(query.toLowerCase())) return true;
  return item.children.some((child) => hasTreeMatch(child, query));
}
