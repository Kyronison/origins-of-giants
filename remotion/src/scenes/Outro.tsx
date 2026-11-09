import { T } from "../theme";
import { Frame, useEnter, RedRule, Layout } from "./common";

export const Outro: React.FC<{ d: any; caption?: string } & Layout> = ({ d, vertical, card }) => {
  vertical = vertical || card;
  const s = useEnter();
  return (
    <Frame vertical={vertical} card={card} align="center">
      <div style={{ fontFamily: T.display, fontSize: vertical ? 72 : 100, letterSpacing: -2, opacity: s }}>{d.text ?? "Next: what to watch"}</div>
      <RedRule width={160} />
      <div style={{ fontSize: 36, color: T.slate, marginTop: 24 }}>{d.sub ?? "Sources in the description."}</div>
    </Frame>
  );
};
