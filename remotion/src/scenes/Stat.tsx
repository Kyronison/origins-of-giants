import { useCurrentFrame, useVideoConfig } from "remotion";
import { T } from "../theme";
import { Frame, RedRule, useEnter, Caption, Layout } from "./common";

/** Одна цифра. Числовая часть считается вверх за 0.8 сек; префикс/суффикс стоят на месте. */
export const Stat: React.FC<{ d: any; caption?: string } & Layout> = ({ d, caption, vertical, card }) => {
  vertical = vertical || card;
  const f = useCurrentFrame(); const { fps } = useVideoConfig(); const s = useEnter();
  const m = String(d.value).match(/^([^0-9-]*)(-?[\d.,]+)(.*)$/);
  let shown = d.value;
  if (m) {
    const target = parseFloat(m[2].replace(/,/g, "")); const dec = (m[2].split(".")[1] || "").length;
    const p = Math.min(1, f / (fps * 0.8)); const eased = 1 - Math.pow(1 - p, 3);
    shown = m[1] + (target * eased).toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec }) + m[3];
  }
  return (
    <Frame vertical={vertical} card={card}>
      <div style={{ fontFamily: T.display, fontWeight: 600, fontSize: vertical ? 190 : 300, lineHeight: 0.95, letterSpacing: -8,
        color: T.ink, opacity: s, fontVariantNumeric: "tabular-nums" }}>{shown}</div>
      <RedRule width={320} delay={fps * 0.7} />
      <div style={{ fontSize: vertical ? 40 : 46, fontWeight: 500, marginTop: 30, maxWidth: 1100, lineHeight: 1.25 }}>{d.label}</div>
      <Caption text={caption} vertical={vertical} card={card} />
    </Frame>
  );
};
