"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";

type Result = {
  section_key: string;
  heading_path: string[];
  body: string;
  excerpt: string;
  section_url: string;
  page_start: number | null;
};

type Answer = {
  status: string;
  answer: string;
  results: Result[];
  edition: string;
  lastChecked: string;
};

const topics = ["Offside", "Handball", "VAR", "Fouls & cards", "Penalty kicks", "Substitutions", "Goalkeepers"];

export default function Home() {
  const [question, setQuestion] = useState("");
  const [competition, setCompetition] = useState("any");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [selected, setSelected] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function ask(event?: FormEvent) {
    event?.preventDefault();
    if (!question.trim()) return;
    setLoading(true);
    setError("");
    setAnswer(null);
    setSelected(0);
    try {
      const response = await fetch("/api/ask", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ question, competition }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "The request failed.");
      setAnswer(data);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The request failed.");
    } finally {
      setLoading(false);
    }
  }

  function useTopic(topic: string) {
    const prompts: Record<string, string> = {
      Offside: "Can a player be offside directly from a throw-in?",
      Handball: "When is touching the ball with the hand or arm an offence?",
      VAR: "When can VAR recommend an on-field review?",
      "Fouls & cards": "What is the difference between careless, reckless and excessive force?",
      "Penalty kicks": "What happens if the goalkeeper leaves the goal line during a penalty kick?",
      Substitutions: "When does a substitution become complete?",
      Goalkeepers: "How long may a goalkeeper control the ball with their hands?",
    };
    setQuestion(prompts[topic]);
  }

  return (
    <main>
      <nav className="nav shell">
        <Link className="brand" href="/"><span className="mark">AR</span><span>Ask the Ref</span></Link>
        <div className="nav-links"><Link href="/laws">Browse the Laws</Link><a href="#method">How it works</a></div>
      </nav>

      <section className="hero shell">
        <div className="eyebrow"><span className="live-dot" /> Current IFAB Laws · 2026/27</div>
        <h1>Football rules.<br /><em>Evidence included.</em></h1>
        <p className="lede">Ask a plain-English question and inspect the exact section behind every result. Free to use, with no model API key.</p>

        <form className="ask-box" onSubmit={ask}>
          <label htmlFor="question">Ask about a match situation or rule</label>
          <textarea id="question" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="A defender deliberately handles the ball to stop a goal. What happens?" rows={3} />
          <div className="ask-actions">
            <select aria-label="Competition" value={competition} onChange={(event) => setCompetition(event.target.value)}>
              <option value="any">Any / IFAB</option>
              <option value="premier-league">Premier League · coming next</option>
              <option value="uefa">UEFA · coming next</option>
              <option value="fifa">FIFA · coming next</option>
            </select>
            <button type="submit" disabled={loading || !question.trim()}>{loading ? "Checking the Laws…" : "Ask the Ref"}<span>→</span></button>
          </div>
        </form>

        <div className="chips" aria-label="Quick topics">
          {topics.map((topic) => <button key={topic} type="button" onClick={() => useTopic(topic)}>{topic}</button>)}
        </div>
      </section>

      {(answer || error) && (
        <section className="results shell" aria-live="polite">
          <div className="answer-card">
            <div className="answer-heading"><span className="whistle">✓</span><div><small>RULING</small><h2>{answer?.status === "answered" ? "Relevant current law found" : "No ruling returned"}</h2></div></div>
            <p>{error || answer?.answer}</p>
            {answer?.results.map((result, index) => (
              <button className={`result-row ${selected === index ? "active" : ""}`} onClick={() => setSelected(index)} key={result.section_key}>
                <span className="citation-number">{index + 1}</span>
                <span><strong>{result.heading_path.slice(1).join(" › ")}</strong><small>{result.page_start ? `Page ${result.page_start}` : "Official web amendment"} · IFAB {answer.edition}</small></span>
                <span>View text →</span>
              </button>
            ))}
          </div>
          {answer?.results.length ? (
            <aside className="source-panel">
              <div className="source-top"><small>QUOTED RULE TEXT</small><a href={answer.results[selected].section_url} target="_blank" rel="noreferrer">Official source ↗</a></div>
              <h3>{answer.results[selected].heading_path.join(" › ")}</h3>
              <blockquote>{answer.results[selected].excerpt}</blockquote>
              <details><summary>Read full section</summary><p>{answer.results[selected].body}</p></details>
              <div className="source-meta"><span>Edition {answer.edition}</span><span>Checked {answer.lastChecked}</span></div>
            </aside>
          ) : null}
        </section>
      )}

      <section className="trust shell" id="method">
        <div><span>01</span><h3>Current corpus</h3><p>Only the active IFAB edition is searchable. Replacements remove the previous edition.</p></div>
        <div><span>02</span><h3>Section-level search</h3><p>Each result preserves its Law, heading path, page, and official source URL.</p></div>
        <div><span>03</span><h3>Inspect the evidence</h3><p>The public build quotes the source instead of generating unsupported legal-sounding text.</p></div>
      </section>

      <footer className="shell"><span>Ask the Ref · An evidence-first football rules project</span><span>Rules current as of IFAB 2026/27 · checked September 28, 2026</span></footer>
    </main>
  );
}
