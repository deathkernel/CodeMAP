"use client";

import { useEffect, useMemo, useState } from "react";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  MarkerType,
  ReactFlowProvider,
  type Edge,
  type Node,
} from "reactflow";
import "reactflow/dist/style.css";
import type { AnalysisResult } from "@/lib/types";
import { API_BASE } from "@/lib/config";
import { buildFileTree, hasTreeMatch, type FileTreeItem } from "@/lib/file-tree";
import { getFileIcon } from "@/lib/file-icons";
import { getFolderGroup, getGraphPositions, getLanguageStyle, toMermaid } from "@/lib/graph";
import { Feature, Metric } from "@/components/ui";
import {
  ArrowRight, Boxes, Bug, ChevronDown, ChevronRight, FileCode2,
  FileArchive, Folder, FolderOpen, Github, LoaderCircle,
  Network, Search, ShieldCheck, Sparkles, Workflow,
} from "lucide-react";

function Explorer() {
  const [url, setUrl] = useState("");
  const [localSources, setLocalSources] = useState<Record<string, string>>({});
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [showDisconnected, setShowDisconnected] = useState(false);
  const [activeFolder, setActiveFolder] = useState("all");
  const [highlightDependencies, setHighlightDependencies] = useState(true);
  const [expandedFolders, setExpandedFolders] = useState<Record<string, boolean>>({});
  const [query, setQuery] = useState("");
  const [codeSearchQuery, setCodeSearchQuery] = useState("");
  const [codeSearchMode, setCodeSearchMode] = useState<"all" | "functions" | "classes" | "imports">("all");
  const [codeSearchLanguage, setCodeSearchLanguage] = useState("all");
  const [sourceLine, setSourceLine] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [source, setSource] = useState<{ path: string; content: string; truncated: boolean } | null>(null);
  const [sourceLoading, setSourceLoading] = useState(false);
  const [explanation, setExplanation] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [aiStatus, setAiStatus] = useState("");
  const [aiError, setAiError] = useState("");
  const [bugAiLoadingId, setBugAiLoadingId] = useState<string | null>(null);
  const [bugAiFindingId, setBugAiFindingId] = useState<string | null>(null);
  const [bugAiExplanation, setBugAiExplanation] = useState("");
  const [bugAiError, setBugAiError] = useState("");
  const [architectureExplanation, setArchitectureExplanation] = useState("");
  const [architectureAiLoading, setArchitectureAiLoading] = useState(false);
  const [architectureAiError, setArchitectureAiError] = useState("");
  const [codebaseQuestion, setCodebaseQuestion] = useState("");
  const [codebaseAnswer, setCodebaseAnswer] = useState("");
  const [codebaseSources, setCodebaseSources] = useState<Array<{ path: string; start_line: number }>>([]);
  const [codebaseLoading, setCodebaseLoading] = useState(false);
  const [codebaseClearLoading, setCodebaseClearLoading] = useState(false);
  const [codebaseError, setCodebaseError] = useState("");
  const [ollamaState, setOllamaState] = useState<"checking" | "ready" | "missing" | "offline">("checking");
  const [reportStatus, setReportStatus] = useState("");
  const [reportError, setReportError] = useState("");
  const [reportComparison, setReportComparison] = useState<any>(null);

  useEffect(() => {
    let active = true;
    fetch(`${API_BASE}/api/ai/status`)
      .then(async (response) => {
        if (!response.ok) throw new Error("Ollama status unavailable");
        return response.json();
      })
      .then((status) => {
        if (!active) return;
        if (!status.available) setOllamaState("offline");
        else setOllamaState(status.model_installed ? "ready" : "missing");
      })
      .catch(() => {
        if (active) setOllamaState("offline");
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!source || !sourceLine) return;
    document.getElementById(`source-line-${sourceLine}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [source, sourceLine]);

  const fileTree = useMemo(() => buildFileTree(result?.nodes || []), [result]);
  const codeSearchResults = useMemo(() => {
    const term = codeSearchQuery.trim().toLowerCase();
    if (!term || !Object.keys(localSources).length) return [];
    const matches: Array<{ path: string; line: number; text: string; kind: string }> = [];
    const nodeByPath = new Map((result?.nodes || []).map((node) => [node.path, node]));
    const patterns = {
      functions: /^\s*(?:(?:export|default|public|private|protected|static|async)\s+)*(?:function\s+|def\s+|fn\s+|(?:const|let|var)\s+)[\w$]+\s*(?:=\s*(?:async\s*)?(?:\([^)]*\)|[\w$]+)\s*=>)?/,
      classes: /^\s*(?:(?:export|default|public|private|abstract)\s+)*class\s+[\w$]+/,
      imports: /^\s*(?:import\s|from\s+.+\s+import\s|const\s+.+\s*=\s*require\s*\(|(?:const|let|var)\s+.+\s*=\s*await\s+import\s*\()/,
    };
    Object.entries(localSources).forEach(([path, content]) => {
      const node = nodeByPath.get(path);
      if (codeSearchLanguage !== "all" && node?.language !== codeSearchLanguage) return;
      content.split(/\r?\n/).forEach((line, index) => {
        const trimmed = line.trim();
        if (!trimmed) return;
        const kind = codeSearchMode === "all" ? "code"
          : codeSearchMode === "functions" ? "function"
          : codeSearchMode === "classes" ? "class" : "import";
        if (codeSearchMode !== "all" && !patterns[codeSearchMode].test(line)) return;
        if (!trimmed.toLowerCase().includes(term)) return;
        matches.push({ path, line: index + 1, text: trimmed.slice(0, 220), kind });
      });
    });
    return matches.slice(0, 150);
  }, [codeSearchQuery, codeSearchMode, codeSearchLanguage, localSources, result]);
  const codeSearchLanguages = useMemo(
    () => [...new Set((result?.nodes || []).map((node) => node.language).filter(Boolean))].sort(),
    [result],
  );
  const graphMetrics = useMemo(() => {
    const degree = new Map<string, number>();
    const adjacency = new Map<string, string[]>();
    result?.nodes.forEach((node) => { degree.set(node.id, 0); adjacency.set(node.id, []); });
    result?.edges.forEach((edge) => {
      degree.set(edge.source, (degree.get(edge.source) || 0) + 1);
      degree.set(edge.target, (degree.get(edge.target) || 0) + 1);
      adjacency.get(edge.source)?.push(edge.target);
    });
    const disconnected = result?.nodes.filter((node) => (degree.get(node.id) || 0) === 0).map((node) => node.id) || [];
    const important = [...degree.entries()].filter(([, count]) => count > 0).sort((a, b) => b[1] - a[1]).slice(0, 5).map(([id]) => id);
    const reachable = new Set<string>();
    if (selected && adjacency.has(selected)) {
      const queue = [...(adjacency.get(selected) || [])];
      while (queue.length) {
        const current = queue.shift()!;
        if (reachable.has(current) || current === selected) continue;
        reachable.add(current);
        queue.push(...(adjacency.get(current) || []));
      }
      reachable.add(selected);
    }
    return { degree, disconnected, important, reachable };
  }, [result, selected]);

  const graphNodes: Node[] = useMemo(() => {
    if (!result) return [];
    const positions = getGraphPositions(result);
    return result.nodes.map((node) => {
      const degree = graphMetrics.degree.get(node.id) || 0;
      const disconnected = degree === 0;
      const isImportant = graphMetrics.important.includes(node.id);
      const inPath = !selected || !highlightDependencies || graphMetrics.reachable.has(node.id);
      const languageStyle = getLanguageStyle(node.language);
      const borderColor = selected === node.id ? "#a5b4fc" : disconnected ? "#fbbf24" : isImportant ? "#34d399" : languageStyle.border;
      return {
        id: node.id,
        position: positions.get(node.id) || { x: 0, y: 0 },
        data: { label: (
          <div className="min-w-40 rounded-xl border px-4 py-3 shadow-xl" style={{ borderColor, background: languageStyle.background }}>
            <div className="flex items-center gap-2" style={{ color: languageStyle.text }}><FileCode2 size={15} /><span className="text-xs uppercase">{node.language}</span>{isImportant && <span className="ml-auto text-[9px] text-emerald-300">CORE</span>}</div>
            <div className="mt-2 max-w-48 truncate text-sm font-semibold text-slate-100">{node.label}</div>
            <div className="mt-1 max-w-48 truncate text-[10px] text-slate-400">{node.path}</div>
            <div className="mt-2 flex justify-between text-[10px] text-slate-500"><span>{node.lines} lines</span><span>{degree} links</span></div>
            {disconnected && <div className="mt-1 text-[9px] text-amber-300">Disconnected</div>}
          </div>
        ) },
        style: { width: 205, border: "none", background: "transparent", padding: 0, opacity: inPath ? 1 : 0.18 },
      };
    });
  }, [result, graphMetrics, selected, highlightDependencies]);
  const graphEdges: Edge[] = useMemo(
    () => result?.edges.map((edge) => {
      const active = !selected || !highlightDependencies || (graphMetrics.reachable.has(edge.source) && graphMetrics.reachable.has(edge.target));
      return {
        id: edge.id, source: edge.source, target: edge.target, label: "imports", animated: active,
        style: { stroke: active ? "#818cf8" : "#334155", strokeWidth: active ? 1.8 : 1, opacity: active ? 1 : 0.15 },
        labelStyle: { fill: "#a5b4fc", fontSize: 10 },
        markerEnd: { type: MarkerType.ArrowClosed, color: active ? "#818cf8" : "#334155", width: 16, height: 16 },
      };
    }) ?? [],
    [result, graphMetrics, selected, highlightDependencies],
  );

  const folderOptions = useMemo(
    () => [...new Set(result?.nodes.map((node) => getFolderGroup(node.path)) || [])].sort(),
    [result],
  );
  const visibleGraphNodes = useMemo(() => {
    const folderNodes = activeFolder === "all"
      ? graphNodes
      : graphNodes.filter((node) => getFolderGroup(node.id) === activeFolder);
    return showDisconnected
      ? folderNodes.filter((node) => graphMetrics.disconnected.includes(node.id))
      : folderNodes;
  }, [graphNodes, activeFolder, showDisconnected, graphMetrics.disconnected]);
  const visibleNodeIds = useMemo(
    () => new Set(visibleGraphNodes.map((node) => node.id)),
    [visibleGraphNodes],
  );
  const visibleGraphEdges = useMemo(
    () => showDisconnected ? [] : graphEdges.filter(
      (edge) => visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target),
    ),
    [graphEdges, visibleNodeIds, showDisconnected],
  );

  const dependencyDrilldown = useMemo(() => {
    if (!result || !selected) return null;
    const known = new Set(result.nodes.map((node) => node.id));
    if (!known.has(selected)) return null;
    const incoming = new Map<string, string[]>();
    const outgoing = new Map<string, string[]>();
    result.nodes.forEach((node) => {
      incoming.set(node.id, []);
      outgoing.set(node.id, []);
    });
    result.edges.forEach((edge) => {
      if (!known.has(edge.source) || !known.has(edge.target)) return;
      outgoing.get(edge.source)?.push(edge.target);
      incoming.get(edge.target)?.push(edge.source);
    });
    const walk = (adjacency: Map<string, string[]>) => {
      const depths = new Map<string, number>();
      const queue: Array<[string, number]> = (adjacency.get(selected) || []).map((path) => [path, 1]);
      while (queue.length) {
        const [path, depth] = queue.shift()!;
        const previous = depths.get(path);
        if (previous !== undefined && previous <= depth) continue;
        depths.set(path, depth);
        (adjacency.get(path) || []).forEach((next) => queue.push([next, depth + 1]));
      }
      depths.delete(selected);
      return [...depths.entries()]
        .map(([path, depth]) => ({ path, depth }))
        .sort((a, b) => a.depth - b.depth || a.path.localeCompare(b.path));
    };
    const unique = (paths: string[]) => [...new Set(paths)].sort();
    return {
      incoming: unique(incoming.get(selected) || []),
      outgoing: unique(outgoing.get(selected) || []),
      upstream: walk(incoming),
      downstream: walk(outgoing),
    };
  }, [result, selected]);

  const impactAnalysis = useMemo(() => {
    if (!dependencyDrilldown) return null;
    const affected = dependencyDrilldown.upstream;
    const modules = new Map<string, string[]>();
    affected.forEach(({ path }) => {
      const parts = path.split("/");
      const name = parts.length > 1 ? parts[0] : "(root)";
      modules.set(name, [...(modules.get(name) || []), path]);
    });
    const affectedModules = [...modules.entries()]
      .map(([name, paths]) => ({ name, paths }))
      .sort((a, b) => b.paths.length - a.paths.length || a.name.localeCompare(b.name));
    const radius = affected.length >= 20 || affectedModules.length >= 5 ? "high"
      : affected.length >= 6 || affectedModules.length >= 3 ? "moderate"
      : affected.length ? "low" : "none";
    return { affected, affectedModules, radius };
  }, [dependencyDrilldown]);

  async function openSource(path: string, line?: number) {
    if (!result) return;
    setSourceLine(line ?? null);
    setSelected(path);
    setSourceLoading(true);
    setSource(null);
    setExplanation("");
    setAiError("");
    try {
      if (Object.prototype.hasOwnProperty.call(localSources, path)) {
        const content = localSources[path];
        setSource({ path, content: content.slice(0, 20000), truncated: content.length > 20000 });
        return;
      }
      if (!url) throw new Error("Source is not available for this file.");
      const response = await fetch(`${API_BASE}/api/repository/source`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, path }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Could not load source.");
      setSource(payload);
    } catch (err) {
      setAiError(err instanceof Error ? err.message : "Could not load source file.");
    } finally { setSourceLoading(false); }
  }

  async function prepareModel() {
    const response = await fetch(`${API_BASE}/api/ai/prepare`, { method: "POST" });
    if (!response.ok || !response.body) throw new Error("Could not prepare the local Ollama model.");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line);
        if (event.status === "checking") setAiStatus("Checking local model…");
        if (event.status === "downloading") {
          const percent = event.total && event.completed
            ? Math.round((event.completed / event.total) * 100)
            : null;
          setAiStatus(percent === null
            ? `Downloading Qwen3.5-9B: ${event.detail || "Preparing files"}…`
            : `Downloading Qwen3.5-9B: ${percent}%`);
        }
        if (event.status === "error") throw new Error(event.message || "Model download failed.");
        if (event.status === "ready") setAiStatus("Local model ready. Generating explanation…");
      }
    }
  }

  async function explainSource() {
    if (!source || !selectedNode) return;
    setAiLoading(true); setAiError(""); setExplanation(""); setAiStatus("Preparing local AI…");
    try {
      await prepareModel();
      const response = await fetch(`${API_BASE}/api/ai/explain`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: source.path, language: selectedNode.language, code: source.content }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Ollama explanation failed.");
      setExplanation(payload.explanation || "The model returned an empty explanation.");
      setAiStatus("Explanation generated locally.");
    } catch (err) {
      setAiError(err instanceof Error ? err.message : "Could not reach local Ollama.");
    } finally { setAiLoading(false); }
  }


  async function explainBug(finding: AnalysisResult["bug_findings"][number]) {
    setBugAiLoadingId(finding.id);
    setBugAiFindingId(finding.id);
    setBugAiExplanation("");
    setBugAiError("");
    setAiStatus("Preparing local AI…");
    try {
      await prepareModel();
      let sourceCode = localSources[finding.path];
      if (sourceCode === undefined) {
        if (!url) throw new Error("Source is not available for this finding.");
        const sourceResponse = await fetch(`${API_BASE}/api/repository/source`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url, path: finding.path }),
        });
        const sourcePayload = await sourceResponse.json();
        if (!sourceResponse.ok) throw new Error(sourcePayload.detail || "Could not load source for this finding.");
        sourceCode = sourcePayload.content;
      }

      const extension = finding.path.split(".").pop()?.toLowerCase() || "unknown";
      const language = extension === "py" ? "python" : extension;
      const response = await fetch(`${API_BASE}/api/ai/explain-bug`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          path: finding.path,
          language,
          line: finding.line,
          rule_id: finding.rule_id,
          title: finding.title,
          severity: finding.severity,
          message: finding.message,
          recommendation: finding.recommendation,
          code: sourceCode,
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "AI bug explanation failed.");
      setBugAiExplanation(payload.explanation || "The model returned an empty explanation.");
      setAiStatus("Bug explanation generated locally.");
    } catch (err) {
      setBugAiError(err instanceof Error ? err.message : "Could not explain this finding.");
    } finally {
      setBugAiLoadingId(null);
    }
  }

  async function explainArchitecture() {
    if (!result) return;
    setArchitectureAiLoading(true);
    setArchitectureAiError("");
    setArchitectureExplanation("");
    setAiStatus("Preparing local AI…");
    try {
      await prepareModel();
      const response = await fetch(`${API_BASE}/api/ai/explain-architecture`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          repository: result.repository,
          stats: result.stats,
          architecture_insights: result.architecture_insights,
          advanced_architecture: result.advanced_architecture,
          architecture_health: result.architecture_health,
          code_intelligence: result.code_intelligence,
          symbol_stats: result.symbol_intelligence.symbol_stats,
          bug_stats: result.bug_stats,
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Architecture explanation failed.");
      setArchitectureExplanation(payload.explanation || "The model returned an empty explanation.");
      setAiStatus("Architecture explanation generated locally.");
    } catch (err) {
      setArchitectureAiError(err instanceof Error ? err.message : "Could not explain this architecture.");
    } finally {
      setArchitectureAiLoading(false);
    }
  }

  async function clearCodebaseIndex() {
    if (!result) return;
    setCodebaseClearLoading(true);
    setCodebaseError("");
    try {
      const response = await fetch(`${API_BASE}/api/repository/index/${result.project_id}`, { method: "DELETE" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Could not clear the local index.");
      setResult((current) => current ? { ...current, indexed_chunks: 0 } : current);
      setCodebaseAnswer("");
      setCodebaseSources([]);
    } catch (err) {
      setCodebaseError(err instanceof Error ? err.message : "Could not clear the local index.");
    } finally {
      setCodebaseClearLoading(false);
    }
  }

  async function askCodebase(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!result || !codebaseQuestion.trim()) return;
    setCodebaseLoading(true);
    setCodebaseError("");
    setCodebaseAnswer("");
    setCodebaseSources([]);
    try {
      await prepareModel();
      const response = await fetch(`${API_BASE}/api/ai/ask-codebase`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: result.project_id,
          repository: result.repository,
          question: codebaseQuestion.trim(),
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Could not answer this codebase question.");
      setCodebaseAnswer(payload.answer || "The model returned an empty answer.");
      setCodebaseSources(payload.sources || []);
    } catch (err) {
      setCodebaseError(err instanceof Error ? err.message : "Could not query the local code index.");
    } finally {
      setCodebaseLoading(false);
    }
  }

  async function analyze(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);
    setCodebaseAnswer("");
    setCodebaseSources([]);
    setCodebaseError("");
    try {
      const response = await fetch(`${API_BASE}/api/repository/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Analysis failed. Check the API server.");
      setLocalSources({});
      setResult(payload);
      setExpandedFolders({});
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not connect to CodeMap API.");
    } finally {
      setLoading(false);
    }
  }


  async function analyzeZip(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".zip")) {
      setError("Please select a .zip archive.");
      return;
    }
    if (file.size > 50 * 1024 * 1024) {
      setError("ZIP exceeds the 50 MB upload limit.");
      return;
    }

    setLoading(true);
    setError("");
    setResult(null);
    setLocalSources({});
    setCodebaseAnswer("");
    setCodebaseSources([]);
    setCodebaseError("");
    setUrl("");

    try {
      const formData = new FormData();
      formData.append("file", file);
      const response = await fetch(`${API_BASE}/api/repository/analyze-zip`, {
        method: "POST",
        body: formData,
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "ZIP analysis failed.");
      setLocalSources(payload.source_contents || {});
      setResult(payload);
      setExpandedFolders({});
      setSelected(null);
      setSource(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not analyze this ZIP archive.");
    } finally {
      setLoading(false);
    }
  }

  async function analyzeFolder(event: React.ChangeEvent<HTMLInputElement>) {
    const selectedFiles = Array.from(event.target.files || []);
    event.target.value = "";
    if (!selectedFiles.length) return;

    setLoading(true);
    setError("");
    setResult(null);
    setLocalSources({});
    setCodebaseAnswer("");
    setCodebaseSources([]);
    setCodebaseError("");
    setUrl("");

    try {
      const supported = selectedFiles.filter((file) => {
        const path = file.webkitRelativePath || file.name;
        const ignored = [".git/", "node_modules/", ".next/", "dist/", "build/", "venv/", ".venv/", "__pycache__/"];
        const suffixes = [".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".java", ".go", ".rs", ".c", ".h", ".cpp", ".cs", ".php", ".rb", ".swift", ".kt", ".vue", ".svelte", ".html", ".css", ".scss", ".json", ".yaml", ".yml", ".toml", ".md", ".sql", ".sh"];
        return !ignored.some((part) => path.split("/").includes(part.slice(0, -1))) &&
          suffixes.some((suffix) => path.toLowerCase().endsWith(suffix));
      }).slice(0, 1000);

      const sources: Record<string, string> = {};
      const payloadFiles: Array<{ path: string; content: string }> = [];
      let totalBytes = 0;

      for (const file of supported) {
        if (file.size > 256 * 1024) continue;
        totalBytes += file.size;
        if (totalBytes > 64 * 1024 * 1024) throw new Error("Selected source files exceed the 64 MB limit.");
        const content = await file.text();
        const path = file.webkitRelativePath || file.name;
        sources[path] = content;
        payloadFiles.push({ path, content });
      }

      if (!payloadFiles.length) throw new Error("No supported source files found within the size limits.");
      const folderName = (selectedFiles[0].webkitRelativePath || selectedFiles[0].name).split("/")[0];
      const projectId = crypto.randomUUID().replaceAll("-", "");
      const response = await fetch(`${API_BASE}/api/repository/analyze-folder`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ folder_name: folderName, project_id: projectId, files: payloadFiles }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Folder analysis failed.");
      setLocalSources(sources);
      setResult(payload);
      setExpandedFolders({});
      setSelected(null);
      setSource(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not analyze this folder.");
    } finally {
      setLoading(false);
    }
  }

  function exportMermaid() {
    if (!result) return;
    const visibleIds = new Set(visibleGraphNodes.map((node) => node.id));
    const nodes = result.nodes.filter((node) => visibleIds.has(node.id));
    const edges = result.edges.filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target));
    const blob = new Blob([toMermaid(nodes, edges)], { type: "text/plain;charset=utf-8" });
    const href = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = href;
    anchor.download = `codemap-${activeFolder === "all" ? "architecture" : activeFolder.replaceAll("/", "-")}.mmd`;
    anchor.click();
    URL.revokeObjectURL(href);
  }

  function exportJson() {
    if (!result) return;
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json;charset=utf-8" });
    const href = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = href;
    anchor.download = `codemap-${result.repository.replace(/[^a-z0-9-_]/gi, "-")}-analysis.json`;
    anchor.click();
    URL.revokeObjectURL(href);
  }

  async function exportPdf() {
    if (!result) return;
    setReportError("");
    setReportStatus("Generating PDF report…");
    try {
      const reportResult = { ...result } as AnalysisResult & { source_contents?: unknown };
      delete reportResult.source_contents;
      const response = await fetch(`${API_BASE}/api/reports/architecture.pdf`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ result: reportResult }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || "PDF report generation failed.");
      }
      const blob = await response.blob();
      const href = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = href;
      anchor.download = `codemap-${result.repository.replace(/[^a-z0-9-_]/gi, "-")}-report.pdf`;
      anchor.click();
      URL.revokeObjectURL(href);
      setReportStatus("PDF report downloaded.");
    } catch (err) {
      setReportError(err instanceof Error ? err.message : "Could not generate PDF report.");
      setReportStatus("");
    }
  }

  async function saveReportSnapshot() {
    if (!result) return;
    setReportError("");
    setReportStatus("Saving analysis snapshot…");
    try {
      const reportResult = { ...result } as AnalysisResult & { source_contents?: unknown };
      delete reportResult.source_contents;
      const response = await fetch(`${API_BASE}/api/reports/snapshots`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ result: reportResult }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Could not save snapshot.");
      setReportStatus(`Snapshot saved · ${payload.snapshot_id.slice(0, 8)}`);
    } catch (err) {
      setReportError(err instanceof Error ? err.message : "Could not save snapshot.");
      setReportStatus("");
    }
  }

  async function compareReportSnapshots() {
    if (!result) return;
    setReportError("");
    setReportStatus("Comparing latest snapshots…");
    try {
      const response = await fetch(`${API_BASE}/api/reports/compare/${encodeURIComponent(result.project_id)}`);
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Save two snapshots before comparing.");
      setReportComparison(payload);
      setReportStatus("Latest two snapshots compared.");
    } catch (err) {
      setReportError(err instanceof Error ? err.message : "Could not compare snapshots.");
      setReportStatus("");
    }
  }

  async function exportPng() {
    if (!result || !visibleGraphNodes.length) return;
    const width = 205;
    const height = 126;
    const padding = 72;
    const minX = Math.min(...visibleGraphNodes.map((node) => node.position.x));
    const minY = Math.min(...visibleGraphNodes.map((node) => node.position.y));
    const maxX = Math.max(...visibleGraphNodes.map((node) => node.position.x + width));
    const maxY = Math.max(...visibleGraphNodes.map((node) => node.position.y + height));
    const svgWidth = maxX - minX + padding * 2;
    const svgHeight = maxY - minY + padding * 2;
    const positions = new Map(visibleGraphNodes.map((node) => [
      node.id,
      { x: node.position.x - minX + padding, y: node.position.y - minY + padding },
    ]));
    const visibleIds = new Set(visibleGraphNodes.map((node) => node.id));
    const sourceNodes = result.nodes.filter((node) => visibleIds.has(node.id));
        const escapeSvg = (value: string) => value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
    const edges = result.edges.filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target));
    const edgeMarkup = edges.map((edge) => {
      const from = positions.get(edge.source);
      const to = positions.get(edge.target);
      if (!from || !to) return "";
      const startX = from.x + width;
      const startY = from.y + height / 2;
      const endX = to.x;
      const endY = to.y + height / 2;
      const curve = Math.max(45, Math.abs(endX - startX) / 2);
      return `<path d="M ${startX} ${startY} C ${startX + curve} ${startY}, ${endX - curve} ${endY}, ${endX} ${endY}" fill="none" stroke="#818cf8" stroke-width="2" marker-end="url(#arrow)" opacity="0.82"/>`;
    }).join("");
    const nodeMarkup = sourceNodes.map((node) => {
      const point = positions.get(node.id)!;
      const style = getLanguageStyle(node.language);
      return `<g transform="translate(${point.x} ${point.y})">
        <rect width="${width}" height="${height}" rx="14" fill="${style.background}" stroke="${style.border}" stroke-width="2"/>
        <text x="16" y="25" fill="${style.text}" font-size="11" font-weight="700">${escapeSvg(node.language.toUpperCase())}</text>
        <text x="16" y="53" fill="#f8fafc" font-size="14" font-weight="700">${escapeSvg(node.label.slice(0, 25))}</text>
        <text x="16" y="76" fill="#94a3b8" font-size="10">${escapeSvg(node.path.slice(0, 31))}</text>
        <text x="16" y="105" fill="#64748b" font-size="10">${node.lines} lines</text>
      </g>`;
    }).join("");
    const title = activeFolder === "all" ? "CodeMap Architecture" : `CodeMap · ${activeFolder}`;
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${svgWidth}" height="${svgHeight}" viewBox="0 0 ${svgWidth} ${svgHeight}">
      <defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#818cf8"/></marker></defs>
      <rect width="100%" height="100%" fill="#080d17"/>
      <text x="${padding}" y="38" fill="#e2e8f0" font-size="20" font-weight="700">${escapeSvg(title)}</text>
      <text x="${padding}" y="57" fill="#64748b" font-size="11">${sourceNodes.length} files · ${edges.length} dependencies · Exported from CodeMap</text>
      ${edgeMarkup}${nodeMarkup}
    </svg>`;
    const svgUrl = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml;charset=utf-8" }));
    try {
      const image = new Image();
      await new Promise<void>((resolve, reject) => {
        image.onload = () => resolve();
        image.onerror = () => reject(new Error("Could not render the architecture image."));
        image.src = svgUrl;
      });
      const scale = Math.min(2, 12000 / svgWidth, 12000 / svgHeight);
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(svgWidth * scale));
      canvas.height = Math.max(1, Math.round(svgHeight * scale));
      const context = canvas.getContext("2d");
      if (!context) throw new Error("PNG export is not supported by this browser.");
      context.scale(scale, scale);
      context.drawImage(image, 0, 0);
      const png = await new Promise<Blob>((resolve, reject) => {
        canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error("PNG rendering failed.")), "image/png");
      });
      const pngUrl = URL.createObjectURL(png);
      const anchor = document.createElement("a");
      anchor.href = pngUrl;
      anchor.download = `codemap-${activeFolder === "all" ? "architecture" : activeFolder.replaceAll("/", "-")}.png`;
      anchor.click();
      URL.revokeObjectURL(pngUrl);
    } finally {
      URL.revokeObjectURL(svgUrl);
    }
  }

  function renderTree(items: FileTreeItem[], depth = 0): React.ReactNode {
    return items.map((item) => {
      if (!hasTreeMatch(item, query)) return null;
      if (item.isFolder) {
        const isExpanded = query ? true : (expandedFolders[item.path] ?? depth === 0);
        const FolderIcon = isExpanded ? FolderOpen : Folder;
        return (
          <div key={item.path}>
            <button onClick={() => setExpandedFolders((current) => ({ ...current, [item.path]: !current[item.path] }))}
              className="flex w-full items-center gap-2 rounded-lg py-2 pr-2 text-left text-xs text-slate-300 hover:bg-white/5"
              style={{ paddingLeft: 8 + depth * 14 }}>
              {isExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
              <FolderIcon size={14} className="text-amber-300" />
              <span className="truncate">{item.name}</span>
              <span className="ml-auto text-[10px] text-slate-600">{item.children.length}</span>
            </button>
            {isExpanded && <div>{renderTree(item.children, depth + 1)}</div>}
          </div>
        );
      }
      const Icon = getFileIcon(item.path);
      return (
        <button key={item.path} onClick={() => { void openSource(item.path); }}
          className={`flex w-full items-center gap-2 rounded-lg py-2 pr-2 text-left text-xs transition ${selected === item.path ? "bg-indigo-500/20 text-indigo-200" : "text-slate-400 hover:bg-white/5"}`}
          style={{ paddingLeft: 28 + depth * 14 }} title={item.path}>
          <Icon size={14} className="shrink-0 text-indigo-300" />
          <span className="truncate">{item.name}</span>
        </button>
      );
    });
  }

  const selectedNode = result?.nodes.find((node) => node.id === selected);

  return (
    <main className="min-h-screen px-5 py-6 md:px-10">
      <header className="mx-auto flex max-w-[1500px] items-center justify-between border-b border-white/10 pb-5">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-indigo-500/15 p-2.5 text-indigo-300"><Boxes size={22} /></div>
          <div><div className="text-lg font-bold tracking-tight">CodeMap</div><div className="text-[10px] tracking-[0.2em] text-slate-500">CODEBASE INTELLIGENCE</div></div>
        </div>
        <div className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs ${
          ollamaState === "ready" ? "border-emerald-400/20 bg-emerald-400/5 text-emerald-300" :
          ollamaState === "offline" ? "border-rose-400/20 bg-rose-400/5 text-rose-300" :
          "border-amber-400/20 bg-amber-400/5 text-amber-300"
        }`}><ShieldCheck size={14} /> {
          ollamaState === "checking" ? "Checking Ollama…" :
          ollamaState === "ready" ? "Qwen3.5 ready" :
          ollamaState === "missing" ? "Model will auto-download" : "Ollama offline"
        }</div>
      </header>

      <section className="mx-auto max-w-[1500px] py-10">
        <div className="mb-8 max-w-3xl">
          <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.22em] text-indigo-300"><Sparkles size={14} /> See how your code connects</div>
          <h1 className="text-4xl font-semibold tracking-tight md:text-5xl">Every file has a place.<br /><span className="text-indigo-300">See the whole system.</span></h1>
          <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-400">Map repository dependencies, navigate source files, and uncover the structure behind your project. Your AI stays local with Ollama.</p>
        </div>

        <div className="flex flex-col gap-3 rounded-2xl border border-white/10 bg-white/[0.035] p-3 md:flex-row">
          <form onSubmit={analyze} className="flex min-w-0 flex-1 flex-col gap-3 md:flex-row">
          <div className="flex flex-1 items-center gap-3 rounded-xl border border-white/10 bg-[#080d17] px-4">
            <Github size={18} className="text-slate-500" />
            <input value={url} onChange={(event) => setUrl(event.target.value)} required type="url" placeholder="https://github.com/owner/repository" className="h-12 w-full bg-transparent text-sm outline-none placeholder:text-slate-600" />
          </div>
          <button disabled={loading} className="flex items-center justify-center gap-2 rounded-xl bg-indigo-500 px-6 py-3 text-sm font-semibold text-white transition hover:bg-indigo-400 disabled:opacity-60">
            {loading ? <LoaderCircle className="animate-spin" size={17} /> : <ArrowRight size={17} />} {loading ? "Mapping..." : "Generate map"}
          </button>
          </form>
          <label className="flex cursor-pointer items-center justify-center gap-2 rounded-xl border border-indigo-400/30 bg-indigo-500/10 px-5 py-3 text-sm font-semibold text-indigo-200 transition hover:bg-indigo-500/20">
            <FolderOpen size={17} /> Select project folder
            <input type="file" multiple onChange={analyzeFolder} className="hidden" {...({ webkitdirectory: "" } as React.InputHTMLAttributes<HTMLInputElement> & { webkitdirectory: string })} />
          </label>
          <label className="flex cursor-pointer items-center justify-center gap-2 rounded-xl border border-cyan-400/30 bg-cyan-500/10 px-5 py-3 text-sm font-semibold text-cyan-200 transition hover:bg-cyan-500/20">
            <FileArchive size={17} /> Upload ZIP
            <input type="file" accept=".zip,application/zip" onChange={analyzeZip} className="hidden" />
          </label>
        </div>
        {error && <p role="alert" className="mt-3 rounded-xl border border-rose-400/20 bg-rose-400/5 p-3 text-sm text-rose-300">{error}</p>}

        {result ? (
          <div className="mt-6 grid gap-4 lg:grid-cols-[minmax(0,1fr)_290px]">
            <section className="overflow-hidden rounded-2xl border border-white/10 bg-[#0b1220]">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-5 py-4">
                <div><div className="font-semibold">{result.repository}</div><div className="mt-1 text-xs text-slate-500">Branch: {result.default_branch}</div></div>
                <div className="flex flex-wrap gap-2">
                  <button onClick={exportPng} className="rounded-lg border border-indigo-400/30 bg-indigo-500/10 px-3 py-2 text-xs text-indigo-200 hover:bg-indigo-500/20">Export PNG</button>
                  <button onClick={exportMermaid} className="rounded-lg border border-white/10 px-3 py-2 text-xs text-slate-300 hover:bg-white/5">Export Mermaid</button>
                  <button onClick={exportJson} className="rounded-lg border border-white/10 px-3 py-2 text-xs text-slate-300 hover:bg-white/5">Export JSON</button>
                  <button onClick={exportPdf} className="rounded-lg border border-cyan-400/30 bg-cyan-500/10 px-3 py-2 text-xs text-cyan-200 hover:bg-cyan-500/20">PDF report</button>
                  <button onClick={saveReportSnapshot} className="rounded-lg border border-white/10 px-3 py-2 text-xs text-slate-300 hover:bg-white/5">Save snapshot</button>
                  <button onClick={compareReportSnapshots} className="rounded-lg border border-amber-400/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200 hover:bg-amber-500/20">Compare snapshots</button>
                </div>
              </div>
              {(reportStatus || reportError) && <div className="border-b border-white/10 px-4 py-2">
                {reportStatus && <p className="text-[11px] text-emerald-300">{reportStatus}</p>}
                {reportError && <p role="alert" className="text-[11px] text-rose-300">{reportError}</p>}
              </div>}
              {reportComparison && <div className="border-b border-white/10 px-4 py-4">
                <div className="mb-2 text-xs font-semibold text-amber-200">Before / after comparison</div>
                <div className="grid gap-2 sm:grid-cols-3">
                  {[
                    ["Health score", reportComparison.changes.health_score],
                    ["Potential findings", reportComparison.changes.bugs_total],
                    ["High-risk modules", reportComparison.changes.high_risk_modules],
                    ["High severity", reportComparison.changes.bugs_high],
                    ["Dependencies", reportComparison.changes.dependencies],
                    ["Circular groups", reportComparison.changes.circular_groups],
                  ].map(([label, change]: any) => (
                    <div key={label} className="rounded-lg bg-black/20 p-2">
                      <div className="text-[10px] text-slate-500">{label}</div>
                      <div className="mt-1 text-sm font-semibold tabular-nums">{change.before} → {change.after}</div>
                      <div className="text-[10px] text-slate-400">Change: {change.delta > 0 ? "+" : ""}{change.delta}</div>
                    </div>
                  ))}
                </div>
                <p className="mt-2 text-[10px] text-slate-500">{reportComparison.note}</p>
              </div>}
              <div className="border-b border-white/10 px-4 py-3">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <span className="font-semibold uppercase tracking-wider text-[10px] text-slate-500">Folder navigation</span>
                  <span className="text-[10px] text-slate-500">{visibleGraphNodes.length} of {result.nodes.length} files · {visibleGraphEdges.length} connections</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button onClick={() => { setActiveFolder("all"); setShowDisconnected(false); }}
                    className={"rounded-full border px-3 py-1.5 text-[10px] " + (activeFolder === "all" ? "border-indigo-400/40 bg-indigo-500/15 text-indigo-200" : "border-white/10 bg-white/[0.04] text-slate-400 hover:bg-white/10")}>All folders</button>
                  {folderOptions.map((folder) => (
                    <button key={folder} onClick={() => { setActiveFolder(folder); setShowDisconnected(false); }}
                      className={"rounded-full border px-3 py-1.5 text-[10px] " + (activeFolder === folder ? "border-indigo-400/40 bg-indigo-500/15 text-indigo-200" : "border-white/10 bg-white/[0.04] text-slate-400 hover:bg-white/10")}>{folder}</button>
                  ))}
                </div>
                <div className="mt-2 text-[10px] text-slate-500">Arrow direction = importer to imported file</div>
              </div>
              <div className="flex flex-wrap items-center gap-2 border-b border-white/10 px-4 py-3">
                <span className="mr-auto text-[11px] text-slate-500">{graphMetrics.disconnected.length} disconnected · {graphMetrics.important.length} core candidates</span>
                <button onClick={() => setHighlightDependencies((value) => !value)} className={"rounded-lg border px-3 py-2 text-[11px] " + (highlightDependencies ? "border-indigo-400/30 bg-indigo-500/10 text-indigo-200" : "border-white/10 text-slate-400")}>{highlightDependencies ? "Dependency path: on" : "Dependency path: off"}</button>
                <button onClick={() => setShowDisconnected((value) => !value)} className={"rounded-lg border px-3 py-2 text-[11px] " + (showDisconnected ? "border-amber-400/30 bg-amber-500/10 text-amber-200" : "border-white/10 text-slate-400")}>{showDisconnected ? "Show all files" : "Inspect disconnected"}</button>
              </div>
              <div className="h-[620px]">
                <ReactFlow key={`${activeFolder}-${showDisconnected}`} nodes={visibleGraphNodes} edges={visibleGraphEdges} fitView onNodeClick={(_, node) => { void openSource(node.id); }} minZoom={0.15}>
                  <Background color="#334155" gap={24} />
                  <MiniMap nodeColor="#6366f1" maskColor="rgba(8,13,23,0.7)" />
                  <Controls />
                </ReactFlow>
              </div>
            </section>
            <aside className="space-y-4">
              <div className="rounded-2xl border border-white/10 bg-white/[0.025] p-5">
                <div className="mb-4 flex items-center gap-2 text-sm font-semibold"><Workflow size={16} className="text-indigo-300" /> Analysis overview</div>
                <div className="grid grid-cols-2 gap-3">
                  <Metric label="Files" value={result.stats.files_analyzed} />
                  <Metric label="Connections" value={result.stats.dependencies_found} />
                  <Metric label="Unresolved" value={result.stats.relative_imports_unresolved} />
                  <Metric label="Not fetched" value={result.stats.files_not_fetched} />
                </div>
              </div>
              <div className="rounded-2xl border border-cyan-400/20 bg-cyan-400/[0.035] p-5">
                <div className="mb-2 flex items-center gap-2 text-sm font-semibold"><Sparkles size={16} className="text-cyan-300" /> Ask your codebase</div>
                <div className="mb-3 flex items-center justify-between gap-2">
                  <p className="text-[10px] leading-5 text-slate-500">Local retrieval index · {result.indexed_chunks} source chunks · project-isolated</p>
                  {result.indexed_chunks > 0 && <button type="button" onClick={() => { void clearCodebaseIndex(); }} disabled={codebaseClearLoading}
                    className="shrink-0 text-[10px] text-rose-300 hover:text-rose-200 disabled:opacity-50">{codebaseClearLoading ? "Clearing…" : "Clear index"}</button>}
                </div>
                <form onSubmit={askCodebase} className="space-y-2">
                  <textarea value={codebaseQuestion} onChange={(event) => setCodebaseQuestion(event.target.value)}
                    placeholder="How does authentication work? Where is the database connection created?"
                    rows={3} maxLength={2000}
                    className="w-full resize-y rounded-lg border border-white/10 bg-[#080d17] p-3 text-xs text-slate-200 outline-none placeholder:text-slate-600 focus:border-cyan-400/40" />
                  <button disabled={codebaseLoading || !codebaseQuestion.trim() || result.indexed_chunks === 0}
                    className="flex w-full items-center justify-center gap-2 rounded-lg bg-cyan-500/15 px-3 py-2.5 text-xs font-semibold text-cyan-200 hover:bg-cyan-500/25 disabled:opacity-50">
                    {codebaseLoading ? <LoaderCircle size={14} className="animate-spin" /> : <Sparkles size={14} />}
                    {codebaseLoading ? "Searching and thinking…" : result.indexed_chunks === 0 ? "Re-analyze to enable Q&A" : "Ask local codebase"}
                  </button>
                </form>
                {codebaseError && <p role="alert" className="mt-3 rounded-lg border border-rose-400/20 bg-rose-400/5 p-2 text-xs text-rose-300">{codebaseError}</p>}
                {codebaseAnswer && <div className="mt-3 whitespace-pre-wrap rounded-lg bg-black/20 p-3 text-xs leading-6 text-slate-300">{codebaseAnswer}</div>}
                {codebaseSources.length > 0 && <div className="mt-3 border-t border-white/10 pt-3">
                  <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Retrieved source chunks</div>
                  {codebaseSources.map((item, index) => <div key={item.path + index} className="mb-1 truncate text-[10px] text-cyan-200">{item.path}:{item.start_line}</div>)}
                </div>}
              </div>
              {dependencyDrilldown && (
                <div className="rounded-2xl border border-indigo-400/20 bg-indigo-400/[0.04] p-5">
                  <div className="mb-3 flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 text-sm font-semibold"><Workflow size={16} className="text-indigo-300" /> Dependency drilldown</div>
                    <button onClick={() => setSelected(null)} className="rounded-lg border border-white/10 px-2.5 py-1.5 text-[10px] text-slate-400 hover:bg-white/5">Clear focus</button>
                  </div>
                  <div className="mb-3 break-all rounded-lg bg-black/20 px-3 py-2 text-xs font-semibold text-indigo-200">{selected}</div>
                  <div className="mb-4 grid grid-cols-2 gap-2">
                    <Metric label="Imports" value={dependencyDrilldown.outgoing.length} />
                    <Metric label="Imported by" value={dependencyDrilldown.incoming.length} />
                    <Metric label="Downstream files" value={dependencyDrilldown.downstream.length} />
                    <Metric label="Upstream files" value={dependencyDrilldown.upstream.length} />
                  </div>
                  <div className="mb-4">
                    <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Direct dependencies · imports</div>
                    {dependencyDrilldown.outgoing.length ? dependencyDrilldown.outgoing.map((path) => (
                      <button key={path} onClick={() => { void openSource(path); }} className="mb-1 block w-full truncate rounded-lg bg-black/20 px-3 py-2 text-left text-[11px] text-cyan-200 hover:bg-white/5">{path}</button>
                    )) : <p className="text-xs text-slate-500">No locally resolved imports.</p>}
                  </div>
                  <div className="mb-4">
                    <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Direct dependents · imported by</div>
                    {dependencyDrilldown.incoming.length ? dependencyDrilldown.incoming.map((path) => (
                      <button key={path} onClick={() => { void openSource(path); }} className="mb-1 block w-full truncate rounded-lg bg-black/20 px-3 py-2 text-left text-[11px] text-emerald-200 hover:bg-white/5">{path}</button>
                    )) : <p className="text-xs text-slate-500">No analyzed files import this file.</p>}
                  </div>
                  {impactAnalysis && (
                    <div className="mb-4 rounded-xl border border-amber-400/15 bg-amber-400/[0.035] p-3">
                      <div className="mb-3 flex items-center justify-between gap-2">
                        <div className="text-[10px] font-semibold uppercase tracking-wider text-amber-200">Change impact estimate</div>
                        <span className="rounded-full bg-black/20 px-2 py-1 text-[9px] uppercase text-amber-200">{impactAnalysis.radius} impact</span>
                      </div>
                      <div className="mb-3 grid grid-cols-2 gap-2">
                        <Metric label="Affected files" value={impactAnalysis.affected.length} />
                        <Metric label="Affected modules" value={impactAnalysis.affectedModules.length} />
                      </div>
                      {impactAnalysis.affectedModules.length ? impactAnalysis.affectedModules.map((module) => (
                        <div key={module.name} className="mb-2 rounded-lg bg-black/20 p-2">
                          <div className="mb-1 flex justify-between gap-2 text-[11px]"><span className="truncate text-slate-200">{module.name}</span><span className="text-amber-200">{module.paths.length}</span></div>
                          {module.paths.slice(0, 5).map((path) => <button key={path} onClick={() => { void openSource(path); }} className="mt-1 block w-full truncate text-left text-[10px] text-slate-400 hover:text-amber-200">{path}</button>)}
                          {module.paths.length > 5 && <p className="mt-1 text-[9px] text-slate-600">+{module.paths.length - 5} more</p>}
                        </div>
                      )) : <p className="text-xs text-slate-500">No other analyzed files depend on this file.</p>}
                      <p className="mt-2 text-[9px] leading-4 text-slate-600">Estimated from reverse import links only; dynamic/runtime effects may be missing.</p>
                    </div>
                  )}
                  <div className="mb-3">
                    <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Dependency paths · downstream</div>
                    {dependencyDrilldown.downstream.length ? dependencyDrilldown.downstream.slice(0, 12).map((item) => (
                      <button key={item.path} onClick={() => { void openSource(item.path); }} className="mb-1 flex w-full items-center justify-between gap-2 rounded-lg bg-black/20 px-3 py-2 text-left hover:bg-white/5">
                        <span className="truncate text-[11px] text-slate-300">{item.path}</span>
                        <span className="shrink-0 text-[10px] tabular-nums text-indigo-300">depth {item.depth}</span>
                      </button>
                    )) : <p className="text-xs text-slate-500">No downstream dependency path found.</p>}
                  </div>
                  <div>
                    <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Dependency paths · upstream</div>
                    {dependencyDrilldown.upstream.length ? dependencyDrilldown.upstream.slice(0, 12).map((item) => (
                      <button key={item.path} onClick={() => { void openSource(item.path); }} className="mb-1 flex w-full items-center justify-between gap-2 rounded-lg bg-black/20 px-3 py-2 text-left hover:bg-white/5">
                        <span className="truncate text-[11px] text-slate-300">{item.path}</span>
                        <span className="shrink-0 text-[10px] tabular-nums text-emerald-300">depth {item.depth}</span>
                      </button>
                    )) : <p className="text-xs text-slate-500">No upstream dependency path found.</p>}
                  </div>
                  <p className="mt-3 text-[10px] leading-4 text-slate-600">Paths include only dependencies resolved inside the analyzed file set. Dynamic imports and external packages may not appear.</p>
                </div>
              )}
              <div className="rounded-2xl border border-white/10 bg-white/[0.025] p-5">
                <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-2 text-sm font-semibold"><Network size={16} className="text-indigo-300" /> Architecture intelligence</div>
                  <button onClick={() => { void explainArchitecture(); }} disabled={architectureAiLoading}
                    className="rounded-lg border border-indigo-400/30 bg-indigo-500/10 px-3 py-2 text-[11px] font-medium text-indigo-200 hover:bg-indigo-500/20 disabled:opacity-50">
                    {architectureAiLoading ? "Explaining…" : "Explain architecture with AI"}
                  </button>
                </div>
                {architectureAiError && <p role="alert" className="mb-3 rounded-lg border border-rose-400/20 bg-rose-400/5 p-2 text-xs text-rose-300">{architectureAiError}</p>}
                {architectureExplanation && <div className="mb-4 whitespace-pre-wrap rounded-xl border border-indigo-400/20 bg-indigo-400/[0.05] p-3 text-xs leading-6 text-slate-300">{architectureExplanation}</div>}
                <div className="mb-4 grid grid-cols-3 gap-2">
                  <Metric label="Entry points" value={result.architecture_insights.architecture_stats.entry_points} />
                  <Metric label="Cycles" value={result.architecture_insights.architecture_stats.circular_dependency_groups} />
                  <Metric label="Modules" value={result.architecture_insights.architecture_stats.top_level_modules} />
                </div>
                <div className="mb-4 rounded-xl border border-white/10 bg-black/20 p-3">
                  <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Detected frameworks</div>
                  <div className="flex flex-wrap gap-2">
                    {result.advanced_architecture.frameworks.length ? result.advanced_architecture.frameworks.map((framework) => (
                      <span key={framework} className="rounded-full border border-indigo-400/20 bg-indigo-400/10 px-2.5 py-1 text-[11px] text-indigo-200">{framework}</span>
                    )) : <span className="text-xs text-slate-500">No supported framework detected from manifests.</span>}
                  </div>
                </div>
                <div className="mb-4 rounded-xl border border-white/10 bg-black/20 p-3">
                  <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Framework-aware entry points ({result.advanced_architecture.entry_points.length})</div>
                  {result.advanced_architecture.entry_points.length ? result.advanced_architecture.entry_points.map((entry) => (
                    <button key={`${entry.path}:${entry.framework}:${entry.reason}`} onClick={() => { void openSource(entry.path); }} className="mb-1 block w-full rounded-lg bg-white/[0.03] px-2.5 py-2 text-left hover:bg-white/[0.07]">
                      <span className="block truncate text-xs text-slate-200">{entry.path}</span>
                      <span className="mt-1 block text-[10px] text-slate-500">{entry.framework} · {entry.reason}</span>
                    </button>
                  )) : <p className="text-xs text-slate-500">No framework-aware entry point detected.</p>}
                </div>
                <div className="mb-4 grid gap-3 lg:grid-cols-2">
                  <div className="rounded-xl border border-white/10 bg-black/20 p-3">
                    <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">API endpoints ({result.advanced_architecture.api_endpoints.length})</div>
                    <div className="max-h-56 space-y-1 overflow-y-auto">
                      {result.advanced_architecture.api_endpoints.length ? result.advanced_architecture.api_endpoints.map((endpoint) => (
                        <button key={`${endpoint.path}:${endpoint.line}:${endpoint.method}:${endpoint.route}`} onClick={() => { void openSource(endpoint.path); }} className="block w-full rounded-lg bg-white/[0.03] px-2.5 py-2 text-left hover:bg-white/[0.07]">
                          <span className="mr-2 rounded bg-emerald-400/10 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-300">{endpoint.method}</span>
                          <span className="text-xs text-slate-200">{endpoint.route}</span>
                          <span className="mt-1 block truncate text-[10px] text-slate-500">{endpoint.path}:{endpoint.line} · {endpoint.framework}</span>
                        </button>
                      )) : <p className="text-xs text-slate-500">No statically recognized API routes.</p>}
                    </div>
                  </div>
                  <div className="rounded-xl border border-white/10 bg-black/20 p-3">
                    <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Database relationships ({result.advanced_architecture.database_relations.length})</div>
                    <div className="max-h-56 space-y-1 overflow-y-auto">
                      {result.advanced_architecture.database_relations.length ? result.advanced_architecture.database_relations.map((relation) => (
                        <button key={`${relation.path}:${relation.line}:${relation.source_model}:${relation.target}`} onClick={() => { void openSource(relation.path); }} className="block w-full rounded-lg bg-white/[0.03] px-2.5 py-2 text-left hover:bg-white/[0.07]">
                          <span className="text-xs text-slate-200">{relation.source_model} → {relation.target}</span>
                          <span className="mt-1 block truncate text-[10px] text-slate-500">{relation.path}:{relation.line} · {relation.kind}</span>
                        </button>
                      )) : <p className="text-xs text-slate-500">No supported static relationship patterns found.</p>}
                    </div>
                  </div>
                </div>
                <div className="mb-4 rounded-xl border border-white/10 bg-black/20 p-3">
                  <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Cross-module dependencies ({result.advanced_architecture.module_dependencies.length})</div>
                  {result.advanced_architecture.module_dependencies.length ? result.advanced_architecture.module_dependencies.slice(0, 10).map((dependency) => (
                    <div key={`${dependency.source}:${dependency.target}`} className="flex items-center justify-between gap-3 border-b border-white/5 py-1.5 text-xs last:border-0">
                      <span className="min-w-0 truncate text-slate-300">{dependency.source} → {dependency.target}</span>
                      <span className="shrink-0 text-slate-500">{dependency.imports} imports</span>
                    </div>
                  )) : <p className="text-xs text-slate-500">No cross-module import links detected.</p>}
                </div>
                <div className="space-y-3">
                  <div>
                    <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Entry-point candidates</div>
                    {result.architecture_insights.entry_points.length ? result.architecture_insights.entry_points.map((item) => (
                      <button key={item.path} onClick={() => { void openSource(item.path); }} className="mb-1 block w-full truncate rounded-lg bg-black/20 px-3 py-2 text-left text-xs text-indigo-200 hover:bg-white/5">{item.path}</button>
                    )) : <p className="text-xs text-slate-500">No recognized entry-point filenames found.</p>}
                  </div>
                  <div>
                    <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Circular dependencies</div>
                    {result.architecture_insights.circular_dependencies.length ? result.architecture_insights.circular_dependencies.map((cycle, index) => (
                      <div key={index} className="mb-2 rounded-lg border border-amber-400/20 bg-amber-400/5 p-2 text-[11px] leading-5 text-amber-200">{cycle.join(" ↔ ")}</div>
                    )) : <p className="text-xs text-emerald-300">No circular imports detected.</p>}
                  </div>
                  <div>
                    <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Top-level modules</div>
                    <div className="space-y-1">
                      {result.architecture_insights.module_groups.slice(0, 8).map((group) => (
                        <div key={group.name} className="flex items-center justify-between rounded-lg bg-black/20 px-3 py-2 text-xs"><span className="truncate text-slate-300">{group.name}</span><span className="ml-3 tabular-nums text-slate-500">{group.files} files</span></div>
                      ))}
                    </div>
                  </div>
                </div>
                <p className="mt-3 text-[10px] leading-4 text-slate-600">{result.architecture_insights.architecture_note}</p>
                <p className="mt-2 text-[10px] leading-4 text-slate-600">{result.advanced_architecture.note}</p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/[0.025] p-5">
                <div className="mb-4 flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2 text-sm font-semibold"><ShieldCheck size={16} className="text-emerald-300" /> Architecture health</div>
                  <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${result.architecture_health.health_grade === "healthy" ? "bg-emerald-400/10 text-emerald-300" : result.architecture_health.health_grade === "watch" ? "bg-amber-400/10 text-amber-300" : "bg-rose-400/10 text-rose-300"}`}>{result.architecture_health.health_score}/100 · {result.architecture_health.health_grade.replaceAll("_", " ")}</span>
                </div>
                <div className="mb-4 grid grid-cols-3 gap-2">
                  <Metric label="High risk" value={result.architecture_health.health_stats.high_risk_modules} />
                  <Metric label="Medium risk" value={result.architecture_health.health_stats.medium_risk_modules} />
                  <Metric label="Cycle files" value={result.architecture_health.health_stats.circular_files} />
                </div>
                <div className="mb-4">
                  <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Risk factors</div>
                  {result.architecture_health.risk_factors.map((factor) => <p key={factor} className="mb-1 rounded-lg bg-black/20 px-3 py-2 text-xs text-slate-300">{factor}</p>)}
                </div>
                <div className="mb-3">
                  <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Module complexity & risk</div>
                  {result.architecture_health.module_health.slice(0, 8).map((module) => (
                    <button key={module.name} onClick={() => { setActiveFolder(module.name); setShowDisconnected(false); }} className="mb-2 block w-full rounded-lg bg-black/20 p-3 text-left hover:bg-white/5">
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate text-xs font-semibold text-slate-200">{module.name}</span>
                        <span className={`text-[10px] uppercase ${module.risk_level === "high" ? "text-rose-300" : module.risk_level === "medium" ? "text-amber-300" : "text-emerald-300"}`}>{module.risk_level} risk</span>
                      </div>
                      <div className="mt-2 grid grid-cols-2 gap-2 text-[10px] text-slate-500">
                        <span>Complexity {module.complexity_score}/100</span><span>Risk {module.risk_score}/100</span>
                        <span>{module.files} files · {module.lines} lines</span><span>{module.dependencies} dependencies</span>
                      </div>
                      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10"><div className="h-full rounded-full bg-indigo-400" style={{ width: `${module.complexity_score}%` }} /></div>
                    </button>
                  ))}
                  {!result.architecture_health.module_health.length && <p className="text-xs text-slate-500">No module groups available.</p>}
                </div>
                <p className="text-[10px] leading-4 text-slate-600">{result.architecture_health.health_note}</p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/[0.025] p-5">
                <div className="mb-4 flex items-center gap-2 text-sm font-semibold"><Network size={16} className="text-cyan-300" /> Code intelligence pro</div>
                <div className="mb-4 grid grid-cols-3 gap-2">
                  <Metric label="Max depth" value={result.code_intelligence.dependency_depth.max_depth} />
                  <Metric label="Reachable" value={result.code_intelligence.dependency_depth.reachable_files} />
                  <Metric label="Unreachable" value={result.code_intelligence.dependency_depth.unreachable_files} />
                </div>
                <div className="mb-4">
                  <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Bottleneck candidates</div>
                  {result.code_intelligence.bottleneck_files.length ? result.code_intelligence.bottleneck_files.map((item) => (
                    <button key={item.path} onClick={() => { void openSource(item.path); }} className="mb-2 block w-full rounded-lg bg-black/20 px-3 py-2 text-left hover:bg-white/5">
                      <span className="block truncate text-xs text-cyan-200">{item.path}</span>
                      <span className="mt-1 block text-[10px] text-slate-500">Used by {item.fan_in} files · imports {item.fan_out} files</span>
                    </button>
                  )) : <p className="text-xs text-slate-500">No high-connectivity bottlenecks detected.</p>}
                </div>
                <div className="mb-3">
                  <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Unreferenced in analyzed graph</div>
                  {result.code_intelligence.unreferenced_files.length ? result.code_intelligence.unreferenced_files.slice(0, 8).map((item) => (
                    <button key={item.path} onClick={() => { void openSource(item.path); }} className="mb-1 block w-full truncate rounded-lg bg-black/20 px-3 py-2 text-left text-xs text-amber-200 hover:bg-white/5">{item.path}</button>
                  )) : <p className="text-xs text-emerald-300">Every analyzed file has an incoming import.</p>}
                </div>
                {result.code_intelligence.dependency_depth.deepest_files.length > 0 && (
                  <div className="mb-3"><div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Deepest dependency files</div>
                    {result.code_intelligence.dependency_depth.deepest_files.slice(0, 5).map((path) => (
                      <button key={path} onClick={() => { void openSource(path); }} className="mb-1 block w-full truncate rounded-lg bg-black/20 px-3 py-2 text-left text-xs text-indigo-200 hover:bg-white/5">{path}</button>
                    ))}
                  </div>
                )}
                <p className="text-[10px] leading-4 text-slate-600">{result.code_intelligence.code_intelligence_note}</p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/[0.025] p-5">
                <div className="mb-4 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-sm font-semibold"><Bug size={16} className="text-amber-300" /> Static bug scan</div>
                  <span className="rounded-full bg-white/5 px-2.5 py-1 text-xs text-slate-300">{result.bug_stats.total} findings</span>
                </div>
                <div className="mb-4 grid grid-cols-3 gap-2">
                  <Metric label="High" value={result.bug_stats.by_severity.high} />
                  <Metric label="Medium" value={result.bug_stats.by_severity.medium} />
                  <Metric label="Low" value={result.bug_stats.by_severity.low} />
                </div>
                {result.bug_findings.length ? (
                  <div className="max-h-80 space-y-2 overflow-auto">
                    {result.bug_findings.map((finding) => (
                      <div key={finding.id} className="rounded-xl border border-white/10 bg-black/20 p-3">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs font-semibold text-slate-200">{finding.title}</span>
                          <span className={`rounded-full px-2 py-0.5 text-[10px] uppercase ${finding.severity === "high" ? "bg-rose-400/10 text-rose-300" : finding.severity === "medium" ? "bg-amber-400/10 text-amber-300" : "bg-slate-400/10 text-slate-300"}`}>{finding.severity}</span>
                        </div>
                        <div className="mt-1 truncate text-[10px] text-slate-500">{finding.path}:{finding.line}</div>
                        <p className="mt-2 text-xs leading-5 text-slate-400">{finding.message}</p>
                        <p className="mt-2 text-[11px] leading-5 text-indigo-200">Fix: {finding.recommendation}</p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <button onClick={() => { void openSource(finding.path); }} className="rounded-lg border border-white/10 px-3 py-2 text-[11px] text-slate-300 hover:bg-white/5">Open file</button>
                          <button disabled={bugAiLoadingId !== null} onClick={() => { void explainBug(finding); }} className="rounded-lg bg-indigo-500/15 px-3 py-2 text-[11px] font-semibold text-indigo-200 hover:bg-indigo-500/25 disabled:opacity-50">
                            {bugAiLoadingId === finding.id ? "Analyzing…" : "Explain with AI"}
                          </button>
                        </div>
                        {bugAiFindingId === finding.id && bugAiLoadingId === finding.id && <p className="mt-2 text-[11px] text-indigo-300">{aiStatus}</p>}
                        {bugAiFindingId === finding.id && bugAiError && <p role="alert" className="mt-2 text-[11px] text-rose-300">{bugAiError}</p>}
                        {bugAiFindingId === finding.id && bugAiExplanation && <div className="mt-3 whitespace-pre-wrap rounded-lg border border-indigo-400/20 bg-indigo-400/5 p-3 text-xs leading-5 text-slate-300">{bugAiExplanation}</div>}
                      </div>
                    ))}
                  </div>
                ) : <p className="text-xs leading-5 text-slate-400">No supported risky patterns found in the scanned files.</p>}
                <p className="mt-3 text-[10px] leading-4 text-slate-600">{result.bug_analysis_note}</p>
              </div>
              <div className="rounded-2xl border border-cyan-400/20 bg-cyan-400/[0.035] p-4">
                <div className="mb-3 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-sm font-semibold"><Workflow size={15} className="text-cyan-300" /> Symbol intelligence</div>
                  <span className="text-[10px] text-slate-500">{result.symbol_intelligence.symbol_stats.symbols} symbols</span>
                </div>
                <div className="mb-3 grid grid-cols-3 gap-2">
                  <Metric label="Functions" value={result.symbol_intelligence.symbol_stats.functions} />
                  <Metric label="Classes" value={result.symbol_intelligence.symbol_stats.classes} />
                  <Metric label="Call links" value={result.symbol_intelligence.symbol_stats.resolved_call_links} />
                </div>
                <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Functions & classes</div>
                <div className="max-h-52 space-y-1 overflow-auto">
                  {result.symbol_intelligence.symbols.length ? result.symbol_intelligence.symbols.slice(0, 80).map((symbol) => (
                    <button key={symbol.id} onClick={() => { void openSource(symbol.path, symbol.line); }} className="flex w-full items-center justify-between gap-2 rounded-lg bg-black/20 px-3 py-2 text-left hover:bg-white/5">
                      <span className="min-w-0"><span className="block truncate text-[11px] text-cyan-200">{symbol.qualified_name}</span><span className="block truncate text-[9px] text-slate-500">{symbol.path}</span></span>
                      <span className="shrink-0 text-[9px] text-slate-500">{symbol.kind} · L{symbol.line}</span>
                    </button>
                  )) : <p className="text-xs text-slate-500">No supported symbols detected.</p>}
                  {result.symbol_intelligence.symbols.length > 80 && <p className="text-[9px] text-slate-600">Showing first 80 symbols.</p>}
                </div>
                <div className="mb-2 mt-4 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Class inheritance relationships</div>
                <div className="max-h-36 space-y-1 overflow-auto">
                  {result.symbol_intelligence.inheritance_edges.length ? result.symbol_intelligence.inheritance_edges.map((edge, index) => (
                    <button key={`${edge.path}:${edge.line}:${index}`} onClick={() => { void openSource(edge.path, edge.line); }} className="flex w-full items-center justify-between gap-2 rounded-lg bg-black/20 px-3 py-2 text-left text-[10px] hover:bg-white/5">
                      <span className="truncate text-cyan-200">{edge.child} <span className="text-slate-500">extends</span> {edge.parent}</span>
                      <span className="shrink-0 text-[9px] text-slate-500">{edge.resolved ? "local" : "external?"}</span>
                    </button>
                  )) : <p className="text-xs text-slate-500">No inheritance declarations detected.</p>}
                </div>
                <div className="mb-2 mt-4 flex items-center justify-between text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                  <span>Potentially unused functions</span><span>{result.symbol_intelligence.dead_function_candidates.length}</span>
                </div>
                <div className="max-h-36 space-y-1 overflow-auto">
                  {result.symbol_intelligence.dead_function_candidates.length ? result.symbol_intelligence.dead_function_candidates.slice(0, 30).map((item) => (
                    <button key={item.id} onClick={() => { void openSource(item.path, item.line); }} className="block w-full truncate rounded-lg bg-black/20 px-3 py-2 text-left text-[10px] text-amber-200 hover:bg-white/5">{item.qualified_name} <span className="text-slate-600">· {item.path}:{item.line}</span></button>
                  )) : <p className="text-xs text-slate-500">No candidates detected.</p>}
                </div>
                <div className="mb-2 mt-4 flex items-center justify-between text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                  <span>Duplicate function bodies</span><span>{result.symbol_intelligence.duplicate_function_groups.length} groups</span>
                </div>
                <div className="max-h-36 space-y-2 overflow-auto">
                  {result.symbol_intelligence.duplicate_function_groups.length ? result.symbol_intelligence.duplicate_function_groups.slice(0, 20).map((group, index) => (
                    <div key={index} className="rounded-lg bg-black/20 p-2">
                      {group.map((item) => <button key={`${item.path}:${item.line}`} onClick={() => { void openSource(item.path, item.line); }} className="block w-full truncate text-left text-[10px] text-amber-200 hover:text-white">{item.name} · {item.path}:{item.line}</button>)}
                    </div>
                  )) : <p className="text-xs text-slate-500">No exact normalized Python body duplicates detected.</p>}
                </div>
                <div className="mb-2 mt-4 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Resolved call links</div>
                <div className="max-h-40 space-y-1 overflow-auto">
                  {result.symbol_intelligence.call_edges.slice(0, 40).map((edge) => (
                    <button key={edge.id} onClick={() => { void openSource(edge.source_path, edge.line); }} className="block w-full truncate rounded-lg bg-black/20 px-3 py-2 text-left text-[10px] text-slate-300 hover:text-cyan-200">{edge.caller} → {edge.callee} <span className="text-slate-600">· {edge.source_path}:{edge.line}</span></button>
                  ))}
                  {!result.symbol_intelligence.call_edges.length && <p className="text-xs text-slate-500">No unambiguous local call links found.</p>}
                </div>
                <p className="mt-3 text-[9px] leading-4 text-slate-600">{result.symbol_intelligence.symbol_note}</p>
              </div>
              <div className="rounded-2xl border border-indigo-400/20 bg-indigo-400/[0.035] p-4">
                <div className="mb-3 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-sm font-semibold"><Search size={15} className="text-indigo-300" /> Code search</div>
                  <span className="text-[10px] text-slate-500">{codeSearchResults.length} matches</span>
                </div>
                <input value={codeSearchQuery} onChange={(event) => setCodeSearchQuery(event.target.value)} placeholder="Search code, function, class, import…" className="mb-2 h-9 w-full rounded-lg border border-white/10 bg-black/20 px-3 text-xs outline-none focus:border-indigo-400/40" />
                <div className="mb-2 grid grid-cols-2 gap-2">
                  <select value={codeSearchMode} onChange={(event) => setCodeSearchMode(event.target.value as typeof codeSearchMode)} className="h-8 min-w-0 rounded-lg border border-white/10 bg-slate-950 px-2 text-[10px] text-slate-300">
                    <option value="all">All code lines</option><option value="functions">Functions</option><option value="classes">Classes</option><option value="imports">Imports</option>
                  </select>
                  <select value={codeSearchLanguage} onChange={(event) => setCodeSearchLanguage(event.target.value)} className="h-8 min-w-0 rounded-lg border border-white/10 bg-slate-950 px-2 text-[10px] text-slate-300">
                    <option value="all">All languages</option>{codeSearchLanguages.map((language) => <option key={language} value={language}>{language}</option>)}
                  </select>
                </div>
                {Object.keys(localSources).length ? (
                  <div className="max-h-64 space-y-1 overflow-auto">
                    {!codeSearchQuery.trim() ? <p className="py-2 text-xs text-slate-500">Enter a search term to scan the selected folder.</p>
                      : codeSearchResults.length ? codeSearchResults.map((match) => (
                        <button key={`${match.path}:${match.line}`} onClick={() => { void openSource(match.path, match.line); }} className="block w-full rounded-lg bg-black/20 px-3 py-2 text-left hover:bg-white/5">
                          <span className="block truncate text-[10px] font-medium text-indigo-200">{match.path}:{match.line}</span>
                          <span className="mt-1 block truncate font-mono text-[10px] text-slate-400">{match.text}</span>
                          <span className="mt-1 block text-[9px] uppercase tracking-wider text-slate-600">{match.kind}</span>
                        </button>
                      )) : <p className="py-2 text-xs text-slate-500">No matching lines found.</p>}
                    {codeSearchResults.length === 150 && <p className="pt-1 text-[9px] text-slate-600">Showing first 150 matches.</p>}
                  </div>
                ) : <p className="text-[10px] leading-4 text-slate-500">Code-content search is available after selecting a local project folder. GitHub URL analysis currently supports file/path search.</p>}
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/[0.025] p-4">
                <div className="mb-3 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-sm font-semibold"><FolderOpen size={15} /> File explorer</div>
                  <span className="text-[10px] text-slate-500">{result.nodes.length} files</span>
                </div>
                <div className="relative mb-3">
                  <Search size={13} className="absolute left-3 top-3 text-slate-500" />
                  <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search files and folders..." className="h-9 w-full rounded-lg border border-white/10 bg-black/20 pl-9 pr-3 text-xs outline-none focus:border-indigo-400/40" />
                </div>
                <div className="max-h-[420px] overflow-auto">
                  {fileTree.length ? renderTree(fileTree) : <p className="p-3 text-xs text-slate-500">No files to display.</p>}
                </div>
              </div>
              {selectedNode && <div className="rounded-2xl border border-indigo-400/20 bg-indigo-400/5 p-4"><div className="mb-2 flex items-center gap-2 text-sm font-semibold"><FileCode2 size={15} /> Selected file</div><div className="break-all text-xs text-indigo-200">{selectedNode.path}</div><div className="mt-2 text-xs text-slate-400">{selectedNode.language} · {selectedNode.lines} lines</div><div className="mt-3 flex gap-2">
                  <button onClick={() => void openSource(selectedNode.path)} className="rounded-lg border border-white/10 px-3 py-2 text-xs text-slate-300 hover:bg-white/5">Open source</button>
                  <button disabled={!source || aiLoading} onClick={() => void explainSource()} className="rounded-lg bg-indigo-500 px-3 py-2 text-xs font-semibold text-white disabled:opacity-40">{aiLoading ? "Thinking..." : "Explain with Ollama"}</button>
                </div>
                {sourceLoading && <p className="mt-3 text-xs text-slate-400">Loading source…</p>}
                {source && <div className="mt-3 overflow-hidden rounded-lg border border-white/10">
                  <div className="border-b border-white/10 px-3 py-2 text-[10px] text-slate-500">{source.path}{source.truncated ? " · preview truncated" : ""}</div>
                  <pre className="max-h-72 overflow-auto p-3 text-[11px] leading-5 text-slate-300"><code>{source.content.split("\n").map((line, index) => (
                    <span id={`source-line-${index + 1}`} key={index} className={sourceLine === index + 1 ? "block rounded bg-amber-400/15 text-amber-100" : "block"}>
                      <span className="mr-4 inline-block w-8 select-none text-right text-slate-600">{index + 1}</span>{line || " "}
                    </span>
                  ))}</code></pre>
                </div>}
                {aiLoading && <p className="mt-3 text-xs text-indigo-300">{aiStatus || "Preparing local AI…"}</p>}
                {!aiLoading && aiStatus && <p className="mt-3 text-xs text-emerald-300">{aiStatus}</p>}
                {aiError && <p role="alert" className="mt-3 text-xs text-rose-300">{aiError}</p>}
                {explanation && <div className="mt-3 whitespace-pre-wrap rounded-lg border border-indigo-400/20 bg-indigo-400/5 p-3 text-xs leading-6 text-slate-300">{explanation}</div>}
              </div>}
              <p className="text-[11px] leading-5 text-slate-600">{result.analysis_note}</p>
            </aside>
          </div>
        ) : (
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            <Feature icon={<Network size={19} />} title="Architecture graph" text="Explore how modules connect through imports." />
            <Feature icon={<Bug size={19} />} title="Static insights" text="Build a foundation for finding risky code patterns." />
            <Feature icon={<Sparkles size={19} />} title="Local AI" text="Keep explanations private with Ollama running on your machine." />
          </div>
        )}
      </section>
      <footer className="mx-auto max-w-[1500px] border-t border-white/10 py-5 text-center text-xs text-slate-600">CodeMap · Your code stays yours · Early development</footer>
    </main>
  );
}

export default function Home() {
  return <ReactFlowProvider><Explorer /></ReactFlowProvider>;
}
