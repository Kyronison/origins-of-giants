import { AbsoluteFill, Img, staticFile } from "remotion";
import { Concept, Props, T } from "./theme";

type P = Props & { concept: Concept; image: string };
/** Картинка во весь кадр, бумажная плашка с заголовком слева снизу, красная линия под ним. */
export const Thumb: React.FC<P> = ({ concept, image }) => (
  <AbsoluteFill style={{ background: T.ink }}>
    {image && <Img src={staticFile(image)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />}
    <div style={{ position: "absolute", left: 0, bottom: 0, background: T.paper, padding: "36px 56px 44px 56px", maxWidth: 760 }}>
      <div style={{ fontFamily: T.display, fontWeight: 600, fontSize: 92, lineHeight: 0.98, color: T.ink, letterSpacing: -2 }}>
        {concept.headline}
      </div>
      <div style={{ marginTop: 22, width: 160, height: 10, background: T.red }} />
    </div>
  </AbsoluteFill>
);
