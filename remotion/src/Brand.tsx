import { AbsoluteFill, Img, staticFile } from "remotion";
import { T } from "./theme";

/** Оформление канала в той же системе, что и видео: бумага, чернила, Fraunces, одна красная линия.
 *  Avatar 800×800 (показывается кругом — всё внутри центрального круга), Banner 2560×1440 (текст только в
 *  безопасной зоне 1546×423 по центру: её видно на телефоне; десктоп видит полосу 2560×423; ТВ — всё),
 *  Watermark 150×150 с прозрачным фоном для брендинга поверх видео.
 *  image — кинематографичный фон (public dir), как в видео story-формата: картинка + бумажная карточка. */
export type Brand = { name: string; mark: string; tagline: string; image?: string };

export const Avatar: React.FC<Brand> = ({ mark }) => (
  <AbsoluteFill style={{ background: T.paper, alignItems: "center", justifyContent: "center" }}>
    <div style={{ fontFamily: T.display, fontWeight: 600, fontSize: mark.length > 1 ? 300 : 470, lineHeight: 1, color: T.ink, letterSpacing: -14, marginTop: -30 }}>
      {mark}
    </div>
    <div style={{ width: 220, height: 22, background: T.red, marginTop: 6 }} />
  </AbsoluteFill>
);

export const Banner: React.FC<Brand> = ({ name, tagline, image }) => (
  <AbsoluteFill style={{ background: T.paper }}>
    {image ? (
      <>
        <Img src={staticFile(image)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at center, rgba(0,0,0,0.05) 40%, rgba(0,0,0,0.45) 100%)" }} />
      </>
    ) : (
      <>
        {[120, 240, 360, 1080, 1200, 1320].map((y) => (
          <div key={y} style={{ position: "absolute", left: 0, right: 0, top: y, height: 2, background: T.rule, opacity: 0.7 }} />
        ))}
        <div style={{ position: "absolute", left: 160, top: 96, fontFamily: T.text, fontSize: 34, color: T.slate, letterSpacing: 2 }}>
          PRIMARY SOURCES · OWN CALCULATIONS · A THESIS YOU CAN ARGUE WITH
        </div>
      </>
    )}
    <div style={{ position: "absolute", left: 507, top: 508, width: 1546, height: 423, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ background: image ? T.paper : "transparent", padding: image ? "44px 72px 48px" : 0, textAlign: "center",
        boxShadow: image ? "0 30px 90px rgba(0,0,0,0.45)" : "none" }}>
        <div style={{ fontFamily: T.display, fontWeight: 600, fontSize: name.length > 14 ? 128 : 176, letterSpacing: -5, color: T.ink, lineHeight: 1, whiteSpace: "nowrap" }}>
          {name}
        </div>
        <div style={{ width: 240, height: 12, background: T.red, margin: "24px auto 0" }} />
        <div style={{ fontFamily: T.text, fontSize: 42, color: T.slate, marginTop: 20, whiteSpace: "nowrap" }}>{tagline}</div>
      </div>
    </div>
  </AbsoluteFill>
);

export const Watermark: React.FC<Brand> = ({ mark }) => (
  <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
    <div style={{ fontFamily: T.display, fontWeight: 600, fontSize: mark.length > 1 ? 64 : 104, lineHeight: 1, color: T.ink, marginTop: -8 }}>{mark}</div>
    <div style={{ width: 56, height: 7, background: T.red, marginTop: 2 }} />
  </AbsoluteFill>
);
