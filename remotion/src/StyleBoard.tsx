import { AbsoluteFill, Img, staticFile } from "remotion";
import { loadFont as loadPlayfair } from "@remotion/google-fonts/PlayfairDisplay";
import { loadFont as loadCaslon } from "@remotion/google-fonts/LibreCaslonText";
import { loadFont as loadCourier } from "@remotion/google-fonts/CourierPrime";
import { loadFont as loadInter } from "@remotion/google-fonts/InterTight";
import { T } from "./theme";
import { GRADE } from "./Film";

/** Доска вариантов оформления (владелец 16.09: «предложи шрифты, подчёркивания»): одна и та же сцена в трёх стилях.
 *  scene: people — два человека с плашками и возрастом; broll — архивное фото с подписью и цифрой; chapter — карточка главы. */
const pf = loadPlayfair("normal", { weights: ["500", "600"], subsets: ["latin"] });
const pfi = loadPlayfair("italic", { weights: ["500"], subsets: ["latin"] });
const cs = loadCaslon("normal", { weights: ["400", "700"], subsets: ["latin"] });
const cp = loadCourier("normal", { weights: ["400", "700"], subsets: ["latin"] });
const it = loadInter("normal", { weights: ["400", "500", "600"], subsets: ["latin"] });

export type BoardProps = { style: "ledger" | "archive" | "cinema"; scene: "people" | "broll" | "chapter"; left: string; right: string; photo: string };

const Photo: React.FC<{ src: string; style?: React.CSSProperties }> = ({ src, style }) => (
  <Img src={staticFile(src)} style={{ width: "100%", height: "100%", objectFit: "cover", filter: GRADE, ...style }} />
);
const Vig = () => <AbsoluteFill style={{ background: "radial-gradient(ellipse at center, rgba(0,0,0,0) 45%, rgba(0,0,0,.5) 100%)" }} />;

// ---------- 1. Журнал (как сейчас) ----------
const Ledger: React.FC<BoardProps> = ({ scene, left, right, photo }) => {
  if (scene === "chapter") return (
    <AbsoluteFill style={{ background: T.ink, alignItems: "center", justifyContent: "center" }}>
      <AbsoluteFill style={{ opacity: 0.35 }}><Photo src={photo} /></AbsoluteFill>
      <div style={{ textAlign: "center" }}>
        <div style={{ fontFamily: T.text, fontSize: 34, letterSpacing: 6, color: T.paper, opacity: 0.75, marginBottom: 22 }}>CHAPTER III</div>
        <div style={{ fontFamily: T.display, fontSize: 118, fontWeight: 500, color: T.paper, letterSpacing: -2 }}>The Struggle</div>
        <div style={{ height: 6, width: 260, background: T.red, margin: "30px auto 0" }} />
      </div>
    </AbsoluteFill>
  );
  if (scene === "broll") return (
    <AbsoluteFill><Photo src={photo} /><Vig />
      <div style={{ position: "absolute", left: T.pad, top: T.pad * 1.7, background: T.paper, padding: "26px 36px 28px", boxShadow: "0 20px 60px rgba(0,0,0,.35)" }}>
        <div style={{ fontFamily: T.display, fontWeight: 600, fontSize: 112, lineHeight: 0.95, letterSpacing: -4, color: T.ink }}>$250,000</div>
        <div style={{ height: 6, width: 120, background: T.red, marginTop: 12 }} />
        <div style={{ fontFamily: T.text, fontSize: 26, color: T.slate, marginTop: 10 }}>line of credit</div>
      </div>
      <div style={{ position: "absolute", left: T.pad, bottom: T.pad + 110, background: T.paper, padding: "14px 26px 14px", minWidth: 260, boxShadow: "0 10px 30px rgba(0,0,0,.3)" }}>
        <div style={{ fontFamily: T.display, fontSize: 30, fontWeight: 500, color: T.ink }}>Mike Markkula</div>
        <div style={{ fontFamily: T.text, fontSize: 22, color: T.slate, marginTop: 4 }}>1977</div>
        <div style={{ height: 3, width: "100%", background: T.red, marginTop: 10 }} />
      </div>
    </AbsoluteFill>
  );
  const col = (src: string, name: string, role: string, years: string, age: string, x: number) => (
    <div style={{ position: "absolute", left: x, top: 90, width: 780 }}>
      <div style={{ width: 760, height: 560, background: T.paper, padding: 10, boxShadow: "0 18px 50px rgba(0,0,0,.35)" }}><Photo src={src} /></div>
      <div style={{ marginTop: 30, color: T.paper }}>
        <div style={{ fontFamily: T.display, fontSize: 40, fontWeight: 500 }}>{name}</div>
        <div style={{ fontFamily: T.text, fontSize: 26, color: T.slate, marginTop: 6 }}>{role} · {years}</div>
        <div style={{ height: 3, width: 120, background: T.red, marginTop: 12 }} />
        <div style={{ marginTop: 14 }}><span style={{ fontFamily: T.display, fontSize: 44, fontWeight: 600 }}>{age}</span><span style={{ fontFamily: T.text, fontSize: 24, color: T.slate, marginLeft: 10 }}>years old</span></div>
      </div>
    </div>
  );
  return <AbsoluteFill style={{ background: T.ink }}>{col(left, "Steve Jobs", "co-founder, visionary", "1955–2011", "21", 110)}{col(right, "Steve Wozniak", "co-founder, engineer", "born 1950", "25", 1010)}</AbsoluteFill>;
};

// ---------- 2. Архивное досье: машинопись на бумажных ярлыках ----------
const CREAM = "#EFE6D2", BROWN = "#2B2118", OX = "#7A2E1F";
const Tag: React.FC<{ children: React.ReactNode; style?: React.CSSProperties }> = ({ children, style }) => (
  <div style={{ background: CREAM, color: BROWN, boxShadow: "0 12px 34px rgba(0,0,0,.4)", padding: "16px 24px", backgroundImage: "linear-gradient(rgba(122,46,31,.06) 1px, transparent 1px)", backgroundSize: "100% 30px", ...style }}>{children}</div>
);
const Archive: React.FC<BoardProps> = ({ scene, left, right, photo }) => {
  if (scene === "chapter") return (
    <AbsoluteFill style={{ background: "#1B1511", alignItems: "center", justifyContent: "center" }}>
      <AbsoluteFill style={{ opacity: 0.3 }}><Photo src={photo} /></AbsoluteFill>
      <Tag style={{ padding: "44px 90px", transform: "rotate(-0.6deg)", textAlign: "center" }}>
        <div style={{ fontFamily: cp.fontFamily, fontSize: 30, letterSpacing: 4, color: OX }}>— FILE No. 3 —</div>
        <div style={{ fontFamily: cs.fontFamily, fontSize: 104, color: BROWN, marginTop: 10 }}>The Struggle</div>
        <div style={{ borderTop: `2px solid ${BROWN}`, borderBottom: `2px solid ${BROWN}`, height: 5, width: 300, margin: "22px auto 0" }} />
      </Tag>
    </AbsoluteFill>
  );
  if (scene === "broll") return (
    <AbsoluteFill><Photo src={photo} /><Vig />
      <Tag style={{ position: "absolute", left: T.pad, top: T.pad * 1.5, transform: "rotate(-1deg)", padding: "20px 32px 22px" }}>
        <div style={{ fontFamily: cs.fontFamily, fontSize: 104, lineHeight: 1, color: BROWN }}>$250,000</div>
        <div style={{ fontFamily: cp.fontFamily, fontSize: 26, letterSpacing: 2, color: OX, marginTop: 8 }}>LINE OF CREDIT</div>
      </Tag>
      <Tag style={{ position: "absolute", left: T.pad, bottom: T.pad + 90, transform: "rotate(0.8deg)" }}>
        <div style={{ fontFamily: cp.fontFamily, fontSize: 28, fontWeight: 700, letterSpacing: 1 }}>MIKE MARKKULA</div>
        <div style={{ fontFamily: cp.fontFamily, fontSize: 22, color: OX, marginTop: 4 }}>CUPERTINO, 1977</div>
      </Tag>
    </AbsoluteFill>
  );
  const col = (src: string, name: string, role: string, years: string, age: string, x: number, rot: number) => (
    <div style={{ position: "absolute", left: x, top: 80, width: 780 }}>
      <div style={{ width: 740, height: 540, background: "#F6F1E6", padding: "16px 16px 46px", transform: `rotate(${rot}deg)`, boxShadow: "0 18px 50px rgba(0,0,0,.45)" }}><Photo src={src} /></div>
      <Tag style={{ marginTop: 28, width: 600, transform: `rotate(${-rot / 2}deg)` }}>
        <div style={{ fontFamily: cs.fontFamily, fontSize: 40 }}>{name}</div>
        <div style={{ fontFamily: cp.fontFamily, fontSize: 22, letterSpacing: 1, marginTop: 6 }}>{role.toUpperCase()} · {years.toUpperCase()}</div>
        <div style={{ fontFamily: cp.fontFamily, fontSize: 30, fontWeight: 700, color: OX, marginTop: 10 }}>AGE {age}</div>
      </Tag>
    </div>
  );
  return <AbsoluteFill style={{ background: "#1B1511" }}>{col(left, "Steve Jobs", "co-founder, visionary", "1955–2011", "21", 110, -1.2)}{col(right, "Steve Wozniak", "co-founder, engineer", "born 1950", "25", 1010, 1)}</AbsoluteFill>;
};

// ---------- 3. Кино: без плашек, белый текст на кадре, янтарная линия ----------
const WHITE = "#F4EFE6", AMBER = "#D9A441";
const sh = "0 2px 18px rgba(0,0,0,.75), 0 1px 3px rgba(0,0,0,.6)";
const Cinema: React.FC<BoardProps> = ({ scene, left, right, photo }) => {
  if (scene === "chapter") return (
    <AbsoluteFill style={{ background: "#0E0D0C", alignItems: "center", justifyContent: "center" }}>
      <AbsoluteFill style={{ opacity: 0.28 }}><Photo src={photo} style={{ filter: GRADE + " blur(6px)" }} /></AbsoluteFill>
      <div style={{ textAlign: "center", color: WHITE, textShadow: sh }}>
        <div style={{ fontFamily: it.fontFamily, fontSize: 26, fontWeight: 500, letterSpacing: 12, opacity: 0.8 }}>CHAPTER III</div>
        <div style={{ height: 2, width: 90, background: AMBER, margin: "26px auto" }} />
        <div style={{ fontFamily: pfi.fontFamily, fontStyle: "italic", fontSize: 120, fontWeight: 500 }}>The Struggle</div>
      </div>
    </AbsoluteFill>
  );
  if (scene === "broll") return (
    <AbsoluteFill><Photo src={photo} /><Vig />
      <AbsoluteFill style={{ background: "radial-gradient(ellipse 60% 55% at 12% 30%, rgba(0,0,0,.72) 0%, rgba(0,0,0,0) 100%), radial-gradient(ellipse 45% 35% at 8% 88%, rgba(0,0,0,.65) 0%, rgba(0,0,0,0) 100%)" }} />
      <div style={{ position: "absolute", left: T.pad, top: T.pad * 2, color: WHITE, textShadow: sh }}>
        <div style={{ fontFamily: pf.fontFamily, fontWeight: 600, fontSize: 132, lineHeight: 1 }}>$250,000</div>
        <div style={{ display: "flex", alignItems: "center", gap: 16, marginTop: 14 }}>
          <div style={{ height: 2, width: 60, background: AMBER }} />
          <div style={{ fontFamily: it.fontFamily, fontSize: 24, fontWeight: 500, letterSpacing: 5 }}>LINE OF CREDIT</div>
        </div>
      </div>
      <div style={{ position: "absolute", left: T.pad, bottom: T.pad + 40, color: WHITE, textShadow: sh }}>
        <div style={{ fontFamily: it.fontFamily, fontSize: 24, fontWeight: 600, letterSpacing: 5 }}>MIKE MARKKULA</div>
        <div style={{ fontFamily: pfi.fontFamily, fontStyle: "italic", fontSize: 30, color: AMBER, marginTop: 4 }}>Cupertino, 1977</div>
      </div>
    </AbsoluteFill>
  );
  const col = (src: string, name: string, role: string, years: string, age: string, x: number) => (
    <div style={{ position: "absolute", left: x, top: 90, width: 800 }}>
      <div style={{ width: 800, height: 580, outline: "1px solid rgba(244,239,230,.25)", outlineOffset: 10 }}><Photo src={src} /></div>
      <div style={{ marginTop: 40, color: WHITE }}>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", width: 800 }}>
          <div style={{ fontFamily: pf.fontFamily, fontSize: 50, fontWeight: 500 }}>{name}</div>
          <div><span style={{ fontFamily: pf.fontFamily, fontSize: 50, fontWeight: 600, color: AMBER }}>{age}</span>
            <span style={{ fontFamily: it.fontFamily, fontSize: 18, letterSpacing: 4, marginLeft: 10, opacity: 0.8 }}>YEARS OLD</span></div>
        </div>
        <div style={{ height: 2, width: 70, background: AMBER, margin: "14px 0" }} />
        <div style={{ fontFamily: it.fontFamily, fontSize: 20, fontWeight: 500, letterSpacing: 4, opacity: 0.75 }}>{role.toUpperCase()}  ·  {years.toUpperCase()}</div>
      </div>
    </div>
  );
  return <AbsoluteFill style={{ background: "#0E0D0C" }}>{col(left, "Steve Jobs", "co-founder, visionary", "1955–2011", "21", 100)}{col(right, "Steve Wozniak", "co-founder, engineer", "born 1950", "25", 1020)}</AbsoluteFill>;
};

export const StyleBoard: React.FC<BoardProps> = (p) => p.style === "archive" ? <Archive {...p} /> : p.style === "cinema" ? <Cinema {...p} /> : <Ledger {...p} />;
