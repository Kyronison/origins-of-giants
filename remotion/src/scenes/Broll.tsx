import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { Slot as SlotT, T } from "../theme";
import { Slot, yearOf } from "./Slot";
import { D, Tag } from "../dossier";

/** Полный кадр на Slot (§2.2). Подпись архива — «карточка архива»: бумажная плашка слева внизу, две строки
 *  (имя/предмет Fraunces 30, год Inter 22 slate), красная линия 3 px за 10 кадров; кредит мелко справа внизу первые 5 с.
 *  Подпись печатается (40 симв/с) и уходит через CAPTION_SEC. Зерно здесь не рисуем — оно на слое Film. */
export const CAPTION_SEC = 5;
export const TYPE_CPS = 40;

/** «Homestead High School, 1971» → имя + год; «Mountain View, 1960s», «c. 1955», «1976–1977» тоже. */
export const splitCaption = (caption: string, year?: number | null): [string, string] => {
  const m = caption.match(/^(.*?)[,\s]+((?:c\.\s*)?\d{4}s?(?:\s*[–-]\s*\d{2,4})?)$/);
  if (m) return [m[1].trim(), m[2].trim()];
  return [caption.trim(), year ? String(year) : ""];
};

export const Broll: React.FC<{ slot?: SlotT; caption?: string; captionDelay?: number; motion?: string; vertical?: boolean; w?: number; h?: number }> =
  ({ slot, caption, captionDelay = 0, motion, vertical, w, h }) => {
  const f = useCurrentFrame(); const { fps } = useVideoConfig();
  // Short: верхняя область 1080×(58 % от 1920) — бокс contain считается от неё, а не от 1920×1080
  w = w ?? (vertical ? 1080 : 1920); h = h ?? (vertical ? 1114 : 1080);
  const s = slot ?? { caption };
  const text = caption ?? s.caption ?? "";
  const archive = s.kind === "archive";
  const c0 = Math.round(captionDelay * fps), c1 = c0 + Math.round(CAPTION_SEC * fps);
  const capO = interpolate(f, [c0, c0 + fps * 0.25, c1 - fps * 0.4, c1], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const typed = Math.max(0, Math.floor(((f - c0) / fps) * TYPE_CPS));
  // год из подписи; иначе год снимка Commons — но только для снимков эпохи: современное фото музейного предмета (2008) датирует не предмет
  const [name, year] = archive ? splitCaption(text, s.year && s.year < 2000 ? s.year : yearOf(text)) : [text, ""];
  const nameT = name.slice(0, typed), yearT = year.slice(0, Math.max(0, typed - name.length - 2));
  const credO = archive && s.credit ? interpolate(f, [c0, c0 + fps * 0.5, c1 - fps * 0.5, c1], [0, 0.92, 0.92, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) : 0;
  const left = vertical ? 48 : T.pad, bottom = vertical ? "32%" : T.pad + 110;
  return (
    <Slot slot={s} motion={motion} w={w} h={h} fit={s.fit ?? "auto"} push={s.fit === "contain" ? [1, 1] : undefined} drift={s.fit !== "contain"}>
      {text && capO > 0 && (
        <div style={{ position: "absolute", left, bottom, opacity: capO, transform: `translateY(${(1 - capO) * 8}px)` }}>
          <Tag rotate={archive ? 0.8 : -0.6} style={{ padding: "14px 24px 14px", minWidth: 240, maxWidth: 820 }}>
            <div style={{ fontFamily: D.mono, fontWeight: 700, fontSize: vertical ? 32 : 27, letterSpacing: 1.2, textTransform: "uppercase", lineHeight: 1.25, minHeight: 34 }}>{archive ? nameT : text.slice(0, typed)}</div>
            {archive && year && <div style={{ fontFamily: D.mono, fontSize: vertical ? 24 : 21, color: D.ox, letterSpacing: 1, marginTop: 4, minHeight: 26, textTransform: "uppercase" }}>{yearT}</div>}
          </Tag>
        </div>
      )}
      {credO > 0 && (
        // кредит под отпечатком, на тёмном поле, одной строкой — не поверх снимка
        <div style={{ position: "absolute", right: vertical ? 48 : T.pad, bottom: vertical ? "32%" : 34, fontFamily: D.mono, fontSize: 18, color: D.cream, opacity: credO,
          maxWidth: vertical ? 520 : 1100, whiteSpace: vertical ? "normal" : "nowrap", overflow: "hidden", textOverflow: "ellipsis",
          textAlign: "right", textShadow: "0 1px 6px rgba(0,0,0,.7)" }}>{s.credit}</div>
      )}
    </Slot>
  );
};
