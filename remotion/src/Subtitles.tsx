import { useEffect, useState } from "react";
import { continueRender, delayRender, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Scene, T, Word } from "./theme";
import { D } from "./dossier";

/** Субтитры фразами по 5–7 слов; текущее слово подчёркнуто красным.
 *  Поверх инфографики — без плашки (контент не заходит в нижнюю полосу, см. Frame);
 *  поверх B-roll — на бумажной полосе, иначе чернила теряются на видео.
 *  Слова приходят в props; если их нет — грузим words.json из public dir. */
export const Subtitles: React.FC<{ words?: Word[]; scenes?: Scene[]; offset?: number; vertical?: boolean }> =
  ({ words: given, scenes = [], offset = 0, vertical }) => {
  const [loaded, setLoaded] = useState<Word[]>([]);
  useEffect(() => {
    if (given) return;
    const h = delayRender("words.json");
    fetch(staticFile("words.json")).then((r) => r.json()).then((w) => { setLoaded(w); continueRender(h); })
      .catch(() => { setLoaded([]); continueRender(h); });
  }, [given]);
  const words = given ?? loaded;
  const t = useCurrentFrame() / useVideoConfig().fps + offset;
  if (!words.length) return null;
  const i = words.findIndex((w) => t >= w.s && t < w.e + 0.15);
  const cur = i === -1 ? words.findIndex((w) => w.s > t) : i;
  if (cur === -1) return null;
  const n = vertical ? 4 : 7;
  const group = words.slice(Math.floor(cur / n) * n, Math.floor(cur / n) * n + n);
  const onVideo = scenes.some((s) => ((s.type.startsWith("broll") && s.src) || s.image) && t >= s.start && t < s.end);
  if (D.flat) {   // cinético: вшитые субтитры для телефона без звука — текущее слово и суммы жёлтым; фразы режутся по знакам препинания
    const hot = (w: Word) => w === words[i] || /[\d$%]/.test(w.w);
    // фразы фиксированы заранее (23.09: окно ползло за текущим словом): клауза по знакам препинания, длинная — равными кусками ≤6 слов
    const MAXW = 6;
    let a = cur, b = cur;
    while (a > 0 && !/[.!?;:,…]$/.test(words[a - 1].w)) a--;
    while (b < words.length - 1 && !/[.!?;:,…]$/.test(words[b].w)) b++;
    const n = b - a + 1, parts = Math.ceil(n / MAXW), per = Math.ceil(n / parts);
    const k = Math.floor((cur - a) / per);
    // граница куска не должна падать на артикль, предлог или голое число — иначе субтитр читается как оборванный
    const STOP = /^(el|la|los|las|un|una|unos|unas|del|de|al|a|en|y|o|que|con|por|para|su|sus|the|an|of|to|in|and|or|for|with|at|on|its|his|her)$/i;
    let s0 = a + k * per, e0 = Math.min(b, a + (k + 1) * per - 1);
    while (e0 < b && (STOP.test(words[e0].w.replace(/[^\p{L}]/gu, "")) || /^\d+$/.test(words[e0].w))) e0++;
    const phrase = words.slice(s0, e0 + 1);
    return (
      <div style={{ position: "absolute", left: 0, right: 0, bottom: vertical ? "24%" : 64, textAlign: "center", padding: "0 160px" }}>
        <span style={{ display: "inline-block", fontFamily: D.sans ?? D.serif, fontWeight: 700, fontSize: vertical ? 64 : 46, lineHeight: 1.2, color: "#FFFFFF",
          textShadow: "0 2px 4px rgba(0,0,0,.9), 0 0 24px rgba(0,0,0,.8)", textTransform: "uppercase", letterSpacing: 1 }}>
          {phrase.map((w, k) => <span key={k} style={{ marginRight: 16, color: hot(w) ? "#FFD500" : "#FFFFFF" }}>{w.w}</span>)}
        </span>
      </div>
    );
  }
  return (
    <div style={{ position: "absolute", left: 0, right: 0, bottom: vertical ? "24%" : T.pad, textAlign: "center", padding: `0 ${T.pad}px` }}>
      <span style={{
        display: "inline-block", fontSize: vertical ? 64 : 44, fontWeight: 500, lineHeight: 1.25, color: T.ink,
        background: onVideo ? T.paper : "transparent", padding: onVideo ? "10px 28px 12px" : 0,
      }}>
        {group.map((w, k) => (
          <span key={k} style={{ marginRight: 14, boxShadow: w === words[i] ? `0 6px 0 ${T.red}` : "none" }}>{w.w}</span>
        ))}
      </span>
    </div>
  );
};
