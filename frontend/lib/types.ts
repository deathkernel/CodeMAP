/** Shape of the JSON returned by CodeMap's analysis endpoints. */

export type AnalysisResult = {
  project_id: string;
  indexed_chunks: number;
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
  bug_findings: Array<{ id: string; path: string; line: number; rule_id: string; title: string; severity: "high" | "medium" | "low"; message: string; recommendation: string }>;
  bug_stats: { total: number; by_severity: { high: number; medium: number; low: number }; files_scanned: number; truncated: boolean };
  bug_analysis_note: string;
  code_intelligence: {
    bottleneck_files: Array<{ path: string; fan_in: number; fan_out: number; connections: number }>;
    unreferenced_files: Array<{ path: string; reason: string }>;
    dependency_depth: { max_depth: number; reachable_files: number; unreachable_files: number; deepest_files: string[] };
    code_intelligence_note: string;
  };
  symbol_intelligence: {
    symbols: Array<{ id: string; path: string; name: string; qualified_name: string; kind: "function" | "class"; line: number; end_line: number }>;
    call_edges: Array<{ id: string; source_path: string; target_path: string; caller: string; callee: string; line: number; target_line: number }>;
    inheritance_edges: Array<{ path: string; child: string; parent: string; line: number; resolved: boolean }>;
    dead_function_candidates: Array<{ id: string; path: string; name: string; qualified_name: string; line: number }>;
    duplicate_function_groups: Array<Array<{ path: string; name: string; line: number }>>;
    symbol_stats: { symbols: number; functions: number; classes: number; resolved_call_links: number; inheritance_links: number; dead_function_candidates: number; duplicate_function_groups: number };
    symbol_note: string;
  };
  advanced_architecture: {
    frameworks: string[];
    entry_points: Array<{ path: string; framework: string; reason: string }>;
    api_endpoints: Array<{ path: string; line: number; method: string; route: string; framework: string }>;
    database_relations: Array<{ path: string; line: number; source_model: string; target: string; kind: string }>;
    module_dependencies: Array<{ source: string; target: string; imports: number }>;
    stats: { frameworks_detected: number; entry_points: number; api_endpoints: number; database_relations: number; cross_module_links: number };
    note: string;
  };
  architecture_insights: {
    entry_points: Array<{ path: string; reason: string }>;
    circular_dependencies: string[][];
    module_groups: Array<{ name: string; files: number }>;
    architecture_stats: { entry_points: number; circular_dependency_groups: number; top_level_modules: number };
    architecture_note: string;
  };
  architecture_health: {
    health_score: number;
    health_grade: "healthy" | "watch" | "needs_attention";
    risk_factors: string[];
    module_health: Array<{
      name: string; files: number; lines: number; dependencies: number;
      internal_dependencies: number; external_dependencies: number; circular_files: number;
      bug_counts: { high: number; medium: number; low: number };
      complexity_score: number; risk_score: number; risk_level: "high" | "medium" | "low";
    }>;
    health_stats: { modules: number; high_risk_modules: number; medium_risk_modules: number; circular_files: number; bug_findings: number };
    health_note: string;
  };
};
