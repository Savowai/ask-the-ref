import { NextRequest, NextResponse } from "next/server";
import { EDITION, LAST_CHECKED, isRulesQuestion, searchCorpus } from "@/lib/search";

export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  let input: unknown;
  try {
    input = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  const question = typeof input === "object" && input !== null && "question" in input
    ? String(input.question).trim()
    : "";
  const competition = typeof input === "object" && input !== null && "competition" in input
    ? String(input.competition)
    : "any";

  if (!question || question.length > 1000) {
    return NextResponse.json({ error: "Ask a question between 1 and 1,000 characters." }, { status: 400 });
  }

  if (competition !== "any" && competition !== "ifab") {
    return NextResponse.json({
      status: "scope_unavailable",
      answer: "That competition rulebook is listed in the source manifest but is not yet in the public corpus. Choose Any / IFAB for current Laws of the Game answers.",
      results: [], edition: EDITION, lastChecked: LAST_CHECKED,
    });
  }

  if (!isRulesQuestion(question)) {
    return NextResponse.json({
      status: "off_topic",
      answer: "I can only help with questions about the current rules of football.",
      results: [], edition: EDITION, lastChecked: LAST_CHECKED,
    });
  }

  const results = searchCorpus(question);
  if (!results.length) {
    return NextResponse.json({
      status: "insufficient_evidence",
      answer: "I could not find a strong enough match in the current IFAB corpus. Try naming the offence, restart, or Law involved.",
      results: [], edition: EDITION, lastChecked: LAST_CHECKED,
    });
  }

  return NextResponse.json({
    status: "answered",
    answer: "These current IFAB sections are the closest authorities for your question. Read the cited wording below; where the Law leaves a decision to the referee, the app does not invent a ruling.",
    results, edition: EDITION, lastChecked: LAST_CHECKED,
  });
}
