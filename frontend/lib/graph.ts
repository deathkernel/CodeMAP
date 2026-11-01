import type { AnalysisResult } from "./types";

export function getFolderGroup(path: string) {
  const parts = path.split("/").filter(Boolean);
  return parts.length > 1 ? parts[0] : "(root)";
}

export function getLanguageStyle(language: string) {
  const styles: Record<string, { border: string; background: string; text: string }> = {
    py: { border: "#3b82f6", background: "#102039", text: "#93c5fd" },
    ts: { border: "#0ea5e9", background: "#0d2533", text: "#7dd3fc" },
    tsx: { border: "#0ea5e9", background: "#0d2533", text: "#7dd3fc" },
    js: { border: "#eab308", background: "#29230e", text: "#fde047" },
    jsx: { border: "#eab308", background: "#29230e", text: "#fde047" },
    json: { border: "#a78bfa", background: "#211a35", text: "#c4b5fd" },
    css: { border: "#ec4899", background: "#301629", text: "#f9a8d4" },
    html: { border: "#f97316", background: "#301d12", text: "#fdba74" },
  };
  return styles[language.toLowerCase()] || { border: "#64748b", background: "#172033", text: "#cbd5e1" };
}

export function getGraphPositions(result: AnalysisResult) {
  const folders = [...new Set(result.nodes.map((node) => getFolderGroup(node.path)))].sort();
  const outgoing = new Map<string, string[]>();
  const indegree = new Map<string, number>();
  const rank = new Map<string, number>();
  const degree = new Map<string, number>();

  result.nodes.forEach((node) => {
    outgoing.set(node.id, []);
    indegree.set(node.id, 0);
    rank.set(node.id, 0);
    degree.set(node.id, 0);
  });
  result.edges.forEach((edge) => {
    if (!outgoing.has(edge.source) || !indegree.has(edge.target)) return;
    outgoing.get(edge.source)?.push(edge.target);
    indegree.set(edge.target, (indegree.get(edge.target) || 0) + 1);
    degree.set(edge.source, (degree.get(edge.source) || 0) + 1);
    degree.set(edge.target, (degree.get(edge.target) || 0) + 1);
  });

  const queue = result.nodes
    .filter((node) => indegree.get(node.id) === 0)
    .map((node) => node.id)
    .sort();
  let cursor = 0;
  while (cursor < queue.length) {
    const current = queue[cursor++];
    for (const target of outgoing.get(current) || []) {
      rank.set(target, Math.max(rank.get(target) || 0, (rank.get(current) || 0) + 1));
      const remaining = (indegree.get(target) || 0) - 1;
      indegree.set(target, remaining);
      if (remaining === 0) queue.push(target);
    }
  }

  const unresolved = result.nodes.filter((node) => (indegree.get(node.id) || 0) > 0);
  const nextRank = Math.max(0, ...rank.values()) + 1;
  unresolved.forEach((node) => rank.set(node.id, nextRank));

  const positions = new Map<string, { x: number; y: number }>();
  let folderTop = 0;
  folders.forEach((folder) => {
    const files = result.nodes.filter((node) => getFolderGroup(node.path) === folder);
    const columns = new Map<number, typeof files>();
    files.forEach((node) => {
      const column = rank.get(node.id) || 0;
      columns.set(column, [...(columns.get(column) || []), node]);
    });

    let folderRows = 1;
    columns.forEach((columnFiles, column) => {
      columnFiles.sort((a, b) =>
        (degree.get(b.id) || 0) - (degree.get(a.id) || 0) || a.path.localeCompare(b.path),
      );
      folderRows = Math.max(folderRows, columnFiles.length);
      columnFiles.forEach((node, index) => {
        positions.set(node.id, { x: column * 360, y: folderTop + index * 170 });
      });
    });
    folderTop += folderRows * 170 + 110;
  });

  return positions;
}

export function toMermaid(nodes: AnalysisResult["nodes"], edges: AnalysisResult["edges"]) {
  const lines = ["flowchart LR"];
  const ids = new Map(nodes.map((node, index) => [node.id, `F${index}`]));
  const folders = [...new Set(nodes.map((node) => getFolderGroup(node.path)))].sort();

  folders.forEach((folder, folderIndex) => {
    const folderId = `GROUP_${folderIndex}`;
    lines.push(`  subgraph ${folderId}["${folder.replaceAll('"', "'")}"]`);
    nodes.filter((node) => getFolderGroup(node.path) === folder).forEach((node) => {
      const id = ids.get(node.id);
      if (id) lines.push(`    ${id}["${node.path.replaceAll('"', "'").replaceAll("\n", " ")}"]`);
    });
    lines.push("  end");
  });

  edges.forEach((edge) => {
    const from = ids.get(edge.source);
    const to = ids.get(edge.target);
    if (from && to) lines.push(`  ${from} --> ${to}`);
  });
  return lines.join("\n");
}
