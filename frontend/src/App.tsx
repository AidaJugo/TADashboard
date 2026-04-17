import { tokens } from "@/theme/tokens";

export function App() {
  return (
    <main
      style={{
        minHeight: "100vh",
        padding: "48px",
        background: tokens.colors.lightGrey,
        color: tokens.colors.black,
        fontFamily: tokens.typography.fontFamily,
      }}
    >
      <h1 style={{ fontSize: 48, fontWeight: 700, marginBottom: 16 }}>
        Symphony TA Hiring Report
      </h1>
      <p style={{ fontSize: 16, maxWidth: 720 }}>
        Scaffolding only. Report, auth, and admin views ship next. See HANDOFF.md.
      </p>
    </main>
  );
}
