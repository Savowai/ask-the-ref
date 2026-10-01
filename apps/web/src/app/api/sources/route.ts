import { NextResponse } from "next/server";
import { EDITION, LAST_CHECKED, corpus } from "@/lib/search";

export async function GET() {
  return NextResponse.json({
    sources: [{
      id: "ifab", title: "IFAB Laws of the Game", edition: EDITION, status: "current",
      sections: corpus.length, lastChecked: LAST_CHECKED,
      url: "https://www.theifab.com/laws/latest/",
    }],
  });
}
