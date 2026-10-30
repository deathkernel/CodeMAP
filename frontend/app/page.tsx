import { ArrowRight, Boxes, Bug, Github, Network, ScanSearch, Sparkles, UploadCloud } from "lucide-react";

const features = [
  { icon: Network, title: "Architecture map", text: "Explore modules and their relationships in an interactive graph." },
  { icon: Bug, title: "Potential bug insights", text: "Review static-analysis findings with file and line references." },
  { icon: Sparkles, title: "Local AI explanations", text: "Ask Ollama to explain code without sending source to a cloud AI." },
];

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-6xl flex-col px-6 py-8">
      <header className="flex items-center justify-between border-b border-white/10 pb-6">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-indigo-500/15 p-2 text-indigo-300"><Boxes size={22} /></div>
          <span className="text-lg font-semibold tracking-tight">CodeMap</span>
          <span className="rounded-full border border-white/10 px-2 py-1 text-xs text-slate-400">LOCAL AI</span>
        </div>
        <div className="text-sm text-slate-400">Codebase intelligence</div>
      </header>

      <section className="mx-auto flex w-full max-w-3xl flex-1 flex-col items-center justify-center py-20 text-center">
        <div className="mb-6 flex items-center gap-2 rounded-full border border-indigo-400/20 bg-indigo-400/10 px-4 py-2 text-sm text-indigo-200">
          <Sparkles size={15} /> Understand any codebase, locally
        </div>
        <h1 className="text-5xl font-semibold leading-tight tracking-tight sm:text-6xl">
          Your codebase,<br /><span className="text-indigo-300">mapped.</span>
        </h1>
        <p className="mt-6 max-w-xl text-base leading-7 text-slate-400">
          Turn repositories into architecture maps. Trace dependencies, inspect potential issues, and understand code with your local AI.
        </p>

        <div className="mt-10 w-full rounded-2xl border border-white/10 bg-white/[0.03] p-3 shadow-2xl shadow-indigo-950/20">
          <label htmlFor="repo" className="mb-2 block text-left text-xs font-medium uppercase tracking-wider text-slate-500">Public GitHub repository</label>
          <div className="flex flex-col gap-3 sm:flex-row">
            <div className="flex flex-1 items-center gap-3 rounded-xl border border-white/10 bg-black/20 px-4">
              <Github size={19} className="shrink-0 text-slate-400" />
              <input id="repo" disabled placeholder="https://github.com/owner/repository" className="h-12 min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-slate-600" />
            </div>
            <button disabled className="flex items-center justify-center gap-2 rounded-xl bg-indigo-500 px-5 py-3 text-sm font-semibold text-white opacity-60">
              Analyze <ArrowRight size={16} />
            </button>
          </div>
          <div className="mt-3 flex flex-col items-center justify-between gap-3 text-xs text-slate-500 sm:flex-row">
            <span>Repository analysis is coming in the next milestone.</span>
            <span className="flex items-center gap-2"><UploadCloud size={14} /> ZIP upload coming soon</span>
          </div>
        </div>

        <div className="mt-5 flex items-center gap-2 text-xs text-slate-500"><ScanSearch size={14} /> No repository code is executed.</div>
      </section>

      <section className="grid gap-4 pb-10 md:grid-cols-3">
        {features.map(({ icon: Icon, title, text }) => (
          <article key={title} className="rounded-2xl border border-white/10 bg-white/[0.025] p-5">
            <div className="mb-4 inline-flex rounded-xl bg-indigo-500/10 p-2.5 text-indigo-300"><Icon size={20} /></div>
            <h2 className="font-medium">{title}</h2>
            <p className="mt-2 text-sm leading-6 text-slate-400">{text}</p>
          </article>
        ))}
      </section>

      <footer className="border-t border-white/10 py-5 text-center text-xs text-slate-600">
        CodeMap · Local-first code intelligence · Early development
      </footer>
    </main>
  );
}
