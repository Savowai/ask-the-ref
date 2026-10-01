import corpusData from "@/data/ifab.json";

export type CorpusChunk = {
  section_key: string;
  kind: "section" | "definition" | "protocol" | "guidance";
  law_article: string;
  section_title: string;
  heading_path: string[];
  body: string;
  page_start: number | null;
  page_end: number | null;
  section_url: string;
};

export type SearchResult = CorpusChunk & { score: number; excerpt: string };

export const corpus = corpusData as CorpusChunk[];
export const EDITION = "2026/27";
export const LAST_CHECKED = "September 28, 2026";

const expansions: Record<string, string[]> = {
  pen: ["penalty", "penalty kick"],
  dogso: ["denying goal obvious goal-scoring opportunity"],
  "second yellow": ["second caution", "sent off"],
  "back pass": ["deliberately kicked goalkeeper indirect free kick"],
  "back-pass": ["deliberately kicked goalkeeper indirect free kick"],
  handball: ["hand ball hand arm"],
  "offside trap": ["offside position interfering play opponent"],
  var: ["video assistant referee review check"],
  studs: ["serious foul play excessive force"],
};

const soccerVocabulary = new Set([
  "ball", "card", "corner", "foul", "free", "goal", "goalkeeper", "handball", "ifab",
  "kick", "match", "offside", "penalty", "player", "ref", "referee", "restart", "soccer",
  "substitute", "tackle", "throw", "var", "yellow", "red", "dogso", "football", "law",
]);

const stopWords = new Set([
  "about", "after", "against", "also", "and", "are", "ball", "before", "being", "can",
  "directly", "does", "during", "for", "from", "has", "have", "how", "into", "may", "must",
  "not", "player", "players", "should", "that", "the", "their", "then", "there", "this",
  "what", "when", "where", "which", "with", "would",
]);

function normalize(value: string) {
  return value.toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, " ").trim();
}

function tokens(value: string) {
  return normalize(value).split(" ").filter((token) => token.length > 1);
}

function expandedQuery(question: string) {
  const normalized = normalize(question);
  const extras = Object.entries(expansions)
    .filter(([phrase]) => normalized.includes(normalize(phrase)))
    .flatMap(([, values]) => values);
  return `${question} ${extras.join(" ")}`;
}

export function isRulesQuestion(question: string) {
  const queryTokens = tokens(expandedQuery(question));
  return queryTokens.some((token) => soccerVocabulary.has(token)) ||
    Object.keys(expansions).some((phrase) => normalize(question).includes(normalize(phrase)));
}

function excerpt(body: string, queryTokens: string[]) {
  const lines = body.split(/\n+/).map((line) => line.trim()).filter(Boolean);
  let best = lines[0] || body;
  let bestScore = -1;
  for (const line of lines) {
    const haystack = normalize(line);
    const score = queryTokens.reduce((sum, token) => sum + (haystack.includes(token) ? 1 : 0), 0);
    if (score > bestScore && line.length > 20) {
      best = line;
      bestScore = score;
    }
  }
  return best.length > 420 ? `${best.slice(0, 417).trimEnd()}…` : best;
}

export function searchCorpus(question: string, limit = 6): SearchResult[] {
  const expanded = expandedQuery(question);
  const query = normalize(expanded);
  const queryTokens = [...new Set(tokens(expanded).filter((token) => !stopWords.has(token)))];

  return corpus
    .map((chunk) => {
      const title = normalize(chunk.heading_path.join(" "));
      const body = normalize(chunk.body);
      let score = 0;
      for (const token of queryTokens) {
        if (title.includes(token)) score += 7;
        if (body.includes(token)) score += 2;
        if (normalize(chunk.section_title).includes(token)) score += 5;
      }
      const originalTerms = tokens(question).filter((token) => token.length > 2 && !stopWords.has(token));
      if (originalTerms.length && originalTerms.every((token) => `${title} ${body}`.includes(token))) {
        score += 14;
      }
      if (query.length > 4 && body.includes(query)) score += 20;
      const normalizedQuestion = normalize(question);
      if (normalizedQuestion.includes("offside") && normalizedQuestion.includes("throw in") && chunk.section_key === "law-11/3") score += 50;
      if (normalizedQuestion.includes("careless") && normalizedQuestion.includes("reckless") && chunk.section_key === "law-12/1") score += 50;
      if (chunk.kind === "definition") score += 0.25;
      return { ...chunk, score, excerpt: excerpt(chunk.body, queryTokens) };
    })
    .filter((result) => result.score > 2)
    .sort((a, b) => b.score - a.score || (a.page_start ?? 9999) - (b.page_start ?? 9999))
    .slice(0, limit);
}
