import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { T, Slot as SlotT } from "../theme";
import { Frame, useEnter, RedRule, Layout } from "./common";
import { Slot } from "./Slot";
import { fitRole } from "./People";
import { D } from "../dossier";

/** Старая карточка цитаты форматов news/anatomy — без изменений. */
export const Quote: React.FC<{ d: any; caption?: string } & Layout> = ({ d, vertical, card }) => {
  vertical = vertical || card;
  const s = useEnter();
  return (
    <Frame vertical={vertical} card={card}>
      <div style={{ fontFamily: T.display, fontStyle: "italic", fontSize: vertical ? 56 : 76, lineHeight: 1.15, maxWidth: 1500, opacity: s }}>
        “{d.text}”
      </div>
      <RedRule width={120} />
      <div style={{ fontSize: 34, color: T.slate, marginTop: 20 }}>{d.who}</div>
    </Frame>
  );
};

type Word = { w: string; s: number; e?: number };
const norm = (w: string) => w.toLowerCase().replace(/[^a-z0-9$%']/g, "");

/** Тайминги слов цитаты: ищем её токены в озвучке внутри окна сцены. Не нашли (цитату пересказали) — равномерно 2.6 слова/с. */
const quoteTimes = (text: string, words: Word[], start: number, end: number): number[] => {
  const toks = text.split(/\s+/).filter(Boolean);
  const pool = words.map((w, i) => ({ i, n: norm(w.w), s: w.s })).filter((w) => w.s >= start - 1.5 && w.s <= end + 1);
  const q = toks.map(norm);
  for (let a = 0; a < pool.length; a++) {
    if (pool[a].n !== q[0]) continue;
    const times: number[] = []; let k = a;
    for (let j = 0; j < q.length; j++) {
      while (k < pool.length && pool[k].n !== q[j] && k - a < j + 6) k++;
      if (k >= pool.length || pool[k].n !== q[j]) break;
      times.push(pool[k].s); k++;
    }
    if (times.length >= Math.ceil(q.length * 0.8)) {
      while (times.length < q.length) times.push(times[times.length - 1] + 0.3);
      return times.map((t) => t - start);
    }
  }
  return toks.map((_, i) => 0.6 + i / 2.6);
};

/** Цитата-сцена story-формата (владелец 21.09): слева проверенный портрет автора в бумажной рамке, справа текст, который ПЕЧАТАЕТСЯ
 *  по буквам вслед за голосом — будущего текста не видно, курсор мигает; после последней буквы курсор гаснет и под линией
 *  проявляются имя · роль · год. Место под весь текст резервируется невидимой копией, блок не прыгает. */
export const QuoteScene: React.FC<{ d: any; slots: SlotT[]; words?: Word[]; sceneStart?: number; sceneEnd?: number }> = ({ d, slots, words = [], sceneStart = 0, sceneEnd = 0 }) => {
  const f = useCurrentFrame(); const { fps, durationInFrames } = useVideoConfig();
  const t = f / fps;
  const text: string = String(d.text ?? "");
  const toks = text.split(/\s+/).filter(Boolean);
  const times = quoteTimes(text, words, sceneStart, sceneEnd || sceneStart + durationInFrames / fps);
  // слово начинает печататься в момент произнесения и дописывается чуть быстрее речи (≤ 45 мс на букву)
  let shown = "";
  let done = false;
  toks.forEach((w, i) => {
    const chunk = (i ? " " : "") + w;
    const next = times[i + 1] ?? times[i] + 0.5;
    const per = Math.min(0.045, ((next - times[i]) * 0.8) / chunk.length);
    const n = Math.max(0, Math.min(chunk.length, Math.floor((t - times[i]) / per) + (t >= times[i] ? 1 : 0)));
    shown += chunk.slice(0, n);
    if (i === toks.length - 1 && n >= chunk.length) done = true;
  });
  const lastT = (times[times.length - 1] ?? 0) + 0.6;
  const att = interpolate(t, [lastT, lastT + 0.5], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const cursorOn = !done && Math.floor(t / 0.4) % 2 === 0;
  const enter = spring({ frame: f, fps, config: { damping: 200, stiffness: 80 } });
  const out = interpolate(f, [durationInFrames - 14, durationInFrames - 2], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const por = slots.find((s) => s.role === "portrait" && (s.image || s.src)) ?? slots.find((s) => s.image || s.src);
  const portraitNote = por?.caption && /historical portrait|\b\d{4} portrait/i.test(por.caption)
    ? por.caption.replace(`${d.who}, `, "").replace(/historical portrait/i, "Historical portrait · undated") : "";
  const size = toks.length > 22 ? 50 : toks.length > 14 ? 58 : 68;
  const who = fitRole(d.role, d.year ? String(d.year) : "", 40);
  const PW = 470, PH = 590;
  // Let the paper frame hug the source portrait, as in People. A fixed cover
  // box crops the head off a tall attributed family-photo crop.
  const portraitAspect = por?.aspect || PW / PH;
  const photoW = Math.min(PW, PH * portraitAspect);
  const photoH = Math.min(PH, PW / portraitAspect);
  if (D.flat) {   // cinético: слова крупно по центру, суммы жёлтым; портрет — кружок с жёлтой рамкой внизу слева
    const toks2 = shown.split(" ");
    return (
      <AbsoluteFill style={{ background: D.dark, opacity: out }}>
        {por && <div style={{ position: "absolute", left: D.pad, bottom: D.pad, width: 150, height: 150, borderRadius: "50%", overflow: "hidden", border: `5px solid ${D.ox}`, opacity: enter }}>
          <Slot slot={por} fit="cover" w={150} h={150} push={[1, 1]} /></div>}
        <div style={{ position: "absolute", left: D.pad * 2, right: D.pad * 2, top: 0, bottom: 0, display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", textAlign: "center" }}>
          <div style={{ fontFamily: D.mono, fontWeight: 700, fontSize: 30, letterSpacing: 8, color: D.ox, marginBottom: 30, opacity: enter }}>{D.words.quote}</div>
          <div style={{ position: "relative", fontFamily: "Anton, Impact, sans-serif", fontSize: Math.min(110, size * 1.5), lineHeight: 1.08, letterSpacing: 2, color: D.text, textTransform: "uppercase" }}>
            <div style={{ visibility: "hidden" }}>{text.toUpperCase()}</div>
            <div style={{ position: "absolute", left: 0, top: 0, right: 0 }}>
              {toks2.map((w, k) => <span key={k} style={{ color: /[\d$%]/.test(w) ? D.ox : D.text }}>{w}{k < toks2.length - 1 ? " " : ""}</span>)}
              <span style={{ display: "inline-block", width: 6, height: "0.9em", background: D.ox, marginLeft: 8, verticalAlign: "-0.1em", opacity: cursorOn ? 1 : 0 }} />
            </div>
          </div>
          <div style={{ marginTop: 44, fontFamily: D.mono, fontWeight: 700, fontSize: 30, letterSpacing: 5, color: D.muted, textTransform: "uppercase", opacity: att }}>{d.who}{who ? " · " + who : ""}</div>
        </div>
      </AbsoluteFill>
    );
  }
  return (
    <AbsoluteFill style={{ background: D.dark, opacity: out }}>
      <div style={{ position: "absolute", left: D.pad, top: D.pad * 1.45, fontFamily: D.mono, fontSize: 24, letterSpacing: 4, color: D.ox, background: D.cream, padding: "6px 16px", opacity: enter }}>{D.words.quote}</div>
      {por && (
        <div style={{ position: "absolute", left: D.pad + 20 + (PW - photoW) / 2, top: (1080 - photoH - 60) / 2, width: photoW + 28, padding: "14px 14px 56px", background: D.photo, boxShadow: "0 18px 48px rgba(0,0,0,.5)",
          transform: `rotate(-2deg) translateY(${(1 - enter) * 30}px)`, opacity: enter }}>
          <div style={{ width: photoW, height: photoH, overflow: "hidden", position: "relative" }}><Slot slot={por} fit="cover" w={photoW} h={photoH} push={[1, 1.02]} matte={false} vignette={false} /></div>
          {portraitNote && <div style={{ position: "absolute", left: 14, right: 14, bottom: 15, fontFamily: D.mono, fontSize: 20, color: D.brown, textAlign: "center" }}>{portraitNote}</div>}
        </div>
      )}
      <div style={{ position: "absolute", left: por ? D.pad + PW + 150 : D.pad * 2, right: D.pad * 1.2, top: 0, bottom: 0, display: "flex", flexDirection: "column", justifyContent: "center" }}>
        <div style={{ fontFamily: D.serif, fontSize: 190, lineHeight: 0.6, height: 96, color: D.ox, opacity: enter }}>“</div>
        <div style={{ position: "relative", fontFamily: D.serif, fontSize: size, lineHeight: 1.3, color: D.text }}>
          <div style={{ visibility: "hidden" }}>{text}</div>
          <div style={{ position: "absolute", left: 0, top: 0, right: 0 }}>
            {shown}<span style={{ display: "inline-block", width: 4, height: size * 0.9, background: D.ox, marginLeft: 6, verticalAlign: "-0.12em", opacity: cursorOn ? 1 : 0 }} />
          </div>
        </div>
        <div style={{ marginTop: 40, borderTop: `2px solid ${D.rule}`, paddingTop: 22, opacity: att, transform: `translateY(${(1 - att) * 10}px)` }}>
          <div style={{ fontFamily: D.serif, fontSize: 44, color: D.text }}>{d.who}</div>
          {who && <div style={{ fontFamily: D.mono, fontSize: 24, letterSpacing: 3, color: D.muted, marginTop: 8, textTransform: "uppercase" }}>{who}</div>}
        </div>
      </div>
    </AbsoluteFill>
  );
};
