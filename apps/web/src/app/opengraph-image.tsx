import { ImageResponse } from "next/og";

export const alt = "Ask the Ref: current football rules, cited";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          background: "#f6f3ec",
          color: "#13251d",
          padding: 80,
        }}
      >
        <div style={{ display: "flex", fontSize: 28, letterSpacing: 4, color: "#0b593d" }}>
          IFAB LAWS OF THE GAME 2026/27
        </div>
        <div style={{ display: "flex", flexDirection: "column" }}>
          <div style={{ display: "flex", fontSize: 128, fontFamily: "Georgia, serif", letterSpacing: -6 }}>
            Ask the Ref
          </div>
          <div style={{ display: "flex", fontSize: 40, color: "#617068", marginTop: 16 }}>
            Plain-English questions. Exact rule text. Page-level citations.
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 16, fontSize: 28 }}>
          <div style={{ display: "flex", width: 24, height: 24, background: "#c9ff5c", borderRadius: 12 }} />
          348 sections · hybrid RAG search · no API key
        </div>
      </div>
    ),
    size,
  );
}
