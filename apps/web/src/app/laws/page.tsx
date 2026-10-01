import Link from "next/link";
import { EDITION, corpus } from "@/lib/search";

export default function LawsPage() {
  const groups = new Map<string, typeof corpus>();
  for (const chunk of corpus) {
    const name = chunk.heading_path[1] || "Other material";
    groups.set(name, [...(groups.get(name) || []), chunk]);
  }

  return (
    <main>
      <nav className="nav shell"><Link className="brand" href="/"><span className="mark">AR</span><span>Ask the Ref</span></Link><div className="nav-links"><Link href="/">Ask a question</Link></div></nav>
      <section className="laws-hero shell"><div className="eyebrow">IFAB · Edition {EDITION}</div><h1>Browse the Laws</h1><p>All {corpus.length} structured sections in the currently active IFAB corpus.</p></section>
      <section className="law-list shell">
        {[...groups.entries()].map(([name, chunks]) => (
          <details key={name}>
            <summary><span>{name}</span><small>{chunks.length} sections</small></summary>
            <div className="law-sections">
              {chunks.map((chunk) => <a href={chunk.section_url} target="_blank" rel="noreferrer" key={chunk.section_key}><span>{chunk.section_title}</span><small>{chunk.page_start ? `Page ${chunk.page_start}` : "Web amendment"} ↗</small></a>)}
            </div>
          </details>
        ))}
      </section>
      <footer className="shell"><span>Ask the Ref</span><span>Official source links open at the cited PDF page.</span></footer>
    </main>
  );
}
