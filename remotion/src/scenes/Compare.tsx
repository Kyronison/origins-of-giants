import { T } from "../theme";
import { Frame, useEnter, Caption, Layout, pick } from "./common";

export const Compare: React.FC<{ d: any; caption?: string } & Layout> = ({ d, caption, vertical, card }) => {
  const L = { vertical, card };
  const Col = ({ c, k }: { c: any; k: number }) => {
    const s = useEnter(k * 10);
    return (
      <div style={{ flex: 1, opacity: s, transform: `translateY(${(1 - s) * 20}px)`, borderTop: `${card ? 6 : 8}px solid ${k ? T.red : T.ink}`, paddingTop: card ? 18 : 28 }}>
        <div style={{ fontFamily: T.display, fontSize: pick(L, 60, 44, 44), marginBottom: card ? 14 : 26 }}>{c?.title ?? ""}</div>
        {(c?.rows ?? []).map((r: string, i: number) => (
          <div key={i} style={{ fontSize: pick(L, 36, 30, 28), lineHeight: 1.3, padding: card ? "9px 0" : "14px 0", borderBottom: `1px solid ${T.rule}` }}>{r}</div>
        ))}
      </div>
    );
  };
  return (
    <Frame vertical={vertical} card={card}>
      <div style={{ display: "flex", flexDirection: vertical && !card ? "column" : "row", gap: pick(L, 90, 40, 56), width: "100%" }}>
        <Col c={d.left} k={0} /><Col c={d.right} k={1} />
      </div>
      <Caption text={caption} vertical={vertical} card={card} />
    </Frame>
  );
};
