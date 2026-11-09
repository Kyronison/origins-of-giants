import { AbsoluteFill, Sequence, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { Overlay } from "./theme";
import { loadFont as loadAnton } from "@remotion/google-fonts/Anton";
import { D, DoubleRule, Tag } from "./dossier";

const anton = loadAnton("normal", { weights: ["400"], subsets: ["latin"] });
const YEL = "#F2C94C";

/** Слой титров story-формата в стиле «Архивное досье» (владелец 16.09): кремовые ярлыки, машинопись, антиква.
 *  caption — место/дата внизу (печатается); flash — цифра на карточке; year — бирка года справа сверху; chapter — карточка главы
 *  (с pause — в тишине над первым кадром главы, §3.5). blur=false — без backdrop-filter (SwiftShader). */
export const Overlays: React.FC<{ overlays: Overlay[]; offset?: number; vertical?: boolean; blur?: boolean }> = ({ overlays, offset = 0, vertical, blur = true }) => {
  const { fps } = useVideoConfig();
  return (
    <>
      {overlays.map((o, i) => {
        // карточка с паузой: вуаль поднимается с `pause.at` (первый кадр главы стартует там же, dip) — без пустого кадра
        const from = o.type === "chapter" && o.pause && o.pause.at < o.start ? o.pause.at : o.start;
        // подпись места/даты стоит внизу по центру — когда в это же время идёт строка-леджер с цифрой, подпись поднимается над ней
        const lift = o.type === "caption" && !vertical && overlays.some((x) => x.type === "flash" && x.start < o.end && x.end > o.start);
        return (
          <Sequence key={i} from={Math.round((from - offset) * fps)} durationInFrames={Math.max(1, Math.round((o.end - from) * fps))}>
            {o.type === "chapter" ? (D.flat && !vertical ? <ChapterNeon text={o.text ?? ""} n={o.n} pause={!!o.pause} lead={o.start - from} /> : <Chapter text={o.text ?? ""} n={o.n} vertical={vertical} pause={!!o.pause} blur={blur} lead={o.start - from} />)
              : o.type === "pair" ? <Pair then={o.then ?? ""} now={o.now ?? o.value ?? ""} tagL={o.tagL} tagR={o.tagR} />
              : o.type === "flash" ? (vertical ? <Flash value={o.value ?? ""} label={o.label} vertical seed={i} /> : D.flat ? <Kinetic value={o.value ?? ""} label={o.label} seed={i} /> : <Ledger value={o.value ?? ""} label={o.label} source={o.source} />)
              : o.type === "year" ? <Year value={o.value ?? ""} from={o.from} vertical={vertical} />
              : <Caption text={o.text ?? ""} vertical={vertical} seed={i} lift={lift} />}
          </Sequence>
        );
      })}
    </>
  );
};

const useInOut = (inSec = 0.35, outSec = 0.35) => {
  const f = useCurrentFrame(); const { fps, durationInFrames } = useVideoConfig();
  const a = interpolate(f, [0, fps * inSec], [0, 1], { extrapolateRight: "clamp" });
  const b = interpolate(f, [durationInFrames - fps * outSec, durationInFrames], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return Math.min(a, b);
};
/** Детерминированный наклон ярлыка ±1° — ярлыки не лежат одинаково, но кадр рендерится одинаково в любом воркере. */
const tilt = (seed: number, max = 1) => (((seed * 7919) % 13) / 12 - 0.5) * 2 * max;

/** Место и дата: ярлык внизу по центру, машинопись печатается 40 симв/с. */
export const Caption: React.FC<{ text: string; vertical?: boolean; seed?: number; lift?: boolean }> = ({ text, vertical, seed = 0, lift }) => {
  const o = useInOut(); const f = useCurrentFrame(); const { fps } = useVideoConfig();
  const typed = text.slice(0, Math.max(0, Math.floor((f / fps) * 40)));
  return (
    <div style={{ position: "absolute", left: 0, right: 0, bottom: vertical ? "30%" : D.pad * 1.1 + (lift ? 84 : 0), display: "flex", justifyContent: "center", opacity: o, transform: `translateY(${(1 - o) * 8}px)` }}>
      <Tag rotate={tilt(seed, 0.8)} style={{ fontFamily: D.mono, fontWeight: 700, fontSize: vertical ? 32 : 26, letterSpacing: 1.5, textTransform: "uppercase", minWidth: 60, minHeight: 34, padding: "12px 22px" }}>
        {typed}
      </Tag>
    </div>
  );
};

/** Цифра: карточка с антиквой и машинописной подписью; въезжает с лёгким «шлепком» (scale 0.92→1). */
export const Flash: React.FC<{ value: string; label?: string; vertical?: boolean; seed?: number }> = ({ value, label, vertical, seed = 0 }) => {
  const f = useCurrentFrame(); const { fps } = useVideoConfig();
  const o = useInOut(0.25, 0.3);
  const s = spring({ frame: f, fps, config: { damping: 18, stiffness: 140 } });
  return (
    <div style={{ position: "absolute", left: vertical ? 56 : D.pad, top: vertical ? "18%" : D.pad * 1.5, opacity: o, transform: `scale(${0.92 + 0.08 * s})`, transformOrigin: "left top" }}>
      <Tag rotate={-1 + tilt(seed, 0.4)} style={{ padding: vertical ? "18px 26px 20px" : "20px 32px 22px" }}>
        <div style={{ fontFamily: D.serif, fontSize: vertical ? 92 : 104, lineHeight: 1, color: D.brown, fontVariantNumeric: "lining-nums" }}>{value}</div>
        {label && <div style={{ fontFamily: D.mono, fontSize: vertical ? 26 : 24, letterSpacing: 2, color: D.ox, marginTop: 8, maxWidth: 560, textTransform: "uppercase", lineHeight: 1.3 }}>{label}</div>}
      </Tag>
    </div>
  );
};

/** Число с «досчётом»: $45.9B считается от нуля за 0.7 с; нечисловое («ILLEGAL», «⅓») и диапазоны показываются сразу. */
const countUp = (value: string, p: number): string => {
  const m = value.match(/^(\D*)(\d[\d,]*(?:\.\d+)?)(\D*)$/);
  if (!m || p >= 1) return value;
  const raw = m[2].replace(/,/g, ""); const dec = (raw.split(".")[1] ?? "").length;
  const v = parseFloat(raw) * (1 - Math.pow(1 - p, 3));
  const s = dec ? v.toFixed(dec) : Math.round(v).toLocaleString("en-US");
  return m[1] + s + m[3];
};

/** Промежуточная цифра — строка-леджер внизу кадра (выбор владельца 21.09, вариант B): цифра шрифтом Anton как на превью,
 *  подпись машинописью, справа источник. Не закрывает кадр и лица; появляется ровно на слове диктора. */
export const Ledger: React.FC<{ value: string; label?: string; source?: string }> = ({ value, label, source }) => {
  const f = useCurrentFrame(); const { fps } = useVideoConfig();
  const o = useInOut(0.22, 0.3);
  const p = interpolate(f, [0, fps * 0.7], [0, 1], { extrapolateRight: "clamp" });
  return (
    <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, transform: `translateY(${(1 - o) * 100}%)`, background: "rgba(21,16,12,.96)", borderTop: `5px solid ${D.ox}`,
      padding: `22px ${D.pad}px 24px`, display: "flex", alignItems: "baseline", gap: 30 }}>
      <div style={{ fontFamily: anton.fontFamily, fontSize: 92, lineHeight: 1, letterSpacing: 2, color: "#FFF8E8", fontVariantNumeric: "tabular-nums" }}>{countUp(value, p)}</div>
      {label && <div style={{ fontFamily: D.mono, fontSize: 30, fontWeight: 700, letterSpacing: 3, color: D.text, textTransform: "uppercase", maxWidth: 1000, lineHeight: 1.25 }}>{label}</div>}
      {source && <div style={{ marginLeft: "auto", fontFamily: D.mono, fontSize: 26, fontWeight: 700, letterSpacing: 3, color: YEL, textTransform: "uppercase" }}>{source}</div>}
    </div>
  );
};

/** cinético (испанский канал): цифра «влетает» крупно поверх кадра — справа или слева, чередуясь, — подпись мелко над ней. Без плашки. */
/** Короткая единица (cents, centavos, %, seconds) печатается рядом с числом: подпись сверху читается как
 *  отдельное слово, и «50» выглядит голым числом (кадры-пробы Costco es, 24.09). Длинная подпись-категория — сверху. */
const inlineUnit = (label?: string) => !!label && label.trim().length <= 12 && !label.includes(" ");

export const Kinetic: React.FC<{ value: string; label?: string; seed?: number }> = ({ value, label, seed = 0 }) => {
  const f = useCurrentFrame(); const { fps } = useVideoConfig();
  const o = useInOut(0.2, 0.3);
  const s = spring({ frame: f, fps, config: { damping: 14, stiffness: 160 } });
  const p = interpolate(f, [0, fps * 0.7], [0, 1], { extrapolateRight: "clamp" });
  const right = seed % 2 === 0;
  return (
    <div style={{ position: "absolute", [right ? "right" : "left"]: D.pad, top: D.pad * 1.3, textAlign: right ? "right" : "left", opacity: o,
      transform: `translateY(${(1 - s) * -40}px) scale(${0.85 + 0.15 * s})`, transformOrigin: right ? "right top" : "left top" }}>
      {label && !inlineUnit(label) && <div style={{ fontFamily: D.sans ?? D.mono, fontWeight: 700, fontSize: 28, letterSpacing: 4, color: "#FFFFFF", textTransform: "uppercase", textShadow: "0 2px 12px rgba(0,0,0,.8)" }}>{label}</div>}
      <div style={{ fontFamily: anton.fontFamily, fontSize: 168, lineHeight: 1, letterSpacing: 2, color: YEL, textShadow: "0 6px 0 #071224, 0 10px 40px rgba(0,0,0,.7)", fontVariantNumeric: "tabular-nums" }}>{countUp(value, p)}{label && inlineUnit(label) && <span style={{ fontSize: 62, letterSpacing: 2, marginLeft: 14 }}>{label.toUpperCase()}</span>}</div>
    </div>
  );
};

/** cinético: карточка главы — жёлтое поле со шторкой слева, «CAPÍTULO N» и название гротеском. */
export const ChapterNeon: React.FC<{ text: string; n?: number; pause?: boolean; lead?: number }> = ({ text, n, pause, lead = 0 }) => {
  const f0 = useCurrentFrame(); const { fps, durationInFrames } = useVideoConfig();
  const L = pause ? Math.round(lead * fps) : 0; const f = f0 - L;
  const wipe = interpolate(f, [0, fps * 0.45], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const out = interpolate(f0, [durationInFrames - fps * 0.5, durationInFrames], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const tx = interpolate(f, [8, 26], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const pre = pause ? interpolate(f0, [0, Math.max(L, 1)], [0.6, 0.6], { extrapolateRight: "clamp" }) : 0;
  return (
    <AbsoluteFill style={{ opacity: out }}>
      {pause && f < 0 && <AbsoluteFill style={{ background: `rgba(7,18,36,${pre})` }} />}
      <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${wipe * 100}%`, background: YEL }} />
      <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 28 * wipe, background: "#0B1B33" }} />
      <div style={{ position: "absolute", left: 140, top: 360, opacity: tx, transform: `translateX(${(1 - tx) * -40}px)` }}>
        {n !== undefined && <div style={{ fontFamily: D.sans ?? D.mono, fontWeight: 700, fontSize: 36, letterSpacing: 8, color: "#0B1B33" }}>{D.words.file} {n}</div>}
        <div style={{ fontFamily: anton.fontFamily, fontSize: 150, lineHeight: 1, letterSpacing: 2, color: "#0B1B33", marginTop: 16, textTransform: "uppercase", maxWidth: 1500 }}>{text}</div>
      </div>
    </AbsoluteFill>
  );
};

/** Главная цифра ролика — полноэкранная пара «было → стало» в логике превью: Anton, справа жёлтая плашка. */
export const Pair: React.FC<{ then: string; now: string; tagL?: string; tagR?: string }> = ({ then, now, tagL, tagR }) => {
  const f = useCurrentFrame(); const { fps } = useVideoConfig();
  const o = useInOut(0.3, 0.4);
  const a = spring({ frame: f - 4, fps, config: { damping: 200, stiffness: 90 } });
  const b = spring({ frame: f - 22, fps, config: { damping: 14, stiffness: 120 } });
  const p = interpolate(f, [22, 22 + fps * 0.8], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  // Размер подбирается под длину строки: при фиксированных 190/210 длинное число («$173.5M», Boston Market 24.09)
  // уезжало за правый край кадра. Бюджет ширины на колонку — 700 px, ширина знака Anton ≈ 0.62 кегля.
  const fit = (s: string, base: number, budget = 700) => {
    const n = Math.max(1, ...String(s || "").split(/\s+/).map((w) => w.length));
    return Math.min(base, Math.floor(budget / (n * 0.62)));
  };
  const thenSize = fit(then, 190), nowSize = fit(now, 210);
  const col: React.CSSProperties = { textAlign: "center", minWidth: 520, maxWidth: 780 };
  const tag: React.CSSProperties = { fontFamily: D.mono, fontSize: 30, letterSpacing: 5, color: D.muted, textTransform: "uppercase", marginBottom: 26 };
  return (
    <AbsoluteFill style={{ background: `rgba(27,21,17,${0.9 * o})`, alignItems: "center", justifyContent: "center", flexDirection: "row", gap: 90, opacity: o }}>
      <div style={{ ...col, opacity: a, transform: `translateY(${(1 - a) * 24}px)` }}>
        {tagL && <div style={tag}>{tagL}</div>}
        <div style={{ fontFamily: anton.fontFamily, fontSize: thenSize, lineHeight: 1, letterSpacing: 3, color: D.text }}>{then}</div>
      </div>
      <div style={{ fontFamily: anton.fontFamily, fontSize: 120, color: D.text, opacity: b }}>→</div>
      <div style={{ ...col, opacity: b, transform: `scale(${0.9 + 0.1 * b})` }}>
        {tagR && <div style={tag}>{tagR}</div>}
        <div style={{ display: "inline-block", fontFamily: anton.fontFamily, fontSize: nowSize, whiteSpace: "nowrap", lineHeight: 1, letterSpacing: 3, color: "#111", background: YEL, padding: "14px 44px 20px", transform: "rotate(-2deg)" }}>{countUp(now, p)}</div>
      </div>
    </AbsoluteFill>
  );
};

/** Бирка года справа сверху: кроссфейд цифр from→value за 0.6 с. */
export const Year: React.FC<{ value: string; from?: string; vertical?: boolean }> = ({ value, from, vertical }) => {
  const f = useCurrentFrame(); const { fps } = useVideoConfig();
  const o = useInOut(0.3, 0.35);
  const x = from ? interpolate(f, [fps * 0.3, fps * 0.9], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) : 1;
  return (
    <div style={{ position: "absolute", right: vertical ? 56 : D.pad, top: vertical ? "12%" : D.pad * 1.2, opacity: o, transform: `translateY(${(1 - o) * -8}px)` }}>
      <Tag rotate={0.8} style={{ padding: "12px 24px 14px" }}>
        <div style={{ position: "relative", fontFamily: D.serif, fontSize: 60, lineHeight: 1, color: D.brown }}>
          <span style={{ opacity: x }}>{value}</span>
          {from && <span style={{ position: "absolute", left: 0, top: 0, opacity: 1 - x, color: D.ox }}>{from}</span>}
        </div>
      </Tag>
    </div>
  );
};

export const ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"];

/** Карточка главы — ярлык «— FILE No. N —» с названием антиквой и двойной линией. С pause (§3.5): под ней первый кадр главы
 *  под тёплой вуалью с размытием; ярлык ложится (наклон −0.6°, опускается на 20 px), слова названия появляются по одному;
 *  выход за 0.6 с до конца — кадр «проявляется» ровно перед первым словом диктора. */
export const Chapter: React.FC<{ text: string; n?: number; vertical?: boolean; pause?: boolean; blur?: boolean; lead?: number }> = ({ text, n, vertical, pause, blur = true, lead = 0 }) => {
  const f0 = useCurrentFrame(); const { fps, durationInFrames } = useVideoConfig();
  const L = pause ? Math.round(lead * fps) : 0; const f = f0 - L;
  const inn = pause ? 0.65 + 0.35 * interpolate(f0, [0, Math.max(L, fps * 0.3)], [0, 1], { extrapolateRight: "clamp" }) : interpolate(f0, [0, fps * 0.5], [0, 1], { extrapolateRight: "clamp" });
  const out = interpolate(f0, [durationInFrames - fps * 0.6, durationInFrames], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const o = Math.min(inn, out);
  const drop = spring({ frame: f, fps, config: { damping: 16, stiffness: 120 } });
  const head = interpolate(f, [6, 20], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const words = text.split(/\s+/).filter(Boolean);
  const rule = interpolate(f, [22, 42], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const blurPx = pause && blur ? (12 * o).toFixed(1) : undefined;
  return (
    <AbsoluteFill style={{ background: `rgba(27,21,17,${(pause ? 0.72 : 0.66) * o})`, backdropFilter: blurPx ? `blur(${blurPx}px)` : undefined,
      WebkitBackdropFilter: blurPx ? `blur(${blurPx}px)` : undefined, alignItems: "center", justifyContent: "center" }}>
      <div style={{ opacity: Math.min(out, drop * 1.2), transform: `translateY(${(1 - drop) * -20}px)` }}>
        <Tag rotate={-0.6} style={{ padding: vertical ? "34px 48px" : "44px 90px", textAlign: "center", maxWidth: vertical ? 920 : 1500 }}>
          {n !== undefined && (
            <div style={{ fontFamily: D.mono, fontSize: vertical ? 26 : 30, letterSpacing: 4, color: D.ox, opacity: head }}>— {D.words.file} {n} —</div>
          )}
          <div style={{ fontFamily: D.serif, fontSize: vertical ? 72 : 104, lineHeight: 1.08, color: D.brown, marginTop: 10 }}>
            {words.map((w, i) => {
              const s = spring({ frame: f - 10 - i * 4, fps, config: { damping: 200, stiffness: 90 } });
              return <span key={i} style={{ display: "inline-block", marginRight: i < words.length - 1 ? "0.26em" : 0, opacity: s, transform: `translateY(${(1 - s) * 18}px)` }}>{w}</span>;
            })}
          </div>
          <DoubleRule width={300 * rule} style={{ margin: "22px auto 0" }} />
        </Tag>
      </div>
    </AbsoluteFill>
  );
};
