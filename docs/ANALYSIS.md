# CodeMap: deep codebase analysis

This is a review of the CodeMap repository as uploaded. It covers architecture, code quality, security, performance, testing, documentation, and developer experience. Every finding points to a file, and every claim was checked against the code. The review also records what was changed in this pass and what could not be verified.

- [1. Executive summary](#1-executive-summary)
- [2. Scorecard](#2-scorecard)
- [3. Metrics](#3-metrics)
- [4. Architecture review](#4-architecture-review)
- [5. Backend findings](#5-backend-findings)
- [6. Frontend findings](#6-frontend-findings)
- [7. Documentation audit and changes made](#7-documentation-audit-and-changes-made)
- [8. Prioritized roadmap](#8-prioritized-roadmap)
- [9. Verification performed](#9-verification-performed)

---

## 1. Executive summary

CodeMap is an ambitious and unusually well-scoped project. It combines static analysis, a dependency graph, architecture scoring, retrieval-augmented Q&A, and report generation, and it runs entirely on the user's machine. Its most valuable design choice is the **"parse, never execute"** rule. The ingestion code enforces that rule rigorously, which is uncommon for a project at this stage.

The main weaknesses are not in the algorithms. They are in **structure and consistency**:

1. **The frontend is one 1,556-line file**, and its central component holds 38 state hooks.
2. **Route handlers contain business logic.** The 295-line analysis route is really a pipeline orchestrator.
3. **Some heavy work runs inside `async` handlers**, so it blocks the server while an analysis runs.
4. **Constants and database setup are duplicated** across modules, and the copies have already drifted.
5. **The documentation contradicted the code** in several places (retrieval type, test location, Tree-sitter, version numbers, and a broken PowerShell command).

Most of these are cheap to fix. The first two groups of changes are included in this pass, and the rest are sequenced in [§8](#8-prioritized-roadmap).

**Overall:** a strong beta. The foundation is sound, the security posture for a local tool is good, and the remaining work is mostly refactoring and hardening.

---

## 2. Scorecard

Scores are out of 10, judged as a local-first developer tool at beta maturity. The "after" column reflects the changes made in this pass.

| Dimension | Score | After | Rationale |
|---|:-:|:-:|---|
| **Feature scope** | 9 | 9 | Very broad coverage: graph, architecture, symbols, findings, RAG, reports, and large-repo support. |
| **Security (ingestion)** | 8 | 8 | ZIP validation covers traversal, symlinks, encryption, duplicates, and limits. Repositories are never executed. |
| **Security (service)** | 5 | 5 | No authentication, and the event loop blocks during analysis. Acceptable locally, weak if exposed. |
| **Backend layering** | 6 | 6 | Routes are thin in most files, but `analysis.py` holds the whole pipeline. Services are large (`analyzer.py` 860 lines). |
| **Performance and scale** | 6 | 6 | Incremental caches and bounded batches are good. Synchronous work in async handlers, N+1 source previews, and in-Python vector scans cap the gains. |
| **Testing** | 5 | 5 | 46 test functions in CI, covering ingestion, analyzer, bug detector, AI, and index. No frontend tests and no lint gate. |
| **Frontend structure** | 3 | **5** | A 1,556-line file is now 1,341 lines, with pure logic moved into `lib/` and UI into `components/`. The 1,313-line `Explorer` is still a monolith. |
| **Documentation** | 5 | **8** | README, architecture, API, security, and this analysis are now structured and consistent with the code. Several contradictions are corrected. |
| **Consistency** | 4 | **6** | Versions aligned, duplicated constants identified, and doc drift fixed. Code-level duplication is still in place (see §5). |
| **Developer experience** | 6 | 7 | Clear setup docs and a CI pipeline. `npm run lint` has no config, and there are no lock files. |
| **Observability** | 2 | 2 | Zero `logging` calls in the backend. Broad `except` blocks hide failures with no trace. |

**Biggest score gains available:** observability (2 to 7 with structured logging), frontend structure (5 to 8 after splitting `Explorer`), and backend layering (6 to 8 after moving the pipeline out of routes).

---

## 3. Metrics

| Area | Measure | Value |
|---|---|---|
| Backend | Python lines (app + tests) | ~3,970 |
| Backend | Largest modules | `analyzer.py` 860 · `code_index.py` 705 · `bug_detector.py` 522 · `reports.py` 353 · `ai.py` 297 · `analysis.py` 295 |
| Backend | HTTP endpoints | 18 |
| Backend | Test functions | 46 across 6 files |
| Backend | Distinct static rule IDs | ~28 |
| Backend | Broad `except Exception` handlers | 4 |
| Backend | Logging calls | 0 |
| Backend | Response models declared (`response_model`) | 0 |
| Frontend | `page.tsx` (before → after) | 1,556 → 1,341 lines |
| Frontend | `Explorer` component | 1,313 lines, 38 `useState` hooks |
| Frontend | Explicit `any` in page | 2 |
| Frontend | Test files | 0 |
| Dependencies | Backend runtime (declared) | 7 packages, including `pytest` and `reportlab` |
| Dependencies | Frontend runtime | 5 packages |
| Repo hygiene | Lock files | None (backend or frontend) |

---

## 4. Architecture review

### 4.1 What is working well

- **Clear separation of concerns in most places.** `services/` contains pure functions with no HTTP awareness, and `routes/` is mostly validation and mapping.
- **Stable identities enable incremental work.** `make_stable_project_id(repository, branch)` means cache rows survive re-analysis.
- **Caching is layered and explicit.** File-level caches exist for graph imports, bug findings, and chunks. Each is keyed by content hash.
- **Graceful degradation.** Semantic retrieval falls back to keyword search, and the response says which mode ran. This is a good pattern that is clearly documented.
- **Safe ingestion is a first-class concern.** Ingestion is the most carefully written code in the project.

### 4.2 Coupling and layering problems

**A. Orchestration lives in a route.** `analyze_github` in `routes/analysis.py` runs eight stages in order: fetch, filter, index, schedule embeddings, graph, findings, symbols, and assemble the response. The three analysis routes repeat most of this sequence. The route should delegate to one `services/pipeline.py` function that all three call. The route then only handles source acquisition and HTTP concerns.

**B. Database setup is duplicated.** `code_index._connect()` sets WAL and busy-timeout options. `routes/reports.py` opens its own `sqlite3.connect(...)` with no WAL setting, and it creates the `code_report_snapshots` table **twice** (lines 300 and 323). Any future schema change has to be made in several places. Reports should use one shared connection helper and one schema definition.

**C. Analysis results are untyped.** Every service returns `dict[str, Any]`, and no route declares a `response_model`. The OpenAPI documentation therefore shows no response shapes, and the frontend's `AnalysisResult` type is written by hand and can silently drift from the backend. Pydantic response models would make the contract explicit, and they could generate the TypeScript type.

**D. `analyzer.py` does too much.** At 860 lines it covers import parsing, graph construction, caching, architecture insights, code intelligence, health scoring, symbol analysis, and framework detection. Splitting it into `graph.py`, `architecture.py`, `health.py`, and `symbols.py` would make each piece testable on its own.

### 4.3 Data flow

The most important data path is the GitHub analysis, described in [ARCHITECTURE.md §4](ARCHITECTURE.md#4-analysis-pipeline). Its key weakness is ordering. The embedding job is scheduled before the graph is built, which is fine, but the synchronous graph and findings work blocks the event loop while that happens (see §5.1).

---

## 5. Backend findings

Each finding has an ID so it can be tracked. Security findings are also listed in [SECURITY.md §4](SECURITY.md#4-findings).

### 5.1 Blocking the event loop (`SEC-01`, Medium)

`analyze_github`, `analyze_local_folder`, `analyze_zip_upload`, and `clear_project_index` are declared `async def`. Inside them, SQLite calls and CPU-heavy functions (`analyze_sources_incremental`, `scan_for_bugs_incremental`, `symbol_intelligence`) run synchronously. While one analysis runs, the whole server stops responding, including the job-status polling that the frontend depends on.

**Fix:** wrap the synchronous pipeline in `await asyncio.to_thread(...)`, or declare the functions with plain `def`, which FastAPI runs in a threadpool. Keep the GitHub blob fetching async.

### 5.2 No authentication (`SEC-02`, Medium)

This is acceptable for a localhost tool, and the default binding protects it. It becomes a real risk the moment the port is reachable. The indexed source can be queried through `/ask-codebase`.

**Fix:** keep the documentation strong about localhost-only use, and add an optional bearer-token dependency for any future remote deployment.

### 5.3 Duplicated constants have drifted

`repository_scanner.py` and `zip_scanner.py` each define `SOURCE_SUFFIXES` and `SKIP_PARTS`. They are not identical. The ZIP scanner skips `.idea` and `.vscode`, but the GitHub scanner does not. That means the same repository can produce different inventories depending on how it was imported.

**Fix:** move both sets into one `services/constants.py`, and add a test that asserts both scanners use the same values.

### 5.4 Per-request re-inventory in the source preview (N+1)

`POST /api/repository/source` calls `scan_github_repository`, which makes two GitHub API calls (metadata and tree) every time a file preview is requested. It then makes a third call for the blob. Each click costs three requests. Unauthenticated GitHub allows only 60 requests per hour, so a short session of file browsing can exhaust the quota and return `502`.

**Fix:** cache the inventory per `(owner, repo, branch)` for a few minutes, or let the client pass the `sha` of a file it already received from the inventory and validate it against the cached tree.

### 5.5 Semantic search scans every vector in Python

`search_project_sources_hybrid` loads every embedding for a project and computes cosine similarity in a Python loop on each question. That is O(chunks × dimensions) work per query, in pure Python. It is fine for a few thousand chunks and becomes slow for large repositories.

**Fix:** use `numpy` for a single matrix product, or keep vectors in a dedicated index such as `sqlite-vec` once the project needs it. Caching the matrix in memory per project would also help.

### 5.6 ZIP limits trust declared sizes (`SEC-03`, Low)

The total-size and per-file checks use `info.file_size`, which comes from the archive directory. Python's `zipfile` stops reading at that declared size, so the practical risk is small. The defense is still thinner than it looks, because `read_zip_sources` calls `archive.read(info)`, which allocates the full entry before the post-read check runs.

**Fix:** read entries through `archive.open(info)` in fixed-size chunks and stop as soon as the configured cap is reached.

### 5.7 Silent failures and no logging (`observability`)

The backend has **no logging at all**. Four `except Exception` blocks convert errors to generic responses. `repository.py` turns every failure into `502 "GitHub could not be reached or returned an invalid response."`, which is true for network errors but also hides programming bugs. `fetch_blob` returns `None` silently for failed blobs, so a file that failed to download is simply missing from the result.

**Fix:** add `logging.getLogger(__name__)` to each module. Log every swallowed exception with its context, and report the count of skipped files in the response (the `files_not_fetched` stat already exists, so the logic is partly in place).

### 5.8 Dependency declarations

- **`python-dotenv` was used but not declared.** `main.py` imports `dotenv`, which was available only because `pydantic-settings` depends on it. It is now declared explicitly.
- **`pytest` was in the runtime requirements.** It now lives in `requirements-dev.txt`, which includes the runtime set.
- **No lock files.** Ranges such as `fastapi>=0.115,<1.0` are reasonable, but reproducible CI and releases need a lock.

### 5.9 Minor code-level issues

- `routes/analysis.py` imports `re` inside a function. Move it to the top of the module.
- `routes/ai.py` mixes third-party and first-party imports, and it contains a `legacy_model` string comparison that should be documented or removed.
- Project-ID validation differs by endpoint (`[a-f0-9]{24}` for delete, length only for Q&A). Use one shared validator.
- `code_index.py` builds SQL with f-strings for table names. The values are constants today, so this is safe, but it is worth a comment so that nobody passes user input into it later.

---

## 6. Frontend findings

### 6.1 The monolithic page

`app/page.tsx` held every type, helper, layout function, and view in one file. Its `Explorer` component is still about 1,300 lines and uses 38 state hooks. Several panels (the graph, file tree, health, architecture, Q&A, and reports) share state through closures, so none of them can be tested or reused in isolation.

**Done in this pass:** the types, configuration, graph layout, Mermaid export, tree logic, file icons, and presentational components were moved out of `page.tsx` into `lib/` and `components/`. The pure helpers were smoke-tested in Node. The file dropped from 1,556 to 1,341 lines, and the new modules are independently importable.

**Next:** move each panel into its own component under `components/explorer/`, and move the shared state into a `useExplorerState` hook or a small reducer. Each panel can then receive only the props it needs.

### 6.2 Graph scale

`getGraphPositions` lays out every file on a grid with fixed spacing (360 px per rank, 170 px per row). For a repository with several hundred nodes, the canvas becomes very large, and React Flow renders every node even when most are off-screen.

**Fix:** enable React Flow's `onlyRenderVisibleElements` prop. It is currently not set. Also consider a folder-collapsed default for large graphs, since the page already supports filtering by folder.

### 6.3 Library currency

The project uses `reactflow` (v11). Its maintainers now publish the library as `@xyflow/react`. The v11 package still works, but new features and fixes land on the new package, so migrating is a maintenance task worth scheduling.

### 6.4 Lint and tooling

`package.json` defines `"lint": "eslint ."`, and `eslint` 9 is a dependency, but there is **no ESLint configuration file**. Running `npm run lint` will prompt for setup or fail. CI runs only the build, which does type-check, so there is no lint gate in CI.

**Fix:** add an `eslint.config.mjs` that extends `next/core-web-vitals`, and add a lint step to CI.

### 6.5 Typing and styling

- Two `any` escapes remain in `page.tsx`, in the report-comparison code. Give that response a type.
- Colors and surfaces are repeated as inline Tailwind arbitrary values (for example `bg-white/[0.025]` and `border-white/10`). Move them into Tailwind theme tokens so the visual system can change in one place. The existing `tailwind.config.ts` already declares `canvas`, `panel`, and `accent`, but most components don't use them.
- The app is dark-only (`color-scheme: dark`). That is a valid choice, but it should be a documented decision.
- **Low-contrast disclaimers.** The analysis notes that explain the limits of the results (for example, `bug_analysis_note` and `health_note`) are rendered at `10px` in `text-slate-600` on a near-black background. That is hard to read, and these notes carry the most important caveats in the product. Raise them to at least `text-slate-400` and `12px`, and give them a visible label.

### 6.6 Tests

There are no frontend tests. The helpers now in `lib/` are pure and easy to cover with Vitest. A few component tests with React Testing Library would protect the most fragile areas: the tree search, the graph filters, and the Q&A state.

---

## 7. Documentation audit and changes made

The documentation was accurate in its feature descriptions, but it contradicted itself and the code in several places. Each item below was checked against the source.

| # | Problem found | Where | Resolution |
|---|---|---|---|
| D1 | Said retrieval is "keyword retrieval, not semantic vector embeddings", but the README and code implement hybrid semantic retrieval. | `docs/development.md`, `docs/ollama-setup.md` | Rewritten to describe keyword retrieval as always-on and embeddings as optional. |
| D2 | README said "Testing and validation are intentionally pending", while CI runs the test suite on every push. | `README.md` | Replaced with an accurate status: backend tests in CI, no frontend tests. |
| D3 | Listed Tree-sitter as the parser. Nothing imports or uses it. Parsing uses Python `ast` and regular expressions. | `README.md` | Removed from the stack. The real parsers are documented in ARCHITECTURE. |
| D4 | Repository layout showed `tests/` at the root. The tests live in `backend/tests/`. | `README.md` | Corrected. |
| D5 | PowerShell commands contained doubled backslashes (`.\\.venv\\Scripts\\Activate.ps1`), which fail. | `docs/development.md` | Rewritten with correct paths. |
| D6 | Backend version `0.4.0` and frontend version `0.2.0` disagreed. | `main.py`, `package.json` | Aligned frontend to `0.4.0`. |
| D7 | The README linked a `LICENSE` file that does not exist in the upload. | `README.md` | Documented as MIT. The `LICENSE` file itself still needs to be added with the copyright holder's name. |
| D8 | `models/` was described as holding "API/domain schemas" but is empty. | `README.md` | Described as reserved, with schemas currently living in route modules. |
| D9 | `tailwind.config.ts` scanned a `components/` directory that did not exist. | `tailwind.config.ts` | The directory now exists and holds shared UI components. |

**New documentation:** `docs/ARCHITECTURE.md` (layers, pipeline, storage, and design decisions), `docs/API.md` (every endpoint with request and response shapes), `docs/SECURITY.md` (trust boundaries, controls, and findings), and this analysis.

**Also corrected:** `docs/ollama-setup.md` keeps its setup steps, and its retrieval section now matches the implementation. `.env.example` now separates backend and frontend settings, and it explains where the frontend variable belongs.

**Code changes made in this pass:**

- `backend/requirements.txt` now declares `python-dotenv` and no longer includes `pytest`. New `backend/requirements-dev.txt` adds `pytest`, and CI installs it.
- `frontend/app/page.tsx` reduced from 1,556 to 1,341 lines. Imports now come from the new modules.
- New `frontend/lib/`: `types.ts`, `config.ts`, `graph.ts`, `file-tree.ts`, and `file-icons.ts`.
- New `frontend/components/ui.tsx`: `Metric` and `Feature`, previously private to `page.tsx`.
- `frontend/package.json` version aligned to `0.4.0`.
- `.env.example` split into backend and frontend sections. The frontend variable was previously placed where Next.js never reads it.
- `docs/development.md` rewritten: PowerShell paths fixed, Linux and macOS commands added, troubleshooting based on real UI messages.

No backend logic was changed. Changing analysis code without running the test suite would be a risk, and the fixes for §5 should go in with tests.

---

## 8. Prioritized roadmap

Effort is an estimate for one experienced developer.

### P0: do first (small, high-value, low-risk)

| # | Task | Refs | Effort |
|---|---|---|---|
| 1 | Run `pytest` and `npm run build` locally to confirm this pass (see §9). | §9 | 15 min |
| 2 | Wrap the synchronous analysis work in `asyncio.to_thread` (or use `def`). | SEC-01, §5.1 | 1 h |
| 3 | ~~Declare `python-dotenv` explicitly. Split `pytest` into `requirements-dev.txt`.~~ **Done in this pass.** | §5.8 | 15 min |
| 4 | Add `eslint.config.mjs` and a lint step in CI. | §6.4 | 30 min |
| 5 | Add the `LICENSE` file with the correct copyright holder. | D7 | 5 min |
| 6 | Commit `package-lock.json`. Pin backend versions with a lock file. | SEC-07 | 30 min |

### P1: next (structure and reliability)

| # | Task | Refs | Effort |
|---|---|---|---|
| 7 | Add logging to every module, and log each swallowed exception. | §5.7 | 2 h |
| 8 | Move the analysis pipeline from `routes/analysis.py` into `services/pipeline.py`. | §4.2 A | 3 h |
| 9 | Create one SQLite connection helper and one schema module. Remove the duplicate `CREATE TABLE` in reports. | §4.2 B | 2 h |
| 10 | Consolidate `SOURCE_SUFFIXES` and `SKIP_PARTS` into one constants module, with a test. | §5.3 | 30 min |
| 11 | Cache the GitHub inventory per repository for a short time. | §5.4 | 2 h |
| 12 | Add Pydantic `response_model`s for the main endpoints, and generate the TypeScript types from them. | §4.2 C | 1 day |
| 13 | Stream-bounded ZIP entry reads. | SEC-03, §5.6 | 2 h |
| 14 | Unify project-ID validation. | SEC-04 | 30 min |

### P2: later (scale and polish)

| # | Task | Refs | Effort |
|---|---|---|---|
| 15 | Split `Explorer` into panel components, with a shared state hook. | §6.1 | 2 to 3 days |
| 16 | Set `onlyRenderVisibleElements` on the graph and add a collapsed-folder default for large repositories. | §6.2 | 2 h |
| 17 | Add Vitest tests for `lib/`, and component tests for the fragile panels. | §6.6 | 1 to 2 days |
| 18 | Move from `reactflow` to `@xyflow/react`. | §6.3 | 1 day |
| 19 | Use `numpy` or a vector index for semantic search. | §5.5 | 1 day |
| 20 | Add optional bearer-token auth for non-local deployments. | SEC-02 | 1 day |
| 21 | Move colors and surfaces into Tailwind theme tokens. Decide on light and dark modes. | §6.5 | 1 day |

---

## 9. Verification performed

This pass was done in a sandbox without network access, so the full toolchain could not be installed. Here is exactly what was and was not checked.

| Check | Result |
|---|---|
| Python syntax compile, all backend modules | **Passed.** |
| Backend test suite (`pytest`) | **Not run.** Dependencies could not be installed without network access. |
| Strict TypeScript check on the new `lib/` modules | **Passed**, except one expected error: `process` is undefined because `@types/node` is not installed in this sandbox. It is a declared devDependency, so it resolves after `npm install`. |
| Behavioral smoke test of graph layout, Mermaid export, file tree, and language styles | **Passed**, run in Node on sample data. |
| Full `next build` of `page.tsx` after the split | **Not run.** `node_modules` is not available. This is the first thing to run locally. |
| Endpoint and documentation consistency | Checked by hand against the route decorators and the frontend `fetch` calls. Every endpoint the frontend calls exists with a matching HTTP method. |

**Recommended first step on your machine:**

```bash
cd backend && pip install -r requirements.txt && python -m pytest
cd ../frontend && npm install && npm run build
```

If `npm run build` reports an error in the new imports, the most likely cause is the `@/` path alias. It is defined in `tsconfig.json` as `"@/*": ["./*"]`, so imports such as `@/lib/graph` resolve from the frontend root.
