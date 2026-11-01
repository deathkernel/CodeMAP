import type { ReactNode } from "react";

export function Metric({ label, value }: { label: string; value: number }) {
  return <div className="rounded-xl bg-black/20 p-3"><div className="text-2xl font-semibold tabular-nums">{value}</div><div className="mt-1 text-[10px] uppercase tracking-wider text-slate-500">{label}</div></div>;
}

export function Feature({ icon, title, text }: { icon: ReactNode; title: string; text: string }) {
  return <article className="rounded-2xl border border-white/10 bg-white/[0.025] p-5"><div className="mb-4 inline-flex rounded-xl bg-indigo-500/10 p-2.5 text-indigo-300">{icon}</div><h2 className="font-medium">{title}</h2><p className="mt-2 text-sm leading-6 text-slate-400">{text}</p></article>;
}
