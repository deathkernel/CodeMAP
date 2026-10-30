"use client";

import { useEffect, useMemo, useState } from "react";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  ReactFlowProvider,
  type Edge,
  type Node,
} from "reactflow";
import "reactflow/dist/style.css";
import {
  ArrowRight, Boxes, Bug, FileCode2, Github, LoaderCircle,
  Network, Search, ShieldCheck, Sparkles, Workflow,
} from "lucide-react";

type AnalysisResult = {
  repository: string;
  default_branch: string;
  nodes: Array<{ id: string; label: string; path: string; language: string; lines: number }>;
  edges: Array<{ id: string; source: string; target: string; label: string }>;
  stats: {
    files_analyzed: number;
    dependencies_found: number;
    relative_imports_unresolved: number;
    files_not_fetched: number;
  };
  analysis_note: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function toMermaid(result: AnalysisResult) {
  const lines = ["flowchart LR"];
  result.nodes.forEach((node, index) => {
    lines.push(`  F${index}["${node.path.replaceAll('"', "'")}"]`);
  });
  const ids = new Map(result.nodes.map((node, index) => [node.id, `F${index}`]));
  result.edges.forEach((edge) => {
    const from = ids.get(edge.source);
    const to = ids.get(edge.target);
    if (from && to) lines.push(`  ${from} --> ${to}`);
  });
  return lines.join("\n");
}

function Explorer() {
  const [url, setUrl] = useState("");
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [source, setSource] = useState<{ path: string; content: string; truncated: boolean } | null>(null);
  const [sourceLoading, setSourceLoading] = useState(false);
  const [explanation, setExplanation] = useState("");
  const [aiLoading, setAiLoading] = useState(false);\n  const [aiStatus, setAiStatus] = useState("");
  const [aiError, setAiError] = useState("");
  const [ollamaState, setOllamaState] = useState<"checking" | "ready" | "missing" | "offline">("checking");

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

  const visibleNodes = useMemo(
    () => result?.nodes.filter((node) => node.path.toLowerCase().includes(query.toLowerCase())) ?? [],
    [result, query],
  );
  const graphNodes: Node[] = useMemo(() => {
    if (!result) return [];
    const nodes = result.nodes.map((node, index) => ({
      id: node.id,
      position: { x: (index % 4) * 260, y: Math.floor(index / 4) * 150 },
      data: { label: (
        <div className="min-w-40 rounded-xl border border-indigo-400/30 bg-[#111a2b] px-4 py-3 shadow-xl">
          <div className="flex items-center gap-2 text-indigo-300"><FileCode2 size={15} /><span className="text-xs uppercase">{node.language}</span></div>
          <div className="mt-2 max-w-48 truncate text-sm font-semibold text-slate-100">{node.label}</div>
          <div className="mt-1 max-w-48 truncate text-[10px] text-slate-400">{node.path}</div>
          <div className="mt-2 text-[10px] text-slate-500">{node.lines} lines</div>
        </div>
      ) },
      style: { width: 205, border: "none", background: "transparent", padding: 0 },
    }));
    return nodes;
  }, [result]);
  const graphEdges: Edge[] = useMemo(
    () => result?.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: "imports",
      animated: true,
      style: { stroke: "#818cf8", strokeWidth: 1.5 },
      labelStyle: { fill: "#a5b4fc", fontSize: 10 },
    })) ?? [],
    [result],
  );

  async function openSource(path: string) {
    if (!url || !result) return;
    setSelected(path);
    setSourceLoading(true);
    setSource(null);
    setExplanation("");
    setAiError("");
    try {
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

  async function analyze(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const response = await fetch(`${API_BASE}/api/repository/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Analysis failed. Check the API server.");
      setResult(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not connect to CodeMap API.");
    } finally {
      setLoading(false);
    }
  }

  function exportMermaid() {
    if (!result) return;
    const blob = new Blob([toMermaid(result)], { type: "text/plain;charset=utf-8" });
    const href = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = href;
    anchor.download = "codemap-architecture.mmd";
    anchor.click();
    URL.revokeObjectURL(href);
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

        <form onSubmit={analyze} className="flex flex-col gap-3 rounded-2xl border border-white/10 bg-white/[0.035] p-3 md:flex-row">
          <div className="flex flex-1 items-center gap-3 rounded-xl border border-white/10 bg-[#080d17] px-4">
            <Github size={18} className="text-slate-500" />
            <input value={url} onChange={(event) => setUrl(event.target.value)} required type="url" placeholder="https://github.com/owner/repository" className="h-12 w-full bg-transparent text-sm outline-none placeholder:text-slate-600" />
          </div>
          <button disabled={loading} className="flex items-center justify-center gap-2 rounded-xl bg-indigo-500 px-6 py-3 text-sm font-semibold text-white transition hover:bg-indigo-400 disabled:opacity-60">
            {loading ? <LoaderCircle className="animate-spin" size={17} /> : <ArrowRight size={17} />} {loading ? "Mapping..." : "Generate map"}
          </button>
        </form>
        {error && <p role="alert" className="mt-3 rounded-xl border border-rose-400/20 bg-rose-400/5 p-3 text-sm text-rose-300">{error}</p>}

        {result ? (
          <div className="mt-6 grid gap-4 lg:grid-cols-[minmax(0,1fr)_290px]">
            <section className="overflow-hidden rounded-2xl border border-white/10 bg-[#0b1220]">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-5 py-4">
                <div><div className="font-semibold">{result.repository}</div><div className="mt-1 text-xs text-slate-500">Branch: {result.default_branch}</div></div>
                <button onClick={exportMermaid} className="rounded-lg border border-white/10 px-3 py-2 text-xs text-slate-300 hover:bg-white/5">Export Mermaid</button>
              </div>
              <div className="h-[620px]">
                <ReactFlow nodes={graphNodes} edges={graphEdges} fitView onNodeClick={(_, node) => { void openSource(node.id); }} minZoom={0.15}>
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
                      <button key={finding.id} onClick={() => { void openSource(finding.path); }} className="block w-full rounded-xl border border-white/10 bg-black/20 p-3 text-left transition hover:border-indigo-400/30">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs font-semibold text-slate-200">{finding.title}</span>
                          <span className={`rounded-full px-2 py-0.5 text-[10px] uppercase ${finding.severity === "high" ? "bg-rose-400/10 text-rose-300" : finding.severity === "medium" ? "bg-amber-400/10 text-amber-300" : "bg-slate-400/10 text-slate-300"}`}>{finding.severity}</span>
                        </div>
                        <div className="mt-1 truncate text-[10px] text-slate-500">{finding.path}:{finding.line}</div>
                        <p className="mt-2 text-xs leading-5 text-slate-400">{finding.message}</p>
                        <p className="mt-2 text-[11px] leading-5 text-indigo-200">Fix: {finding.recommendation}</p>
                      </button>
                    ))}
                  </div>
                ) : <p className="text-xs leading-5 text-slate-400">No supported risky patterns found in the scanned files.</p>}
                <p className="mt-3 text-[10px] leading-4 text-slate-600">{result.bug_analysis_note}</p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/[0.025] p-4">
                <div className="mb-3 flex items-center gap-2 text-sm font-semibold"><Search size={15} /> File explorer</div>
                <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter files..." className="mb-3 h-9 w-full rounded-lg border border-white/10 bg-black/20 px-3 text-xs outline-none" />
                <div className="max-h-64 space-y-1 overflow-auto">
                  {visibleNodes.map((node) => <button key={node.id} onClick={() => { void openSource(node.id); }} className={`block w-full truncate rounded-lg px-3 py-2 text-left text-xs ${selected === node.id ? "bg-indigo-500/20 text-indigo-200" : "text-slate-400 hover:bg-white/5"}`}>{node.path}</button>)}
                </div>
              </div>
              {selectedNode && <div className="rounded-2xl border border-indigo-400/20 bg-indigo-400/5 p-4"><div className="mb-2 flex items-center gap-2 text-sm font-semibold"><FileCode2 size={15} /> Selected file</div><div className="break-all text-xs text-indigo-200">{selectedNode.path}</div><div className="mt-2 text-xs text-slate-400">{selectedNode.language} · {selectedNode.lines} lines</div><div className="mt-3 flex gap-2">
                  <button onClick={() => void openSource(selectedNode.path)} className="rounded-lg border border-white/10 px-3 py-2 text-xs text-slate-300 hover:bg-white/5">Open source</button>
                  <button disabled={!source || aiLoading} onClick={() => void explainSource()} className="rounded-lg bg-indigo-500 px-3 py-2 text-xs font-semibold text-white disabled:opacity-40">{aiLoading ? "Thinking..." : "Explain with Ollama"}</button>
                </div>
                {sourceLoading && <p className="mt-3 text-xs text-slate-400">Loading source…</p>}
                {source && <div className="mt-3 overflow-hidden rounded-lg border border-white/10">
                  <div className="border-b border-white/10 px-3 py-2 text-[10px] text-slate-500">{source.path}{source.truncated ? " · preview truncated" : ""}</div>
                  <pre className="max-h-72 overflow-auto p-3 text-[11px] leading-5 text-slate-300"><code>{source.content}</code></pre>
                </div>}
                {aiLoading && <p className="mt-3 text-xs text-indigo-300">{aiStatus || "Preparing local AI…"}</p>}\n                {!aiLoading && aiStatus && <p className="mt-3 text-xs text-emerald-300">{aiStatus}</p>}
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

function Metric({ label, value }: { label: string; value: number }) {
  return <div className="rounded-xl bg-black/20 p-3"><div className="text-2xl font-semibold tabular-nums">{value}</div><div className="mt-1 text-[10px] uppercase tracking-wider text-slate-500">{label}</div></div>;
}

function Feature({ icon, title, text }: { icon: React.ReactNode; title: string; text: string }) {
  return <article className="rounded-2xl border border-white/10 bg-white/[0.025] p-5"><div className="mb-4 inline-flex rounded-xl bg-indigo-500/10 p-2.5 text-indigo-300">{icon}</div><h2 className="font-medium">{title}</h2><p className="mt-2 text-sm leading-6 text-slate-400">{text}</p></article>;
}

export default function Home() {
  return <ReactFlowProvider><Explorer /></ReactFlowProvider>;
}
