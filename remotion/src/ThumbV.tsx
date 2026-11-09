import { AbsoluteFill, Img, staticFile } from "remotion";
import { loadFont as loadAnton } from "@remotion/google-fonts/Anton";
import { loadFont as loadBebas } from "@remotion/google-fonts/BebasNeue";
import { D, Tag } from "./dossier";
import grain from "./film/grain_1.png";

/** Варианты обложки story-видео (1280×720), владелец 17.09: «давай другие версии превью».
 *  Правила: настоящие архивные снимки вместо генерации, ≤ 5 слов, одна главная цифра, читается на 360 px в ленте;
 *  справа снизу не ставим текст — там YouTube рисует длительность ролика. */
const anton = loadAnton("normal", { weights: ["400"], subsets: ["latin"] });
const bebas = loadBebas("normal", { weights: ["400"], subsets: ["latin"] });
const W = 1280, H = 720;

export type ThumbVProps = { variant: string; bw: string; color: string; now: string; jobs: string; woz: string;
  cut?: string; product?: string; logo?: string; wordmark?: string; paper?: string; hook?: string; hookLabel?: string; layout?: string; stamp?: string; logoPos?: string; portraitFit?: boolean; kind?: string; bg?: string; logoBlack?: string; title?: string; brandWord?: string; cutH?: number; cutX?: number; mark?: string; cutSepia?: number;
  bg2?: string; text1?: string; text2?: string; hook2?: string; tagL?: string; tagR?: string; markSize?: number; theme?: string;
  logoStyle?: string; brandColor?: string; logoAspect?: number; logoMask?: string; logoScale?: number; logoPlate?: boolean; logoBottom?: number; logoCorner?: string; logoSticker?: boolean; plateColor?: string; wordColor?: string; lines?: { k: string; v: string; hot?: boolean }[]; pct?: number; bgColor?: string;
  logo2?: string; logoAspect2?: number; brandColor2?: string };

const OUT = [[3, 0], [-3, 0], [0, 3], [0, -3], [2, 2], [-2, 2], [2, -2], [-2, -2]].map(([x, y]) => `${x}px ${y}px 0 #0d0a08`).join(", ") + ", 0 8px 22px rgba(0,0,0,.6)";
const Big: React.FC<{ children: React.ReactNode; size: number; color?: string; style?: React.CSSProperties }> = ({ children, size, color = "#FFFFFF", style }) => (
  <div style={{ fontFamily: anton.fontFamily, fontSize: size, lineHeight: 0.95, textTransform: "uppercase", color, textShadow: OUT, letterSpacing: 1, ...style }}>{children}</div>
);
const Box: React.FC<{ children: React.ReactNode; size: number; rotate?: number; style?: React.CSSProperties }> = ({ children, size, rotate = -2, style }) => (
  <span style={{ display: "inline-block", fontFamily: anton.fontFamily, fontSize: size, lineHeight: 1, textTransform: "uppercase", color: D.cream, background: D.ox,
    padding: "6px 20px 10px", transform: `rotate(${rotate}deg)`, boxShadow: "0 14px 34px rgba(0,0,0,.5)", ...style }}>{children}</span>
);
const Photo: React.FC<{ src: string; pos: string; scale?: number; filter?: string; style?: React.CSSProperties }> = ({ src, pos, scale = 1, filter, style }) => (
  <Img src={staticFile(src)} style={{ position: "absolute", width: "100%", height: "100%", objectFit: "cover", objectPosition: pos, transform: `scale(${scale})`, transformOrigin: pos, filter, ...style }} />
);
const Vignette = ({ a = 0.55 }: { a?: number }) => <AbsoluteFill style={{ background: `radial-gradient(ellipse at 45% 45%, rgba(0,0,0,0) 50%, rgba(0,0,0,${a}) 100%)` }} />;

/** 1. Культовый снимок 1976 + контраст денег: «$1,300 → $3.7 TRILLION». */
const MoneyBW: React.FC<ThumbVProps> = ({ bw }) => (
  <AbsoluteFill style={{ background: D.dark }}>
    <div style={{ position: "absolute", left: 0, top: 0, width: 820, height: H, overflow: "hidden" }}>
      <Photo src={bw} pos="42% 22%" scale={1.18} filter="grayscale(1) contrast(1.15) brightness(1.02)" />
    </div>
    <AbsoluteFill style={{ background: "linear-gradient(90deg, rgba(27,21,17,0) 38%, rgba(27,21,17,.92) 64%, #1B1511 72%)" }} />
    <Vignette a={0.45} />
    <div style={{ position: "absolute", left: 38, top: 34 }}><Tag rotate={-3}><div style={{ fontFamily: D.mono, fontWeight: 700, fontSize: 40, letterSpacing: 4, color: D.ox }}>1976</div></Tag></div>
    <div style={{ position: "absolute", right: 46, top: 110, width: 470, textAlign: "center" }}>
      <Big size={132} color={D.cream}>$1,300</Big>
      <svg width={90} height={90} viewBox="0 0 90 90" style={{ margin: "4px auto -6px", display: "block" }}>
        <path d="M45 6 V70 M18 46 L45 76 L72 46" stroke={D.cream} strokeWidth={12} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <Box size={150} rotate={-3}>$3.7T</Box>
    </div>
  </AbsoluteFill>
);

/** 2. Цветной снимок с платой: «THE $666 COMPUTER» + обводка платы. */
const Computer666: React.FC<ThumbVProps> = ({ color }) => (
  <AbsoluteFill style={{ background: D.dark }}>
    <Photo src={color} pos="50% 18%" scale={1.0} filter="contrast(1.08) saturate(1.15)" style={{ top: 38 }} />
    <AbsoluteFill style={{ background: "linear-gradient(180deg, rgba(0,0,0,.72) 0%, rgba(0,0,0,.15) 34%, rgba(0,0,0,0) 60%)" }} />
    <Vignette a={0.4} />
    <svg width={W} height={H} style={{ position: "absolute", inset: 0 }}>
      <ellipse cx={715} cy={575} rx={390} ry={128} fill="none" stroke={D.ox} strokeWidth={14} transform="rotate(-4 715 575)" />
      <ellipse cx={715} cy={575} rx={390} ry={128} fill="none" stroke={D.cream} strokeWidth={4} transform="rotate(-4 715 575)" opacity={0.6} />
    </svg>
    <div style={{ position: "absolute", left: 0, right: 0, top: 28, textAlign: "center" }}>
      <Big size={104}>THE <Box size={108} rotate={-2} style={{ margin: "0 6px" }}>$666</Box> COMPUTER</Big>
    </div>
    <div style={{ position: "absolute", left: 36, bottom: 22 }}><Tag rotate={-2}><div style={{ fontFamily: D.mono, fontWeight: 700, fontSize: 30, letterSpacing: 3, color: D.brown }}>THAT BUILT A $3.7T GIANT</div></Tag></div>
  </AbsoluteFill>
);

/** 3. Тогда / сейчас: чёрно-белые основатели 1976 против складного iPhone 2026. */
const ThenNow: React.FC<ThumbVProps> = ({ bw, now }) => (
  <AbsoluteFill style={{ background: D.dark }}>
    <div style={{ position: "absolute", left: 0, top: 0, width: 700, height: H, overflow: "hidden", clipPath: "polygon(0 0, 100% 0, 84% 100%, 0 100%)" }}>
      <Photo src={bw} pos="45% 20%" scale={1.25} filter="grayscale(1) sepia(0.25) contrast(1.12)" />
      <AbsoluteFill style={{ background: "radial-gradient(ellipse at 40% 40%, rgba(0,0,0,0) 45%, rgba(0,0,0,.55) 100%)" }} />
    </div>
    <div style={{ position: "absolute", right: 0, top: 0, width: 700, height: H, overflow: "hidden", clipPath: "polygon(16% 0, 100% 0, 100% 100%, 0 100%)", background: "#EDEDED" }}>
      <Photo src={now} pos="55% 45%" scale={1.05} filter="contrast(1.05) saturate(1.1)" />
    </div>
    <svg width={W} height={H} style={{ position: "absolute", inset: 0 }}><line x1={700} y1={-10} x2={588} y2={730} stroke={D.cream} strokeWidth={14} /></svg>
    <div style={{ position: "absolute", left: 40, top: 34 }}><Tag rotate={-3}><div style={{ fontFamily: D.mono, fontWeight: 700, fontSize: 44, letterSpacing: 4, color: D.ox }}>1976</div></Tag></div>
    <div style={{ position: "absolute", right: 150, top: 34 }}><Tag rotate={3}><div style={{ fontFamily: D.mono, fontWeight: 700, fontSize: 44, letterSpacing: 4, color: D.ox }}>2026</div></Tag></div>
    <div style={{ position: "absolute", left: 0, right: 0, bottom: 44, textAlign: "center" }}>
      <Box size={118} rotate={-2}>GARAGE → $3.7T</Box>
    </div>
  </AbsoluteFill>
);

/** 4. Досье: два отпечатка на столе, красная нить, штамп — продолжение стиля самого видео. */
const Dossier: React.FC<ThumbVProps> = ({ jobs, woz }) => {
  const Print: React.FC<{ src: string; x: number; y: number; w: number; h: number; r: number; pos: string; label: string }> = ({ src, x, y, w, h, r, pos, label }) => (
    <div style={{ position: "absolute", left: x, top: y, width: w, transform: `rotate(${r}deg)`, background: D.photo, padding: "14px 14px 54px", boxShadow: "0 26px 60px rgba(0,0,0,.6)" }}>
      <div style={{ position: "relative", width: w - 28, height: h, overflow: "hidden" }}><Photo src={src} pos={pos} filter="grayscale(0.2) sepia(0.2) contrast(1.05)" /></div>
      <div style={{ position: "absolute", left: 18, bottom: 12, fontFamily: D.mono, fontWeight: 700, fontSize: 26, letterSpacing: 2, color: D.brown }}>{label}</div>
    </div>
  );
  return (
    <AbsoluteFill style={{ background: `radial-gradient(ellipse at 50% 40%, #3A2C22 0%, ${D.dark} 75%)` }}>
      <Print src={jobs} x={40} y={70} w={330} h={400} r={-6} pos="50% 30%" label="JOBS, 21" />
      <Print src={woz} x={330} y={150} w={380} h={330} r={4} pos="62% 35%" label="WOZ, 26" />
      <svg width={W} height={H} style={{ position: "absolute", inset: 0 }}>
        <path d="M200 95 C 320 40, 420 120, 520 175" stroke="#B3261E" strokeWidth={5} fill="none" />
        <circle cx={200} cy={95} r={11} fill="#B3261E" /><circle cx={520} cy={175} r={11} fill="#B3261E" />
      </svg>
      <div style={{ position: "absolute", left: 760, top: 64, width: 490 }}>
        <Tag rotate={-2}><div style={{ fontFamily: D.mono, fontWeight: 700, fontSize: 32, letterSpacing: 4, color: D.ox }}>CASE FILE: APPLE</div></Tag>
        <div style={{ fontFamily: D.serif, fontWeight: 700, fontSize: 80, lineHeight: 1.05, color: D.cream, marginTop: 30, whiteSpace: "nowrap", textShadow: "0 6px 20px rgba(0,0,0,.6)" }}>Two Steves.<br />One Garage.</div>
      </div>
      <div style={{ position: "absolute", left: 800, top: 430, width: 270, height: 150, border: `10px solid #B3261E`, borderRadius: 18, transform: "rotate(-9deg)",
        display: "flex", alignItems: "center", justifyContent: "center", fontFamily: anton.fontFamily, fontSize: 104, color: "#C8352B", background: "rgba(239,230,210,.06)" }}>$3.7T</div>
    </AbsoluteFill>
  );
};

/** 5. Крупное лицо + крючок-вопрос: «HE STARTED WITH $1,300». */
const Face: React.FC<ThumbVProps> = ({ bw }) => (
  <AbsoluteFill style={{ background: D.dark }}>
    <div style={{ position: "absolute", right: 0, top: 0, width: 760, height: H, overflow: "hidden" }}>
      <Photo src={bw} pos="66% 16%" scale={2.1} filter="grayscale(1) contrast(1.2) brightness(1.05)" />
    </div>
    <AbsoluteFill style={{ background: "linear-gradient(270deg, rgba(27,21,17,0) 40%, rgba(27,21,17,.9) 58%, #1B1511 66%)" }} />
    <Vignette a={0.4} />
    <div style={{ position: "absolute", left: 50, top: 120, width: 560 }}>
      <Big size={112}>THEY STARTED WITH</Big>
      <div style={{ marginTop: 18 }}><Box size={170} rotate={-3}>$1,300</Box></div>
    </div>
  </AbsoluteFill>
);

/** 6. «Бренд» (владелец 17.09, по каналам-референсам): состаренная бумага, логотип эпохи, вырезанные по контуру основатели и продукт,
 *  цифра-крючок из варианта 5. layout задаёт композицию: duo (оба слева), solo (герой справа), product (продукт крупно), color (цветное фото).
 *  Логотип берётся эпохи ролика (1977 у Apple), а не нынешний — история читается с первого взгляда. */
const Paper: React.FC<{ paper?: string; bw: string; dim?: number }> = ({ paper, bw, dim = 1 }) => (
  <>
    <AbsoluteFill style={{ background: "linear-gradient(160deg, #E9DBBC 0%, #D8C49B 45%, #B99B6E 100%)" }} />
    <Img src={staticFile(paper || bw)} style={{ position: "absolute", width: "100%", height: "100%", objectFit: "cover", opacity: 0.3, filter: "sepia(1) contrast(0.85) brightness(1.05)", mixBlendMode: "multiply" }} />
    <AbsoluteFill style={{ background: `radial-gradient(ellipse at 50% 45%, rgba(255,245,220,.22) 0%, rgba(60,40,20,${0.3 * dim}) 55%, rgba(28,17,8,${0.85 * dim}) 100%)` }} />
    <Img src={grain} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", opacity: 0.22, mixBlendMode: "multiply" }} />
  </>
);
const SEPIA = "grayscale(0.25) sepia(0.35) contrast(1.08) drop-shadow(0 20px 30px rgba(40,25,10,.6))";
const Logo: React.FC<{ logo?: string; wordmark?: string; side?: "left" | "right"; size?: number }> = ({ logo, wordmark, side = "right", size = 186 }) => (
  <div style={{ position: "absolute", [side]: 44, top: 30, display: "flex", alignItems: "center", gap: 26 }}>
    {logo && <Img src={staticFile(logo)} style={{ height: size, filter: "drop-shadow(0 12px 20px rgba(40,25,10,.55))" }} />}
    {wordmark && <Img src={staticFile(wordmark)} style={{ height: size * 0.34, filter: "drop-shadow(0 8px 14px rgba(40,25,10,.5))" }} />}
  </div>
);
const Hook: React.FC<{ hook: string; label?: string; side?: "left" | "right" }> = ({ hook, label, side = "left" }) => (
  // подпись — на кремовой плашке: на тёмной одежде и на плате текст с тенью терялся
  <div style={{ position: "absolute", [side]: 38, bottom: 34, display: "flex", flexDirection: "column", alignItems: side === "right" ? "flex-end" : "flex-start", gap: 10 }}>
    <Box size={110} rotate={-2}>{hook}</Box>
    {label && (
      <span style={{ display: "inline-block", background: "#F2E7CE", color: "#2E2113", fontFamily: anton.fontFamily, fontSize: 44, letterSpacing: 2, textTransform: "uppercase",
        padding: "2px 16px 6px", transform: "rotate(-2deg)", boxShadow: "0 10px 22px rgba(30,18,8,.45)" }}>{label}</span>
    )}
  </div>
);
const Stamp: React.FC<{ text: string }> = ({ text }) => (
  <div style={{ position: "absolute", right: 54, bottom: 40, border: "8px solid #B3261E", color: "#B3261E", borderRadius: 14, padding: "6px 22px 10px",
    transform: "rotate(-9deg)", fontFamily: anton.fontFamily, fontSize: 76, letterSpacing: 4, opacity: 0.85 }}>{text}</div>
);

const Brand: React.FC<ThumbVProps> = (p) => {
  const { layout = "duo", cut, product, logo, wordmark, paper, bw, hook = "$1,300", hookLabel = "TO $3.7 TRILLION", stamp } = p;
  if (layout === "solo") return (
    <AbsoluteFill>
      <Paper paper={paper} bw={bw} />
      {product && <Img src={staticFile(product)} style={{ position: "absolute", left: 18, bottom: 86, width: 560, filter: "drop-shadow(0 18px 26px rgba(40,25,10,.55))" }} />}
      {cut && <Img src={staticFile(cut)} style={{ position: "absolute", right: -30, bottom: 0, height: 730, filter: SEPIA }} />}
      <Logo logo={logo} wordmark={wordmark} side="left" size={168} />
      <Hook hook={hook} label={hookLabel} side="left" />
    </AbsoluteFill>
  );
  if (layout === "product") return (
    <AbsoluteFill>
      <Paper paper={paper} bw={bw} dim={1.1} />
      {product && <Img src={staticFile(product)} style={{ position: "absolute", left: "50%", top: "52%", width: 940, transform: "translate(-50%,-50%) rotate(-3deg)", filter: "drop-shadow(0 26px 40px rgba(30,18,8,.7))" }} />}
      {cut && <Img src={staticFile(cut)} style={{ position: "absolute", left: -60, bottom: 0, height: 470, opacity: 0.95, filter: SEPIA }} />}
      <Logo logo={logo} wordmark={wordmark} side="right" size={150} />
      <Hook hook={hook} label={hookLabel} side="left" />
      {stamp && <Stamp text={stamp} />}
    </AbsoluteFill>
  );
  if (layout === "color") return (
    <AbsoluteFill>
      <Paper paper={paper} bw={bw} />
      {cut && <Img src={staticFile(cut)} style={{ position: "absolute", left: 40, bottom: 0, height: 700, filter: "contrast(1.05) saturate(1.05) drop-shadow(0 20px 30px rgba(40,25,10,.6))" }} />}
      <Logo logo={logo} wordmark={wordmark} side="right" size={176} />
      <Hook hook={hook} label={hookLabel} side="left" />
      {stamp && <Stamp text={stamp} />}
    </AbsoluteFill>
  );
  return (
    <AbsoluteFill>
      <Paper paper={paper} bw={bw} />
      {product && <Img src={staticFile(product)} style={{ position: "absolute", right: 8, bottom: 96, width: 620, filter: "drop-shadow(0 18px 26px rgba(40,25,10,.55))" }} />}
      {cut && <Img src={staticFile(cut)} style={{ position: "absolute", left: -40, bottom: 0, height: 700, filter: SEPIA }} />}
      <Logo logo={logo} wordmark={wordmark} />
      <Hook hook={hook} label={hookLabel} />
      {stamp && <Stamp text={stamp} />}
    </AbsoluteFill>
  );
};

/** 7. Вариант 5 («THEY STARTED WITH $1,300») + логотип: владельцу нравится этот макет, но без логотипа ролик не узнаётся.
 *  logoPos: tr — угол справа сверху; bl — рядом с текстом; wm — крупный полупрозрачный знак за лицом; word — вордмарк под текстом;
 *  prod — знак сверху и плата Apple I снизу. */
const FaceLogo: React.FC<ThumbVProps> = ({ bw, logo, wordmark, product, logoPos = "tr", portraitFit, hook = "$1,300", hookLabel = "THEY STARTED WITH" }) => (
  <AbsoluteFill style={{ background: D.dark }}>
    <div style={{ position: "absolute", right: 0, top: 0, width: 760, height: H, overflow: "hidden" }}>
      <Photo src={bw} pos={portraitFit ? "52% 22%" : "66% 16%"} scale={portraitFit ? 1.12 : 2.1} filter="grayscale(1) contrast(1.2) brightness(1.05)" />
    </div>
    <AbsoluteFill style={{ background: "linear-gradient(270deg, rgba(27,21,17,0) 40%, rgba(27,21,17,.9) 58%, #1B1511 66%)" }} />
    {logoPos === "wm" && logo && (
      <Img src={staticFile(logo)} style={{ position: "absolute", right: -70, bottom: -60, height: 640, opacity: 0.2, filter: "saturate(1.15)" }} />
    )}
    <Vignette a={0.4} />
    <div style={{ position: "absolute", left: 50, top: logoPos === "prod" ? 60 : 120, width: 620 }}>
      <Big size={logoPos === "word" ? 98 : 112}>{hookLabel}</Big>
      <div style={{ marginTop: 18, display: "flex", alignItems: "center", gap: 22 }}>
        <Box size={170} rotate={-3}>{hook}</Box>
        {logoPos === "bl" && logo && <Img src={staticFile(logo)} style={{ height: 150, filter: "drop-shadow(0 10px 24px rgba(0,0,0,.6))" }} />}
      </div>
      {logoPos === "word" && wordmark && <Img src={staticFile(wordmark)} style={{ marginTop: 22, height: 58, filter: "drop-shadow(0 8px 18px rgba(0,0,0,.6))" }} />}
    </div>
    {(logoPos === "tr" || logoPos === "prod") && logo && (
      <Img src={staticFile(logo)} style={{ position: "absolute", right: 44, top: 32, height: logoPos === "prod" ? 150 : 190, filter: "drop-shadow(0 12px 26px rgba(0,0,0,.65))" }} />
    )}
    {logoPos === "prod" && product && (
      <Img src={staticFile(product)} style={{ position: "absolute", left: 24, bottom: 18, width: 430, filter: "drop-shadow(0 16px 30px rgba(0,0,0,.7))" }} />
    )}
  </AbsoluteFill>
);

/** 8. Набор разных концепций (владелец 17.09: «отойти от формата, много вариантов, сгенерированные и нет»).
 *  kind: cinema — кинокадр с одной строкой; poster — плакат с крупным знаком; minimal — только цифра;
 *  mag — обложка журнала эпохи; split2 — «тогда/сейчас» по диагонали; quote — вопрос вместо утверждения. */
const Kit: React.FC<ThumbVProps> = (p) => {
  const { kind = "cinema", bg, bw, now, logo, wordmark, product, hook = "$666", hookLabel = "THE COMPUTER THAT STARTED IT", stamp } = p;
  const Shade = ({ a = 0.55, dir = "180deg" }: { a?: number; dir?: string }) =>
    <AbsoluteFill style={{ background: `linear-gradient(${dir}, rgba(10,7,4,${a}) 0%, rgba(10,7,4,.12) 45%, rgba(10,7,4,${a}) 100%)` }} />;
  if (kind === "poster") return (
    <AbsoluteFill style={{ background: "#0E0B08" }}>
      {bg && <Photo src={bg} pos="50% 50%" scale={1.05} filter="brightness(0.55) contrast(1.1) saturate(0.8)" />}
      <AbsoluteFill style={{ background: "radial-gradient(ellipse at 70% 45%, rgba(0,0,0,0) 30%, rgba(8,5,3,.9) 100%)" }} />
      {logo && <Img src={staticFile(logo)} style={{ position: "absolute", left: 74, top: 96, height: 380, filter: "drop-shadow(0 20px 40px rgba(0,0,0,.8))" }} />}
      <div style={{ position: "absolute", right: 60, top: 150, width: 640, textAlign: "right" }}>
        <Big size={150} color={D.cream}>{hook}</Big>
        <div style={{ marginTop: 16, fontFamily: anton.fontFamily, fontSize: 54, lineHeight: 1.06, textTransform: "uppercase", color: "#E7D9BC", textShadow: OUT }}>{hookLabel}</div>
      </div>
    </AbsoluteFill>
  );
  if (kind === "minimal") return (
    <AbsoluteFill style={{ background: "linear-gradient(140deg, #14100C 0%, #221A13 60%, #100C08 100%)" }}>
      {logo && <Img src={staticFile(logo)} style={{ position: "absolute", right: 70, top: "50%", height: 460, marginTop: -230, opacity: 0.9, filter: "drop-shadow(0 18px 40px rgba(0,0,0,.7))" }} />}
      <div style={{ position: "absolute", left: 78, top: 168, width: 660 }}>
        <div style={{ fontFamily: anton.fontFamily, fontSize: 210, lineHeight: 0.92, color: D.cream, textShadow: OUT }}>{hook}</div>
        <div style={{ marginTop: 22, fontFamily: anton.fontFamily, fontSize: 56, lineHeight: 1.05, textTransform: "uppercase", color: "#C9B189", letterSpacing: 1 }}>{hookLabel}</div>
      </div>
    </AbsoluteFill>
  );
  if (kind === "mag") return (
    <AbsoluteFill style={{ background: "#D9C7A2" }}>
      {bg && <Photo src={bg} pos="50% 45%" scale={1.02} filter="sepia(0.45) contrast(1.05) saturate(0.85)" />}
      <AbsoluteFill style={{ background: "linear-gradient(180deg, rgba(20,12,6,.55) 0%, rgba(20,12,6,0) 35%, rgba(20,12,6,.6) 100%)" }} />
      <div style={{ position: "absolute", left: 0, right: 0, top: 26, textAlign: "center", fontFamily: D.serif, fontWeight: 700, fontSize: 96, letterSpacing: 10, color: "#F3E7CB", textShadow: "0 6px 22px rgba(0,0,0,.7)" }}>
        THE GARAGE ISSUE
      </div>
      <div style={{ position: "absolute", left: 44, bottom: 40 }}><Box size={120} rotate={-2}>{hook}</Box></div>
      <div style={{ position: "absolute", right: 44, bottom: 52, width: 430, textAlign: "right", fontFamily: D.serif, fontWeight: 700, fontSize: 52, lineHeight: 1.1, color: "#F6ECD6", textShadow: "0 4px 18px rgba(0,0,0,.8)" }}>{hookLabel}</div>
      {logo && <Img src={staticFile(logo)} style={{ position: "absolute", left: 46, top: 150, height: 150, filter: "drop-shadow(0 12px 26px rgba(0,0,0,.6))" }} />}
    </AbsoluteFill>
  );
  if (kind === "split2") return (
    <AbsoluteFill style={{ background: "#0E0B08" }}>
      <div style={{ position: "absolute", inset: 0, clipPath: "polygon(0 0, 58% 0, 42% 100%, 0 100%)", overflow: "hidden" }}>
        <Photo src={bw} pos="50% 20%" scale={1.3} filter="grayscale(1) sepia(0.3) contrast(1.15) brightness(0.95)" />
      </div>
      <div style={{ position: "absolute", inset: 0, clipPath: "polygon(58% 0, 100% 0, 100% 100%, 42% 100%)", overflow: "hidden" }}>
        <Photo src={now} pos="50% 50%" scale={1.06} filter="contrast(1.06) saturate(1.05)" />
      </div>
      <svg width={W} height={H} style={{ position: "absolute", inset: 0 }}><line x1={742} y1={-10} x2={538} y2={730} stroke={D.cream} strokeWidth={10} /></svg>
      <div style={{ position: "absolute", left: 46, bottom: 44 }}><Box size={128} rotate={-2}>1976</Box></div>
      <div style={{ position: "absolute", right: 46, bottom: 44 }}><Box size={128} rotate={2}>2026</Box></div>
      {logo && <Img src={staticFile(logo)} style={{ position: "absolute", left: "50%", top: 34, height: 170, marginLeft: -85, filter: "drop-shadow(0 14px 30px rgba(0,0,0,.75))" }} />}
    </AbsoluteFill>
  );
  if (kind === "quote") return (
    <AbsoluteFill style={{ background: "#0E0B08" }}>
      {bg && <Photo src={bg} pos="60% 45%" scale={1.08} filter="brightness(0.6) contrast(1.12) saturate(0.85)" />}
      <Shade a={0.62} />
      <div style={{ position: "absolute", left: 70, top: 130, width: 760 }}>
        <div style={{ fontFamily: D.serif, fontWeight: 700, fontSize: 104, lineHeight: 1.06, color: "#F4E9CF", textShadow: "0 8px 28px rgba(0,0,0,.85)" }}>{hookLabel}</div>
        <div style={{ marginTop: 26 }}><Box size={128} rotate={-2}>{hook}</Box></div>
      </div>
      {logo && <Img src={staticFile(logo)} style={{ position: "absolute", right: 56, top: 40, height: 168, filter: "drop-shadow(0 14px 30px rgba(0,0,0,.8))" }} />}
      {stamp && <Stamp text={stamp} />}
    </AbsoluteFill>
  );
  return (   // cinema
    <AbsoluteFill style={{ background: "#0E0B08" }}>
      {bg && <Photo src={bg} pos="50% 50%" scale={1.04} filter="contrast(1.08) saturate(0.95)" />}
      <Shade a={0.6} />
      {product && <Img src={staticFile(product)} style={{ position: "absolute", right: 26, bottom: 40, width: 520, filter: "drop-shadow(0 20px 34px rgba(0,0,0,.8))" }} />}
      <div style={{ position: "absolute", left: 60, bottom: 54, width: 700 }}>
        <Big size={122}>{hookLabel}</Big>
        <div style={{ marginTop: 16 }}><Box size={140} rotate={-2}>{hook}</Box></div>
      </div>
      {logo && <Img src={staticFile(logo)} style={{ position: "absolute", right: 52, top: 36, height: 168, filter: "drop-shadow(0 14px 30px rgba(0,0,0,.8))" }} />}
    </AbsoluteFill>
  );
};

/** 9. По присланным владельцем референсам (17.09): тёплый сепийный фон, вырезанный портрет, продукт рядом, крупное «Apple» с логотипом.
 *  ref1 — как первый референс: кинематографичный портрет во весь кадр, крупная надпись и радужный знак;
 *  ref2 — как второй: пергамент, вырезанный портрет слева, гараж и Macintosh справа, чёрный знак и слово Apple сверху. */
/** Знак Amazon рисуем кодом: на Wikimedia Commons чистого логотипа нет (нефри лицензия), а кадры с вывесками для обложки не годятся.
 *  Слово + стрелка-улыбка от «a» к «z» — узнаётся мгновенно и не зависит от чужого файла. */
const AmzMark: React.FC<{ size?: number; color?: string }> = ({ size = 128, color = "#1D1409" }) => (
  <div style={{ position: "relative", paddingBottom: size * 0.34 }}>
    <div style={{ fontFamily: D.serif, fontWeight: 700, fontSize: size, lineHeight: 1, color, letterSpacing: -size * 0.02, textShadow: "0 3px 0 rgba(255,246,222,.55)" }}>amazon</div>
    <svg width={size * 3.05} height={size * 0.42} viewBox="0 0 305 42" style={{ position: "absolute", left: size * 0.12, bottom: 0 }}>
      <path d="M6 8 C70 40, 215 40, 286 10" fill="none" stroke="#E8912A" strokeWidth={12} strokeLinecap="round" />
      <path d="M268 2 L296 8 L272 26 Z" fill="#E8912A" />
    </svg>
  </div>
);

// Знак Microsoft кодом: четыре квадрата в фирменных цветах + слово. Яркое пятно на пергаменте — у сильных каналов ниши логотип
// крупный и цветной, а тусклый коричневый знак на коричневом фоне терялся в ленте (сравнение с Tech District 19.09).
const MsMark: React.FC<{ size?: number; color?: string }> = ({ size = 124, color = "#1D1409" }) => {
  const q = size * 0.43, g = size * 0.05;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: size * 0.2 }}>
      <div style={{ display: "grid", gridTemplateColumns: `${q}px ${q}px`, gap: g, filter: "drop-shadow(0 8px 14px rgba(40,25,10,.45))" }}>
        {["#F25022", "#7FBA00", "#00A4EF", "#FFB900"].map((c) => <div key={c} style={{ width: q, height: q, background: c }} />)}
      </div>
      <div style={{ fontFamily: "'Segoe UI', 'Helvetica Neue', Arial, sans-serif", fontWeight: 600, fontSize: size * 0.82, lineHeight: 1, color,
        letterSpacing: -size * 0.01, textShadow: "0 3px 0 rgba(255,246,222,.55)" }}>Microsoft</div>
    </div>
  );
};

/** Знак Google: четырёхцветное кольцо «G» с перекладиной — читается в ленте лучше, чем слово. */
const GoogleMark: React.FC<{ size?: number; color?: string }> = ({ size = 120, color = "#FFFFFF" }) => {
  const R = 34, SW = 22, C = 50;                                   // радиус кольца, толщина, центр в системе 100×100
  const pt = (deg: number) => [C + R * Math.cos((deg * Math.PI) / 180), C - R * Math.sin((deg * Math.PI) / 180)];
  const arc = (a: number, b: number) => {                          // дуга строго против часовой стрелки от a до b (b > a)
    const [x1, y1] = pt(a), [x2, y2] = pt(b);
    return `M ${x1} ${y1} A ${R} ${R} 0 ${b - a > 180 ? 1 : 0} 0 ${x2} ${y2}`;
  };
  return (
    <div style={{ display: "flex", alignItems: "center", gap: size * 0.22 }}>
      <svg width={size} height={size} viewBox="0 0 100 100" style={{ filter: "drop-shadow(0 8px 14px rgba(0,0,0,.5))" }}>
        <path d={arc(18, 118)} stroke="#EA4335" strokeWidth={SW} strokeLinecap="butt" fill="none" />
        <path d={arc(118, 196)} stroke="#FBBC04" strokeWidth={SW} strokeLinecap="butt" fill="none" />
        <path d={arc(196, 286)} stroke="#34A853" strokeWidth={SW} strokeLinecap="butt" fill="none" />
        <path d={arc(286, 350)} stroke="#4285F4" strokeWidth={SW} strokeLinecap="butt" fill="none" />
        <rect x={C - 4} y={C - SW / 2} width={R + 18} height={SW} fill="#4285F4" />
      </svg>
      <div style={{ fontFamily: "'Segoe UI', 'Helvetica Neue', Arial, sans-serif", fontWeight: 600, fontSize: size * 0.8, lineHeight: 1, color,
        letterSpacing: -size * 0.015, textShadow: "0 3px 10px rgba(0,0,0,.45)" }}>Google</div>
    </div>
  );
};

const Ref: React.FC<ThumbVProps> = (p) => {
  const { kind = "ref1", bg, cut, cutH = 690, cutX = -20, cutSepia = 0, product, logo, logoBlack, mark, title = "THE STORY OF", brandWord = "APPLE", hook, hookLabel } = p;
  // ref2: владелец 17.09 — «в стиле второй, но получше расположить элементы и без большого пустого места».
  // Пустоту давали мелкая фигура по центру и воздух сверху: теперь фигура во весь левый край, справа колонка
  // «знак → слово → подзаголовок → продукт» сверху донизу, сверху слева — бирка досье, снизу — цена поверх фигуры.
  // ref3: настоящий архивный снимок во весь кадр, надпись сверху, цифра снизу слева — текст не ложится на людей,
  // как это выходило в ref1 с фотографией, где герои стоят справа (Amazon 18.09).
  if (kind === "ref3") return (
    <AbsoluteFill style={{ background: "#0E0B08" }}>
      {bg && <Photo src={bg} pos="50% 52%" scale={1.04} filter="contrast(1.12) saturate(1.06) brightness(1.02)" />}
      <AbsoluteFill style={{ background: "linear-gradient(180deg, rgba(8,6,4,.88) 0%, rgba(8,6,4,.55) 26%, rgba(8,6,4,0) 46%, rgba(8,6,4,.35) 78%, rgba(8,6,4,.8) 100%)" }} />
      <div style={{ position: "absolute", left: 0, right: 0, top: 18, display: "flex", flexDirection: "column", alignItems: "center" }}>
        {title && <div style={{ fontFamily: anton.fontFamily, fontSize: 54, letterSpacing: 5, textTransform: "uppercase", color: "#F3E7CB", textShadow: OUT }}>{title}</div>}
        {mark === "amazon"
          ? <div style={{ filter: "drop-shadow(0 10px 22px rgba(0,0,0,.9))", marginTop: -2 }}><AmzMark size={132} color="#FFFFFF" /></div>
          : <div style={{ fontFamily: anton.fontFamily, fontSize: 150, lineHeight: 0.95, textTransform: "uppercase", color: "#FFFFFF", textShadow: OUT }}>{brandWord}</div>}
      </div>
      {hook && <div style={{ position: "absolute", left: 38, bottom: 30 }}><Box size={122} rotate={-3}>{hook}</Box></div>}
      {hookLabel && (
        <div style={{ position: "absolute", right: 38, bottom: 42, background: "#F2E7CE", color: "#2E2113", fontFamily: D.mono, fontWeight: 700,
          fontSize: 30, letterSpacing: 4, textTransform: "uppercase", padding: "7px 18px 9px", transform: "rotate(-1.5deg)", boxShadow: "0 12px 24px rgba(30,18,8,.55)" }}>{hookLabel}</div>
      )}
    </AbsoluteFill>
  );
  if (kind === "ref2") return (
    <AbsoluteFill style={{ background: "linear-gradient(150deg, #EADCBB 0%, #D9C297 50%, #B08F62 100%)" }}>
      {bg && <Img src={staticFile(bg)} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", objectPosition: "38% 60%",
        transform: "scale(1.22)", transformOrigin: "38% 60%", opacity: 0.6, filter: "sepia(0.7) contrast(0.98)", mixBlendMode: "multiply" }} />}
      <Img src={grain} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", opacity: 0.25, mixBlendMode: "multiply" }} />
      <AbsoluteFill style={{ background: "radial-gradient(ellipse at 38% 55%, rgba(255,244,214,.34) 0%, rgba(70,45,20,.22) 55%, rgba(30,19,8,.82) 100%)" }} />
      {/* cutH/cutX — под конкретную вырезку: одиночная фигура узкая (её сдвигаем правее, иначе бирка ложится на голову), групповая широкая */}
      {cut && <Img src={staticFile(cut)} style={{ position: "absolute", left: cutX, bottom: 0, height: cutH, filter: `contrast(1.06) sepia(${cutSepia}) saturate(${1 - cutSepia * 0.45}) drop-shadow(0 24px 38px rgba(40,25,10,.75))` }} />}
      <div style={{ position: "absolute", right: 30, top: 22, bottom: 22, width: 596, display: "flex", flexDirection: "column", alignItems: "flex-end", justifyContent: "space-between" }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            {mark === "amazon" ? <AmzMark size={124} /> : mark === "microsoft" ? <MsMark size={118} /> : (<>
              {logoBlack && <Img src={staticFile(logoBlack)} style={{ height: 112, filter: "drop-shadow(0 10px 18px rgba(40,25,10,.55))" }} />}
              <div style={{ fontFamily: D.serif, fontWeight: 700, fontSize: 132, lineHeight: 1, color: "#1D1409", textShadow: "0 3px 0 rgba(255,246,222,.55)" }}>{brandWord}</div>
            </>)}
          </div>
          <div style={{ width: 540, height: 3, background: "#3A2714", opacity: 0.5, marginTop: 4 }} />
        </div>
        {product && <Img src={staticFile(product)} style={{ width: 470, margin: "6px 0", filter: "drop-shadow(0 22px 34px rgba(40,25,10,.7))" }} />}
        {hookLabel && (
          // на кремовой плашке: коричневый текст поверх пергамента и продукта не читался
          <span style={{ background: "#F2E7CE", color: "#2E2113", fontFamily: D.mono, fontWeight: 700, fontSize: 30, letterSpacing: 4, textTransform: "uppercase",
            padding: "7px 18px 9px", transform: "rotate(-1.5deg)", boxShadow: "0 12px 24px rgba(30,18,8,.5)" }}>{hookLabel}</span>
        )}
      </div>
      {title && (
        <div style={{ position: "absolute", left: 30, top: 28, background: "#F2E7CE", color: "#2E2113", fontFamily: D.mono, fontWeight: 700, fontSize: 30,
          letterSpacing: 4, padding: "7px 18px 9px", transform: "rotate(-2deg)", boxShadow: "0 12px 24px rgba(30,18,8,.5)", textTransform: "uppercase" }}>{title}</div>
      )}
      {hook && <div style={{ position: "absolute", left: 34, bottom: 26 }}><Box size={122} rotate={-3}>{hook}</Box></div>}
    </AbsoluteFill>
  );
  return (
    <AbsoluteFill style={{ background: "#120D08" }}>
      {bg && <Photo src={bg} pos="42% 45%" scale={1.06} filter="contrast(1.06) saturate(1.02)" />}
      <AbsoluteFill style={{ background: "linear-gradient(90deg, rgba(10,7,4,.25) 0%, rgba(10,7,4,0) 35%, rgba(10,7,4,.55) 72%, rgba(10,7,4,.8) 100%)" }} />
      <div style={{ position: "absolute", right: 46, top: 46, width: 560, textAlign: "right" }}>
        <div style={{ fontFamily: anton.fontFamily, fontSize: 64, letterSpacing: 4, textTransform: "uppercase", color: "#F3E7CB", textShadow: OUT }}>{title}</div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 20, marginTop: 6 }}>
          {mark === "amazon"
            ? <div style={{ filter: "drop-shadow(0 10px 22px rgba(0,0,0,.85))" }}><AmzMark size={150} color="#FFFFFF" /></div>
            : <div style={{ fontFamily: anton.fontFamily, fontSize: 168, lineHeight: 0.95, textTransform: "uppercase", color: "#FFFFFF", textShadow: OUT }}>{brandWord}</div>}
          {logo && <Img src={staticFile(logo)} style={{ height: 172, filter: "drop-shadow(0 14px 26px rgba(0,0,0,.75))" }} />}
        </div>
        {hookLabel && <div style={{ marginTop: 14, fontFamily: D.mono, fontWeight: 700, fontSize: 34, letterSpacing: 3, color: "#D8C49B" }}>{hookLabel}</div>}
      </div>
      {hook && <div style={{ position: "absolute", left: 44, bottom: 36 }}><Box size={118} rotate={-2}>{hook}</Box></div>}
    </AbsoluteFill>
  );
};

/** Смелые макеты (владелец 19.09: «совершенно новые варианты, чтобы прям хотелось кликнуть, но не кликбейт»): одна загадка, на которую
 *  отвечает ролик, настоящее лицо из архива (вырезка, не генерация), 2–4 слова, контраст «было → стало», яркие акценты вместо пергамента.
 *  Правый нижний угол свободен — там YouTube рисует длительность. */
const YEL = "#FFD21F", RED = "#E3262B";
const Arrow: React.FC<{ w?: number; color?: string }> = ({ w = 150, color = "#FFFFFF" }) => (
  <svg width={w} height={w * 0.6} viewBox="0 0 150 90" style={{ filter: "drop-shadow(0 6px 10px rgba(0,0,0,.7))" }}>
    <path d="M8 45 H118 M90 14 L128 45 L90 76" stroke={color} strokeWidth={16} fill="none" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
const Pill: React.FC<{ children: React.ReactNode; style?: React.CSSProperties }> = ({ children, style }) => (
  <div style={{ background: "rgba(10,10,12,.72)", borderRadius: 14, padding: "12px 20px", ...style }}>{children}</div>
);
const MonoTag: React.FC<{ children: React.ReactNode; rotate?: number; size?: number }> = ({ children, rotate = -2, size = 38 }) => (
  <Tag rotate={rotate}><div style={{ fontFamily: D.mono, fontWeight: 700, fontSize: size, letterSpacing: 4, color: D.ox, textTransform: "uppercase" }}>{children}</div></Tag>
);
/** Знак Microsoft, расколотый пополам: суд 2000 года постановил разделить компанию на две. */
const Cracked: React.FC<{ size?: number }> = ({ size = 170 }) => {
  const sq = (c: string) => <div style={{ width: size, height: size, background: c }} />;
  const col = (a: string, b: string, t: string) => (
    <div style={{ display: "flex", flexDirection: "column", gap: size * 0.08, transform: t, filter: "drop-shadow(0 18px 30px rgba(0,0,0,.7))" }}>{sq(a)}{sq(b)}</div>
  );
  return <div style={{ display: "flex", gap: size * 0.34 }}>{col("#F25022", "#00A4EF", "translate(-6px,-14px) rotate(-6deg)")}{col("#7FBA00", "#FFB900", "translate(6px,16px) rotate(6deg)")}</div>;
};

/** Знак канала-бренда в смелых макетах: Microsoft — плашки, Amazon — слово со стрелкой, иначе логотип из архива ролика. */
/** Знак Netflix: красная надпись с фирменной дугой по нижнему краю (буквы по краям выше, в центре ниже). */
const NetflixMark: React.FC<{ size?: number }> = ({ size = 86 }) => {
  const L = "NETFLIX".split(""); const mid = (L.length - 1) / 2;
  return (
    <div style={{ display: "flex", alignItems: "flex-start", filter: "drop-shadow(0 6px 12px rgba(0,0,0,.55))" }}>
      {L.map((ch, i) => {
        const k = Math.abs(i - mid) / mid;                       // 0 в центре, 1 по краям
        return <span key={i} style={{ fontFamily: bebas.fontFamily, fontSize: size * 1.25, lineHeight: 0.9, color: "#E50914", letterSpacing: size * 0.04,
          display: "inline-block", transformOrigin: "top center", transform: `scaleY(${1 + 0.16 * k * k})` }}>{ch}</span>;
      })}
    </div>
  );
};

/** Компания без своего знака: название шрифтом обложки (Anton), а не картинкой — чисто и в одном стиле с цифрами. */
const WordMark: React.FC<{ text: string; size?: number }> = ({ text, size = 64 }) => (
  <div style={{ fontFamily: anton.fontFamily, fontSize: size * 1.05, lineHeight: 1, letterSpacing: 3, color: "#FFFFFF", textTransform: "uppercase", textShadow: "0 4px 12px rgba(0,0,0,.5)" }}>{text}</div>
);

const BrandMark: React.FC<{ mark?: string; logo?: string; wordmark?: string; size?: number; brandWord?: string }> = ({ mark, logo, wordmark, size = 64, brandWord }) => {
  if (mark === "netflix") return <NetflixMark size={size} />;
  if (!mark && !logo && brandWord) return <WordMark text={brandWord} size={size} />;
  // фирменный знак + название рядом (владелец 22.09: «первую букву фирменной, дальше просто название»), как у Google
  if (!mark && logo && brandWord) return (
    <div style={{ display: "flex", alignItems: "center", gap: size * 0.22 }}>
      <Img src={staticFile(logo)} style={{ height: size * 1.15, filter: "drop-shadow(0 8px 14px rgba(0,0,0,.5))" }} />
      <div style={{ fontFamily: "'Segoe UI', 'Helvetica Neue', Arial, sans-serif", fontWeight: 700, fontSize: size * 0.78, lineHeight: 1, color: "#FFFFFF", letterSpacing: -size * 0.01, textShadow: "0 3px 10px rgba(0,0,0,.45)" }}>{brandWord}</div>
    </div>
  );
  if (mark === "microsoft") return <MsMark size={size} color="#FFFFFF" />;
  if (mark === "amazon") return <AmzMark size={size * 1.15} color="#FFFFFF" />;
  if (mark === "google") return <GoogleMark size={size * 1.05} color="#FFFFFF" />;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: size * 0.25 }}>
      {logo && <Img src={staticFile(logo)} style={{ height: size * 1.25, filter: "drop-shadow(0 8px 14px rgba(0,0,0,.5))" }} />}
      {wordmark && <Img src={staticFile(wordmark)} style={{ height: size * 0.72, filter: "brightness(0) invert(1) drop-shadow(0 8px 14px rgba(0,0,0,.5))" }} />}
    </div>
  );
};

/** Подача логотипа под компанию и тему ролика (владелец 26.09): pill / sign / stamp / badge / ghost. */
const Ink: React.FC<{ src: string; h: number; aspect?: number; color: string }> = ({ src, h, aspect = 2, color }) => (
  <div style={{ width: h * aspect, height: h, background: color, WebkitMaskImage: `url(${staticFile(src)})`, maskImage: `url(${staticFile(src)})`,
    WebkitMaskSize: "contain", maskSize: "contain", WebkitMaskRepeat: "no-repeat", maskRepeat: "no-repeat", WebkitMaskPosition: "center", maskPosition: "center" }} />
);
const LogoArt: React.FC<ThumbVProps> = (p) => {
  const { logoStyle = "pill", logo, brandWord, mark, wordmark, markSize } = p;
  const c = p.brandColor || "#B3261E", asp = p.logoAspect || 2;
  const word = (color: string, size: number) => brandWord ? <div style={{ fontFamily: anton.fontFamily, fontSize: size, lineHeight: 1, letterSpacing: 2, color, textTransform: "uppercase" }}>{brandWord}</div> : null;
  if (logoStyle === "sign") return (   // световой короб-вывеска: белая панель, знак в своих цветах, свечение
    <div style={{ position: "absolute", right: 60, top: 118, transform: "rotate(2deg)", background: "#FFFFFF", borderRadius: 18, padding: "18px 30px",
      display: "flex", alignItems: "center", gap: 18, boxShadow: `0 0 0 6px ${c}, 0 0 60px 12px rgba(255,244,214,.55), 0 18px 40px rgba(0,0,0,.7)` }}>
      {logo && <Img src={staticFile(logo)} style={{ height: Math.min(120, 380 / asp) }} />}
      {logo && brandWord && word("#111", 84)}
      {!logo && word(c, 72)}
    </div>
  );
  if (logoStyle === "stamp") return (   // печать: знак одним цветом бренда, двойная рамка, наклон
    <div style={{ position: "absolute", right: 64, bottom: 44, transform: "rotate(-7deg)", border: `8px double ${c}`, borderRadius: 16, padding: "14px 26px",
      display: "flex", alignItems: "center", gap: 16, background: "rgba(245,236,214,.9)", boxShadow: "0 16px 34px rgba(0,0,0,.65)" }}>
      {logo ? <Ink src={p.logoMask || logo} h={Math.min(100, 360 / asp)} aspect={asp} color={c} /> : null}
      {(!logo || brandWord) && word(c, logo ? 72 : 76)}
    </div>
  );
  if (logoStyle === "badge") return (   // плашка фирменного цвета, знак белым
    <div style={{ position: "absolute", left: 0, right: 0, top: 30, display: "flex", justifyContent: "center" }}>
      <div style={{ background: c, borderRadius: 16, padding: "14px 28px", display: "flex", alignItems: "center", gap: 16, boxShadow: "0 14px 30px rgba(0,0,0,.6)" }}>
        {logo && <Ink src={p.logoMask || logo} h={Math.min(78, 330 / asp)} aspect={asp} color="#FFFFFF" />}
        {word("#FFFFFF", logo ? 64 : 80)}
      </div>
    </div>
  );
  if (logoStyle === "ghost" && logo) return (   // крупный полупрозрачный символ за правой цифрой
    <Img src={staticFile(logo)} style={{ position: "absolute", right: 30, top: 150, height: 430, opacity: 0.28, filter: "saturate(1.2)" }} />
  );
  return <div style={{ position: "absolute", left: 0, right: 0, top: 30, display: "flex", justifyContent: "center" }}><Pill><BrandMark mark={mark} logo={logo} wordmark={wordmark} size={markSize ?? 52} brandWord={brandWord} /></Pill></div>;
};
const tagSize = (s?: string) => { const n = String(s || "").length; return n <= 8 ? 44 : Math.max(26, Math.floor(44 * 9 / n)); };

const Bold: React.FC<ThumbVProps> = (p) => {
  const { kind = "clause", bg, bg2, cut, product, text1, text2, hook, hook2, tagL, tagR, cutH = 700, cutX = 0, markSize, mark, logo, wordmark } = p;
  const full = (src?: string, filter?: string) => src ? <Img src={staticFile(src)} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", filter }} /> : null;
  const person = (src: string | undefined, style: React.CSSProperties, filter = "contrast(1.08) saturate(1.1)") =>
    src ? <Img src={staticFile(src)} style={{ position: "absolute", bottom: 0, filter: `${filter} drop-shadow(0 20px 40px rgba(0,0,0,.75))`, ...style }} /> : null;
  if (kind === "clause") return (
    <AbsoluteFill style={{ background: "#120D08" }}>
      {full(bg, "brightness(.85) contrast(1.1)")}
      <AbsoluteFill style={{ background: "linear-gradient(90deg, rgba(8,6,4,.88) 0%, rgba(8,6,4,.6) 42%, rgba(8,6,4,0) 72%)" }} />
      {person(cut, { right: cutX, height: cutH })}
      <div style={{ position: "absolute", left: 48, top: 56 }}>
        <Big size={112}>{text1}</Big>
        <Box size={116} rotate={-2} style={{ background: YEL, color: "#111", marginTop: 16 }}>{text2}</Box>
      </div>
      <div style={{ position: "absolute", left: 52, bottom: 46 }}><BrandMark mark={mark} logo={logo} wordmark={wordmark} size={markSize ?? 66} /></div>
    </AbsoluteFill>
  );
  if (kind === "face") {   // испанский канал: один человек, один образ компании, одно обещание (владелец 22.09)
    const NAVY = "#0B1B33", YL = "#FFD500";
    const gk = "'Space Grotesk', 'Segoe UI', Arial, sans-serif";
    const [w1, w2] = String(p.text1 ?? "").split("|");
    return (
      <AbsoluteFill style={{ background: NAVY }}>
        {full(bg, "saturate(1.1) contrast(1.05)")}
        <AbsoluteFill style={{ background: "linear-gradient(90deg, rgba(11,27,51,0) 40%, rgba(11,27,51,.55) 62%, rgba(11,27,51,.88) 100%)" }} />
        <AbsoluteFill style={{ background: "linear-gradient(180deg, rgba(11,27,51,.45) 0%, rgba(11,27,51,0) 30%)" }} />
        {person(cut, { left: cutX, height: cutH }, "contrast(1.08) saturate(1.05)")}
        {/* правый столбец: логотип (верх) · слова (середина) · цифра (низ) — с зазорами, лицо в него не заходит */}
        <div style={{ position: "absolute", right: 46, top: 40, background: "rgba(7,18,36,.85)", border: `3px solid ${YL}`, borderRadius: 14, padding: "10px 20px" }}>
          <BrandMark mark={mark} logo={logo} wordmark={wordmark} size={markSize ?? 48} brandWord={p.brandWord} />
        </div>
        <div style={{ position: "absolute", right: 46, top: 250, textAlign: "right" }}>
          {w1 && <div style={{ fontFamily: anton.fontFamily, fontSize: 118, lineHeight: 0.98, letterSpacing: 2, color: "#FFFFFF", textShadow: "0 6px 24px rgba(0,0,0,.6)" }}>{w1.trim()}</div>}
          {w2 && <div style={{ fontFamily: anton.fontFamily, fontSize: 118, lineHeight: 0.98, letterSpacing: 2, color: YL, textShadow: "0 6px 24px rgba(0,0,0,.6)" }}>{w2.trim()}</div>}
        </div>
        {hook2 && <div style={{ position: "absolute", right: 46, bottom: 44 }}>
          <Box size={150} rotate={0} style={{ background: YL, color: NAVY, borderRadius: 14, padding: "8px 26px 12px" }}>{hook2}</Box>
        </div>}
        <div style={{ position: "absolute", left: 40, bottom: 34, fontFamily: gk, fontWeight: 700, fontSize: 26, letterSpacing: 3, color: "rgba(255,255,255,.75)" }} />
      </AbsoluteFill>
    );
  }
  // ---- 26.09: варианты по исследованию ниши — компания узнаётся за секунду, не больше трёх элементов, одна мысль ----
  const panel = (h0: number, style: React.CSSProperties, maxW = 660) => { const h = Math.min(h0, maxW / (p.logoAspect || 1.5)); return logo ? (   // широкий знак (Costco) не должен закрывать сцену
    <div style={{ position: "absolute", background: "#FFFFFF", borderRadius: 22, padding: `${h * 0.1}px ${h * 0.14}px`, boxShadow: "0 18px 44px rgba(0,0,0,.45)", ...style }}>
      <Img src={staticFile(logo)} style={{ height: h, display: "block" }} />
    </div>) : null; };
  if (kind === "logohero") return (   // логотип-герой
    <AbsoluteFill style={{ background: "#1B2A3A" }}>
      {full(bg, "saturate(1.15) contrast(1.05)")}
      <AbsoluteFill style={{ background: "linear-gradient(90deg, rgba(0,0,0,.25) 0%, rgba(0,0,0,0) 55%)" }} />
      {panel(360, { left: 44, top: 40 })}
      {text1 && <div style={{ position: "absolute", left: 44, bottom: 46 }}><Box size={124} rotate={-2} style={{ background: YEL, color: "#111" }}>{text1}</Box></div>}
    </AbsoluteFill>
  );
  if (kind === "bignum") return (   // одно большое число
    <AbsoluteFill style={{ background: p.brandColor || "#0C3C6C" }}>
      <div style={{ position: "absolute", inset: 0, clipPath: "polygon(48% 0, 100% 0, 100% 100%, 40% 100%)" }}>{full(bg, "saturate(1.15) contrast(1.05)")}</div>
      <svg width={W} height={H} style={{ position: "absolute", inset: 0 }}><line x1={W * 0.48} y1={-10} x2={W * 0.40} y2={H + 10} stroke={YEL} strokeWidth={12} /></svg>
      {panel(150, { left: 44, top: 36 }, 340)}
      <div style={{ position: "absolute", left: 40, top: 230 }}>
        <div style={{ fontFamily: anton.fontFamily, fontSize: 330, lineHeight: 0.9, color: YEL, textShadow: OUT }}>{hook}</div>
        {text1 && <div style={{ fontFamily: anton.fontFamily, fontSize: 66, lineHeight: 1, color: "#FFFFFF", textTransform: "uppercase", marginTop: 8, textShadow: OUT }}>{text1}</div>}
      </div>
    </AbsoluteFill>
  );
  if (kind === "phrase") return (   // «было → стало» одной фразой
    <AbsoluteFill style={{ background: "#120D08" }}>
      {full(bg, "contrast(1.08) saturate(1.05)")}
      <AbsoluteFill style={{ background: "linear-gradient(90deg, rgba(8,6,4,.92) 0%, rgba(8,6,4,.75) 38%, rgba(8,6,4,0) 66%)" }} />
      <div style={{ position: "absolute", left: 44, top: 60 }}>
        <Big size={150}>{text1}</Big>
        <div style={{ display: "flex", alignItems: "center", gap: 22, marginTop: 18 }}>
          <Arrow w={120} />
          <Box size={190} rotate={-2} style={{ background: YEL, color: "#111" }}>{text2}</Box>
        </div>
      </div>
      {panel(150, { right: 40, bottom: 36 }, 320)}
    </AbsoluteFill>
  );
  // ---- 26.09, второй заход: ещё четыре направления по исследованию ниши ----
  const bigLogo = (maxW: number, maxH: number, style: React.CSSProperties, filter = "drop-shadow(0 16px 30px rgba(0,0,0,.55))") => {
    if (!logo) return null;
    const a = p.logoAspect || 1.5; const h = Math.min(maxH, maxW / a);
    return <Img src={staticFile(logo)} style={{ position: "absolute", height: h, filter, ...style }} />;
  };
  if (kind === "founder") return (   // основатель + огромный логотип + предмет, без текста
    <AbsoluteFill style={{ background: "#2A1D12" }}>
      {full(bg, "sepia(.35) saturate(1.1) contrast(1.05) brightness(.95)")}
      <AbsoluteFill style={{ background: "radial-gradient(ellipse at 70% 30%, rgba(255,240,210,.35) 0%, rgba(0,0,0,0) 55%)" }} />
      {logo && <div style={{ position: "absolute", right: 40, top: 36, width: 640, height: 250, display: "flex", alignItems: "center", justifyContent: "center",
        background: "rgba(255,250,240,.92)", borderRadius: 24, boxShadow: "0 20px 50px rgba(0,0,0,.5)" }}>
        <Img src={staticFile(logo)} style={{ maxWidth: 580, maxHeight: 200 }} /></div>}
      {product && <Img src={staticFile(product)} style={{ position: "absolute", right: 70, bottom: 26, height: 360, filter: "drop-shadow(0 24px 40px rgba(0,0,0,.7))" }} />}
      {person(cut, { left: cutX, height: cutH }, "contrast(1.08) saturate(1.05)")}
    </AbsoluteFill>
  );
  if (kind === "drama") return (   // тёмная драма: лицо, график, одно число
    <AbsoluteFill style={{ background: "#070707" }}>
      {full(bg, "brightness(.35) contrast(1.2) saturate(.8)")}
      <svg width={W} height={H} style={{ position: "absolute", inset: 0 }}>
        <polyline points={p.theme === "down" ? "520,120 700,200 820,170 960,330 1100,300 1260,560" : "520,600 680,520 800,560 960,380 1100,410 1260,120"}
          fill="none" stroke={p.theme === "down" ? "#E3262B" : "#22D36B"} strokeWidth={14} strokeLinejoin="round" style={{ filter: "drop-shadow(0 0 18px rgba(34,211,107,.6))" }} />
      </svg>
      {person(cut, { left: -30, height: 690 }, "contrast(1.15) saturate(1.05) brightness(1.05)")}
      {bigLogo(360, 130, { right: 50, top: 40 }, "drop-shadow(0 0 22px rgba(255,255,255,.35))")}
      <div style={{ position: "absolute", right: 50, bottom: 70, textAlign: "right" }}>
        <div style={{ fontFamily: anton.fontFamily, fontSize: 250, lineHeight: 0.9, color: p.theme === "down" ? "#FF3B30" : "#FFD21F", textShadow: OUT }}>{hook}</div>
        {text1 && <div style={{ fontFamily: anton.fontFamily, fontSize: 60, color: "#FFFFFF", textTransform: "uppercase", marginTop: 6, textShadow: OUT }}>{text1}</div>}
      </div>
    </AbsoluteFill>
  );
  if (kind === "minimal") return (   // фирменный цвет, логотип по центру, вопрос
    <AbsoluteFill style={{ background: `radial-gradient(ellipse at 50% 42%, ${p.brandColor || "#1B3A5C"} 0%, #0B0B0E 100%)` }}>
      {logo && <div style={{ position: "absolute", left: 0, right: 0, top: 70, display: "flex", justifyContent: "center" }}>
        <div style={{ background: "#FFFFFF", borderRadius: 36, padding: "40px 64px", boxShadow: "0 30px 70px rgba(0,0,0,.55)" }}>
          <Img src={staticFile(logo)} style={{ maxWidth: 820, maxHeight: 300, display: "block" }} /></div></div>}
      {text1 && <div style={{ position: "absolute", left: 0, right: 0, bottom: 56, display: "flex", justifyContent: "center" }}>
        <div style={{ fontFamily: anton.fontFamily, fontSize: 120, lineHeight: 1, color: "#FFFFFF", textTransform: "uppercase", textShadow: OUT }}>{text1}</div></div>}
    </AbsoluteFill>
  );
  // 27.09 шаблоны по разбору Astra (владелец: «превью делать по рекомендациям»)
  // 27.09 владелец: «маленькие лого на белом прямоугольнике ужасно смотрятся» — логотип крупно прямо на картинке,
  // контурная белая обводка (как вырезанная наклейка) и тень: читается на любом фоне без карточки
  const STICK = "drop-shadow(5px 0 0 #fff) drop-shadow(-5px 0 0 #fff) drop-shadow(0 5px 0 #fff) drop-shadow(0 -5px 0 #fff) drop-shadow(0 16px 28px rgba(0,0,0,.6))";
  const plate = (src: string | undefined, aspect: number | undefined, h: number, style: React.CSSProperties, maxW = 480) => {
    if (!src) return null; const a = aspect || 1.5, hh = Math.min(h * (a < 2 ? 1.45 : 1), maxW / a);
    return <Img src={staticFile(src)} style={{ position: "absolute", height: hh, filter: STICK, ...style }} />;
  };
  // 27.09 владелец: «совершенно другие форматы» — шесть непохожих подач
  const stick = (st: React.CSSProperties, h = 110, maxW = 420) => plate(logo, p.logoAspect, h, st, maxW);
  const bc = p.brandColor || "#1B3A5C";
  if (kind === "iceberg") return (   // над водой — то, что все видят; под водой — на чём деньги
    <AbsoluteFill style={{ background: "#06223A" }}>
      {full(bg, "saturate(1.1) contrast(1.05)")}
      {stick({ left: 40, top: 34 }, 100)}
      <div style={{ position: "absolute", right: 60, top: 70 }}><Box size={70} rotate={2} style={{ background: "#FFFFFF", color: "#111" }}>{text1}</Box></div>
      <div style={{ position: "absolute", left: 50, bottom: 60 }}><Box size={120} rotate={-2} style={{ background: YEL, color: "#111" }}>{text2}</Box></div>
    </AbsoluteFill>
  );
  if (kind === "receipt") return (   // чек: куда уходят деньги, одна строка выделена
    <AbsoluteFill style={{ background: `radial-gradient(ellipse at 70% 50%, ${bc} 0%, #0A0A0C 85%)` }}>
      <div style={{ position: "absolute", left: 50, top: 60, width: 560 }}>
        {stick({ position: "relative", display: "block", marginBottom: 34 }, 96)}
        {(text1 || "").split("|").map((w, i) => <div key={i} style={{ fontFamily: anton.fontFamily, fontSize: 124, lineHeight: 1, color: i ? YEL : "#FFFFFF", textShadow: OUT, textTransform: "uppercase" }}>{w}</div>)}
      </div>
      <div style={{ position: "absolute", right: 70, top: 40, width: 520, transform: "rotate(4deg)", filter: "drop-shadow(0 30px 50px rgba(0,0,0,.6))" }}>
        <div style={{ background: "#FBF8F1", padding: "34px 36px 60px", clipPath: "polygon(0 0,100% 0,100% 94%,95% 100%,90% 94%,85% 100%,80% 94%,75% 100%,70% 94%,65% 100%,60% 94%,55% 100%,50% 94%,45% 100%,40% 94%,35% 100%,30% 94%,25% 100%,20% 94%,15% 100%,10% 94%,5% 100%,0 94%)" }}>
          <div style={{ fontFamily: D.mono, fontWeight: 700, fontSize: 30, letterSpacing: 2, color: "#222", textAlign: "center", borderBottom: "3px dashed #999", paddingBottom: 16, marginBottom: 18 }}>{text2}</div>
          {(p.lines || []).map((l, i) => (
            <div key={i} style={{ display: "flex", justifyContent: "space-between", fontFamily: D.mono, fontWeight: 700, fontSize: l.hot ? 46 : 36, color: l.hot ? "#111" : "#555",
              background: l.hot ? YEL : "transparent", padding: l.hot ? "8px 12px" : "6px 12px", margin: "8px -12px" }}><span>{l.k}</span><span>{l.v}</span></div>))}
        </div>
      </div>
    </AbsoluteFill>
  );
  if (kind === "donut") {   // одна доля крупно
    const r = 200, c = 2 * Math.PI * r, f = Math.max(0, Math.min(100, p.pct || 0)) / 100;
    return (
      <AbsoluteFill style={{ background: `linear-gradient(135deg, #0B0B0E 0%, ${bc} 140%)` }}>
        <svg width={560} height={560} style={{ position: "absolute", right: 60, top: 80 }} viewBox="-280 -280 560 560">
          <circle r={r} fill="none" stroke="rgba(255,255,255,.14)" strokeWidth={110} />
          <circle r={r} fill="none" stroke={YEL} strokeWidth={110} strokeDasharray={`${c * f} ${c}`} transform="rotate(-90)" />
          <text y={30} textAnchor="middle" style={{ fontFamily: anton.fontFamily, fontSize: String(hook || "").length > 4 ? 88 : 118, fill: "#FFFFFF" }}>{hook}</text>
        </svg>
        <div style={{ position: "absolute", left: 50, top: 50 }}>{stick({ position: "relative", display: "block" }, 96)}</div>
        <div style={{ position: "absolute", left: 50, top: 230, width: 600 }}>
          <div style={{ fontFamily: anton.fontFamily, fontSize: 130, lineHeight: 1, color: YEL, textShadow: OUT, textTransform: "uppercase" }}>{text1}</div>
          <div style={{ fontFamily: anton.fontFamily, fontSize: 54, lineHeight: 1.08, color: "#FFFFFF", textTransform: "uppercase", marginTop: 16 }}>{text2}</div>
        </div>
      </AbsoluteFill>
    );
  }
  if (kind === "poster") return (   // типографика: одно слово на весь кадр
    <AbsoluteFill style={{ background: p.bgColor || bc }}>
      <Img src={grain} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", opacity: 0.18, mixBlendMode: "multiply" }} />
      <div style={{ position: "absolute", left: 56, right: 56, top: 210, fontFamily: anton.fontFamily, fontSize: (text1 || "").length > 9 ? 200 : 250, lineHeight: 0.9,
        color: "#FFFFFF", textTransform: "uppercase", textShadow: "0 10px 30px rgba(0,0,0,.35)" }}>{text1}</div>
      <div style={{ position: "absolute", left: 60, bottom: 70, fontFamily: anton.fontFamily, fontSize: 64, color: YEL, textTransform: "uppercase", textShadow: OUT }}>{text2}</div>
      {stick({ left: 60, top: 40 }, 90)}
    </AbsoluteFill>
  );
  if (kind === "illus") return (   // иллюстрация, крупный текст по центру снизу
    <AbsoluteFill style={{ background: "#111" }}>
      {full(bg, "saturate(1.2) contrast(1.05)")}
      <AbsoluteFill style={{ background: "linear-gradient(0deg, rgba(0,0,0,.75) 0%, rgba(0,0,0,0) 40%)" }} />
      {stick({ left: 40, top: 34 }, 100)}
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 40, textAlign: "center", fontFamily: anton.fontFamily, fontSize: 132, lineHeight: 1, color: "#FFFFFF", textShadow: OUT, textTransform: "uppercase" }}>
        {(text1 || "").split("|").map((w, i) => <span key={i} style={{ color: i ? YEL : "#FFFFFF" }}>{w}{i ? "" : " "}</span>)}</div>
    </AbsoluteFill>
  );
  if (kind === "xray") return (   // разрез предмета: внутри — настоящий бизнес
    <AbsoluteFill style={{ background: "#111" }}>
      {full(bg, "saturate(1.1) contrast(1.06)")}
      <AbsoluteFill style={{ background: "linear-gradient(180deg, rgba(0,0,0,.6) 0%, rgba(0,0,0,0) 34%)" }} />
      <div style={{ position: "absolute", left: 0, right: 0, top: 30, textAlign: "center", fontFamily: anton.fontFamily, fontSize: 118, lineHeight: 1, color: "#FFFFFF", textShadow: OUT, textTransform: "uppercase" }}>
        {(text1 || "").split("|").map((w, i) => <span key={i} style={{ color: i ? YEL : "#FFFFFF" }}>{w}{i ? "" : " "}</span>)}</div>
      {stick({ left: 40, bottom: 40 }, 96)}
    </AbsoluteFill>
  );
  if (kind === "mech") return (   // A. громкий бренд: привычный продукт + объект механизма, логотип сверху слева, 2–4 слова на жёлтой плашке
    <AbsoluteFill style={{ background: "#111" }}>
      {full(bg, "saturate(1.12) contrast(1.06)")}
      <AbsoluteFill style={{ background: "linear-gradient(0deg, rgba(0,0,0,.6) 0%, rgba(0,0,0,0) 38%), linear-gradient(180deg, rgba(0,0,0,.35) 0%, rgba(0,0,0,0) 30%)" }} />
      {plate(logo, p.logoAspect, 130, { left: 44, top: 38 })}
      {text1 && <div style={{ position: "absolute", left: 40, bottom: 44 }}>
        <Box size={text1.length > 14 ? 88 : 108} rotate={-2} style={{ background: YEL, color: "#111" }}>{text1.replace("|", " ")}</Box></div>}
    </AbsoluteFill>
  );
  if (kind === "deal") return (   // C. сделка/решение: два участника по краям, документ в центре, штамп решения
    <AbsoluteFill style={{ background: "#111" }}>
      {full(bg, "saturate(1.0) contrast(1.05) brightness(.82)")}
      <AbsoluteFill style={{ background: `linear-gradient(90deg, ${p.brandColor2 || "#1B1B1B"}F0 0%, ${p.brandColor2 || "#1B1B1B"}00 30%, ${p.brandColor || "#1B1B1B"}00 70%, ${p.brandColor || "#1B1B1B"}F0 100%)` }} />
      {plate(p.logo2, p.logoAspect2, 130, { left: 40, top: "50%", transform: "translateY(-50%)" }, 330)}
      {plate(logo, p.logoAspect, 130, { right: 40, top: "50%", transform: "translateY(-50%)" }, 330)}
      {text1 && <div style={{ position: "absolute", left: 0, right: 0, top: 250, display: "flex", justifyContent: "center" }}>
        <div style={{ fontFamily: anton.fontFamily, fontSize: text1.length > 9 ? 96 : text1.length > 6 ? 112 : 132, lineHeight: 1, color: RED, textTransform: "uppercase", border: `10px solid ${RED}`,
          borderRadius: 14, padding: "10px 34px 16px", transform: "rotate(-9deg)", background: "rgba(255,248,235,.9)", boxShadow: "0 18px 40px rgba(0,0,0,.45)" }}>{text1.replace("|", " ")}</div></div>}
    </AbsoluteFill>
  );
  if (kind === "object") return (   // предмет-герой и заголовок
    <AbsoluteFill style={{ background: "#111" }}>
      {full(bg, "saturate(1.15) contrast(1.08)")}
      <AbsoluteFill style={{ background: "linear-gradient(180deg, rgba(0,0,0,.72) 0%, rgba(0,0,0,.25) 38%, rgba(0,0,0,0) 60%)" }} />
      {text1 && <div style={{ position: "absolute", left: 44, right: 44, top: 34, fontFamily: anton.fontFamily, lineHeight: 1.0, color: "#FFFFFF", textTransform: "uppercase", textShadow: OUT,
        // 29.09 серия A: «WHAT HAPPENED / TO [БРЕНД]?» — длинное имя бренда уменьшает шрифт, а не залезает под знак
        fontSize: Math.min(118, Math.round(118 * 15 / Math.max(15, ...text1.split("|").map((w) => w.length)))) }}>
        {text1.split("|").map((w, i) => <div key={i} style={{ color: i === 1 ? YEL : "#FFFFFF" }}>{w}</div>)}</div>}
      {p.logoSticker && logo ? plate(logo, p.logoAspect, 120, { right: 44, top: 40 }, 440) : p.logoPlate && logo ? (() => {   // 27.09 Safelite: владелец — «увеличь логотип»; на белой плашке, чтобы читался в ленте
        const k = p.logoScale || 1, a = p.logoAspect || 1.5, h = Math.min(110 * k, 300 * k / a);
        return <div style={{ position: "absolute", right: 40, ...(p.logoCorner === "tr" ? { top: 34 } : { bottom: p.logoBottom ?? 34 }), background: "#FFFFFF", borderRadius: 22, padding: `${Math.round(h * 0.28)}px ${Math.round(h * 0.45)}px`, boxShadow: "0 16px 40px rgba(0,0,0,.5)" }}>
          <Img src={staticFile(logo)} style={{ height: h, display: "block" }} /></div>;
      })() : bigLogo(300 * (p.logoScale || 1), 110 * (p.logoScale || 1), { right: 40, bottom: 34 })}
    </AbsoluteFill>
  );
  if (kind === "split" && p.theme === "neon") {   // второй канал: синий/жёлтый вместо бумаги/оксблада, гротеск в бирках, без наклона
    const NAVY = "#0B1B33", YL = "#FFD500";
    const tag = (t: string): React.CSSProperties => ({ fontFamily: "'Space Grotesk', 'Segoe UI', Arial, sans-serif", fontWeight: 700, fontSize: 40, letterSpacing: 4, color: YL, background: NAVY, padding: "8px 22px", borderRadius: 10, border: `3px solid ${YL}` });
    return (
      <AbsoluteFill style={{ background: NAVY }}>
        <div style={{ position: "absolute", inset: 0, clipPath: "polygon(0 0, 56% 0, 44% 100%, 0 100%)" }}>
          {full(bg, "grayscale(1) contrast(1.15) brightness(.75)")}
          <AbsoluteFill style={{ background: "rgba(11,27,51,.35)" }} />
          {person(cut, { left: cutX, height: cutH }, "grayscale(1) contrast(1.15)")}
        </div>
        <div style={{ position: "absolute", inset: 0, clipPath: "polygon(56% 0, 100% 0, 100% 100%, 44% 100%)" }}>{full(bg2, "saturate(1.2) contrast(1.05)")}</div>
        <svg width={W} height={H} style={{ position: "absolute", inset: 0 }}><line x1={W * 0.56} y1={-10} x2={W * 0.44} y2={H + 10} stroke={YL} strokeWidth={12} /></svg>
        {tagL && <div style={{ position: "absolute", left: 34, top: 30, ...tag(tagL) }}>{tagL}</div>}
        {tagR && <div style={{ position: "absolute", right: 34, top: 30, ...tag(tagR) }}>{tagR}</div>}
        <div style={{ position: "absolute", left: 0, right: 0, top: 30, display: "flex", justifyContent: "center" }}>
          <div style={{ background: NAVY, border: `3px solid ${YL}`, borderRadius: 14, padding: "12px 22px" }}><BrandMark mark={mark} logo={logo} wordmark={wordmark} size={markSize ?? 52} brandWord={p.brandWord} /></div>
        </div>
        {hook && <div style={{ position: "absolute", left: 36, bottom: 40 }}><Box size={104} rotate={0} style={{ background: NAVY, color: "#FFFFFF", border: `4px solid ${YL}`, borderRadius: 12 }}>{hook}</Box></div>}
        <div style={{ position: "absolute", left: 575, top: 405 }}><Arrow w={150} color={YL} /></div>
        {hook2 && <div style={{ position: "absolute", right: 46, top: 300 }}><Box size={168} rotate={0} style={{ background: YL, color: NAVY, borderRadius: 14 }}>{hook2}</Box></div>}
      </AbsoluteFill>
    );
  }
  if (kind === "split2") return (   // 28.09: чистая пересборка обложки vidIQ для First American — лица без дефектов, логотип настоящий
    <AbsoluteFill style={{ background: "#000" }}>
      <div style={{ position: "absolute", inset: 0, clipPath: "polygon(0 0, 55% 0, 45% 100%, 0 100%)" }}>
        {bg && <Img src={staticFile(bg)} style={{ position: "absolute", left: 0, top: 0, width: "55%", height: "100%", objectFit: "cover", objectPosition: "50% 62%", filter: "grayscale(1) sepia(.18) contrast(1.08)" }} />}
        <AbsoluteFill style={{ background: "linear-gradient(0deg, rgba(0,0,0,.45) 0%, rgba(0,0,0,0) 35%)" }} />
      </div>
      <div style={{ position: "absolute", inset: 0, clipPath: "polygon(55% 0, 100% 0, 100% 100%, 45% 100%)" }}>
        {bg2 && <Img src={staticFile(bg2)} style={{ position: "absolute", right: 0, top: 0, width: "58%", height: "100%", objectFit: "cover", objectPosition: "60% 50%", filter: "saturate(1.2) contrast(1.05)" }} />}
      </div>
      <svg width={W} height={H} style={{ position: "absolute", inset: 0 }}><line x1={W * 0.55} y1={-10} x2={W * 0.45} y2={H + 10} stroke="#FFFFFF" strokeWidth={8} /></svg>
      {[tagL, tagR].map((t, i) => t ? (() => {   // «год · что это за число»: год крупно, подпись мелко второй строкой — не лезет под логотип
        const [yr, unit] = String(t).split(" · ");
        return <div key={i} style={{ position: "absolute", ...(i ? { right: 40 } : { left: 40 }), top: 34 }}>
          <Tag rotate={i ? 3 : -3}><div style={{ fontFamily: D.mono, fontWeight: 700, fontSize: 60, letterSpacing: 4, color: D.ox, lineHeight: 1 }}>{yr}</div>
            {unit && <div style={{ fontFamily: D.mono, fontWeight: 700, fontSize: 24, letterSpacing: 2, color: D.brown, textTransform: "uppercase", marginTop: 6 }}>{unit}</div>}</Tag></div>;
      })() : null)}
      {(logo || mark || p.brandWord) && <div style={{ position: "absolute", left: 0, right: 0, top: 26, display: "flex", justifyContent: "center" }}>
        <div style={{ background: p.plateColor || p.brandColor || "#0C2D5A", borderRadius: 14, padding: "20px 34px", boxShadow: "0 14px 34px rgba(0,0,0,.5)", display: "flex", alignItems: "center", gap: 18 }}>
          {logo && !mark ? <Img src={staticFile(logo)} style={{ height: Math.min(86, 520 / (p.logoAspect || 5)), display: "block" }} /> : <BrandMark mark={mark} size={62} brandWord={p.brandWord} />}
          {logo && !mark && p.brandWord && <div style={{ fontFamily: "'Segoe UI', 'Helvetica Neue', Arial, sans-serif", fontWeight: 700, fontSize: 62, lineHeight: 1, color: p.wordColor || "#111" }}>{p.brandWord}</div>}
        </div></div>}
      {hook && <div style={{ position: "absolute", left: 40, bottom: 46 }}><Box size={104} rotate={-3}>{hook}</Box></div>}
      <div style={{ position: "absolute", left: 548, top: 420 }}><Arrow w={150} /></div>
      {hook2 && <div style={{ position: "absolute", right: 50, top: 330 }}><Box size={String(hook2).length > 6 ? 146 : 176} rotate={-2} style={{ background: YEL, color: "#111" }}>{hook2}</Box></div>}
    </AbsoluteFill>
  );
  if (kind === "split") return (
    <AbsoluteFill style={{ background: "#000" }}>
      <div style={{ position: "absolute", inset: 0, clipPath: "polygon(0 0, 56% 0, 44% 100%, 0 100%)" }}>
        {full(bg, "grayscale(1) sepia(.35) contrast(1.1) brightness(.8)")}
        {person(cut, { left: cutX, height: cutH }, "grayscale(1) sepia(.3) contrast(1.12)")}
      </div>
      <div style={{ position: "absolute", inset: 0, clipPath: "polygon(56% 0, 100% 0, 100% 100%, 44% 100%)" }}>{full(bg2, "saturate(1.25) contrast(1.05)")}</div>
      <svg width={W} height={H} style={{ position: "absolute", inset: 0 }}><line x1={W * 0.56} y1={-10} x2={W * 0.44} y2={H + 10} stroke="#FFFFFF" strokeWidth={10} /></svg>
      {tagL && <div style={{ position: "absolute", left: 34, top: 30 }}><MonoTag rotate={-3} size={tagSize(tagL)}>{tagL}</MonoTag></div>}
      {tagR && <div style={{ position: "absolute", right: 34, top: 30 }}><MonoTag rotate={3} size={tagSize(tagR)}>{tagR}</MonoTag></div>}
      {p.logoStyle === "ghost" && <LogoArt {...p} />}
      {hook && <div style={{ position: "absolute", left: 36, bottom: 40 }}><Box size={104} rotate={-3}>{hook}</Box></div>}
      <div style={{ position: "absolute", left: 575, top: 405 }}><Arrow w={150} /></div>
      {hook2 && <div style={{ position: "absolute", right: 46, top: 300 }}><Box size={168} rotate={-2} style={{ background: YEL, color: "#111" }}>{hook2}</Box></div>}
      {p.logoStyle !== "ghost" && <LogoArt {...p} />}
    </AbsoluteFill>
  );
  if (kind === "breakup") return (
    <AbsoluteFill style={{ background: "#0B0B0D" }}>
      {full(bg, "brightness(.42) contrast(1.1) saturate(.8)")}
      <AbsoluteFill style={{ background: "radial-gradient(ellipse at 70% 42%, rgba(0,0,0,0) 18%, rgba(0,0,0,.78) 100%)" }} />
      <div style={{ position: "absolute", left: 700, top: 70 }}><Cracked size={170} /></div>
      {product && <Img src={staticFile(product)} style={{ position: "absolute", left: 610, bottom: 16, width: 430, filter: "drop-shadow(0 20px 30px rgba(0,0,0,.85))" }} />}
      <div style={{ position: "absolute", left: 48, top: 64 }}>
        <Big size={128}>{text1}</Big>
        <Box size={112} rotate={-3} style={{ background: RED, color: "#FFFFFF", marginTop: 14 }}>{text2}</Box>
      </div>
      {tagL && <div style={{ position: "absolute", left: 52, bottom: 50 }}><MonoTag rotate={-2}>{tagL}</MonoTag></div>}
    </AbsoluteFill>
  );
  if (kind === "notsoft") return (
    <AbsoluteFill style={{ background: "#06101C" }}>
      {full(bg, "brightness(.75) saturate(1.2)")}
      <AbsoluteFill style={{ background: "linear-gradient(90deg, rgba(3,8,16,.92) 0%, rgba(3,8,16,.55) 45%, rgba(3,8,16,.08) 78%)" }} />
      {person(cut, { right: cutX, height: cutH })}
      <div style={{ position: "absolute", left: 48, top: 40 }}><Big size={150}>{text1}</Big><Big size={150} color={YEL}>{text2}</Big></div>
      {product && (
        <div style={{ position: "absolute", left: 70, bottom: 30, width: 300 }}>
          <Img src={staticFile(product)} style={{ width: "100%", filter: "drop-shadow(0 18px 28px rgba(0,0,0,.85))" }} />
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ position: "absolute", left: -12, top: -12, width: 324, height: "calc(100% + 24px)" }}>
            <path d="M10 10 L90 90 M90 10 L10 90" stroke={RED} strokeWidth={9} strokeLinecap="round" />
          </svg>
        </div>
      )}
      <div style={{ position: "absolute", left: 420, bottom: 44 }}><BrandMark mark={mark} logo={logo} wordmark={wordmark} size={markSize ?? 56} /></div>
    </AbsoluteFill>
  );
  if (kind === "dropouts") return (
    <AbsoluteFill style={{ background: "radial-gradient(ellipse at 70% 45%, #2A3440 0%, #0C0F14 75%)" }}>
      {full(bg, "brightness(.32) saturate(.5) blur(3px)")}
      {product && <Img src={staticFile(product)} style={{ position: "absolute", right: 70, top: 150, width: 460, filter: "drop-shadow(0 26px 40px rgba(0,0,0,.85))" }} />}
      {person(cut, { left: cutX, height: cutH }, "grayscale(1) contrast(1.15)")}
      <div style={{ position: "absolute", right: 46, top: 30, textAlign: "right" }}><Big size={118}>{text1}</Big></div>
      <div style={{ position: "absolute", right: 70, top: 460 }}><Box size={108} rotate={-3} style={{ background: RED, color: "#FFFFFF" }}>{text2}</Box></div>
      <div style={{ position: "absolute", left: 36, top: 30 }}><Pill><BrandMark mark={mark} logo={logo} wordmark={wordmark} size={markSize ?? 46} /></Pill></div>
    </AbsoluteFill>
  );
  return (   // bigface: крупное настоящее лицо + одна огромная цифра
    <AbsoluteFill style={{ background: "radial-gradient(ellipse at 30% 50%, #7A1414 0%, #2A0606 60%, #120303 100%)" }}>
      {person(cut, { left: cutX, height: cutH })}
      <div style={{ position: "absolute", right: 50, top: 56, display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 16 }}>
        {tagL && <MonoTag rotate={2} size={34}>{tagL}</MonoTag>}
        <Big size={230} color={YEL}>{hook}</Big>
        <BrandMark mark={mark} logo={logo} wordmark={wordmark} size={markSize ?? 62} />
      </div>
    </AbsoluteFill>
  );
};

export const ThumbV: React.FC<ThumbVProps> = (p) => {
  const V = { money: MoneyBW, computer: Computer666, thennow: ThenNow, dossier: Dossier, face: Face, brand: Brand, facelogo: FaceLogo, kit: Kit, ref: Ref, bold: Bold }[p.variant] ?? MoneyBW;
  return <V {...p} />;
};
