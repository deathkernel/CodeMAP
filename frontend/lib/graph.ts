import type { AnalysisResult } from "./types";

export function getFolderGroup(path: string) {
  const parts = path.split("/").filter(Boolean);
  return parts.length > 1 ? parts[0] : "(root)";
}

export function getLanguageStyle(language: string) {
  const styles: Record<string, { border: string; background: string; text: string }> = {
    py: { border: "#38bdf8", background: "#102b3b", text: "#7dd3fc" },
    ts: { border: "#2dd4bf", background: "#102f32", text: "#99f6e4" },
    tsx: { border: "#2dd4bf", background: "#102f32", text: "#99f6e4" },
    js: { border: "#fbbf24", background: "#332a13", text: "#fde68a" },
    jsx: { border: "#fbbf24", background: "#332a13", text: "#fde68a" },
    json: { border: "#c084fc", background: "#2a1d3b", text: "#d8b4fe" },
    css: { border: "#f472b6", background: "#351b30", text: "#f9a8d4" },
    html: { border: "#fb923c", background: "#352216", text: "#fdba74" },
  };
  return styles[language.toLowerCase()] || { border: "#94a3b8", background: "#1b2936", text: "#cbd5e1" };
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
  const nodeWidth = 250;
  const nodeHeight = 168;
  const columnGap = 105;
  const rowGap = 42;
  const disconnectedColumns = 5;

  folders.forEach((folder) => {
    const files = result.nodes.filter((node) => getFolderGroup(node.path) === folder);
    const connected = files.filter((node) => (degree.get(node.id) || 0) > 0);
    const disconnected = files
      .filter((node) => (degree.get(node.id) || 0) === 0)
      .sort((a, b) => a.path.localeCompare(b.path));

    const columns = new Map<number, typeof connected>();
    connected.forEach((node) => {
      const column = rank.get(node.id) || 0;
      columns.set(column, [...(columns.get(column) || []), node]);
    });

    let connectedRows = 0;
    columns.forEach((columnFiles, column) => {
      columnFiles.sort((a, b) =>
        (degree.get(b.id) || 0) - (degree.get(a.id) || 0) || a.path.localeCompare(b.path),
      );
      connectedRows = Math.max(connectedRows, columnFiles.length);
      columnFiles.forEach((node, index) => {
        positions.set(node.id, {
          x: column * (nodeWidth + columnGap),
          y: folderTop + index * (nodeHeight + rowGap),
        });
      });
    });

    const maxRank = connected.length ? Math.max(...connected.map((node) => rank.get(node.id) || 0)) : -1;
    const disconnectedStartX = (maxRank + 1) * (nodeWidth + columnGap) + 90;
    disconnected.forEach((node, index) => {
      const column = index % disconnectedColumns;
      const row = Math.floor(index / disconnectedColumns);
      positions.set(node.id, {
        x: disconnectedStartX + column * (nodeWidth + 34),
        y: folderTop + row * (nodeHeight + 28),
      });
    });

    const disconnectedRows = Math.ceil(disconnected.length / disconnectedColumns);
    const folderRows = Math.max(connectedRows, disconnectedRows, 1);
    folderTop += folderRows * (nodeHeight + rowGap) + 120;
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
