import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { Slot as SlotT, T } from "../theme";
import { Slot } from "./Slot";
import { D as DS, Tag } from "../dossier";

/** people (§2.3): 1–3 колонки на ink-фоне. Колонка — портрет на бумажной рамке 10 px, под ним постоянная плашка
 *  имя · роль · годы с красной линией. На 45 % сцены (не раньше f70) портрет уходит шторкой вверх и открывает иллюстрацию занятия.
 *  Solo: портрет слева 40 %, справа занятие 60 %. Между колонками rule 2 px и «and» (duo).
 *  `delay` — первый кадр главы под карточкой: въезд колонок начинается после проявления (иначе анимация отыгрывает под вуалью).
 *  Плашки уходят за PLATE_OUT кадров до конца Sequence (наплыв следующей сцены), чтобы не стоять под чужой подписью. */
type Person = { name?: string; role?: string; years?: string; side?: string; portrait?: number | null; activity?: number | null;
  age?: string; age_t?: number };   // возраст из озвучки («Jobs is 21») и абсолютная секунда, когда он звучит

/** «1950–» (жив) → «born 1950»; «1922–1993» и «1922–93» как есть; одиночный год → «born 1950». Владелец: незакрытый интервал читался как обрыв. */
/** Должность + год в одну строку плашки: длинная должность («CEO, operations manager, architect») съедала год — Copart 26.09. */
export const fitRole = (role?: string, tail?: string, max = 30): string => {
  let r = String(role || "").trim();
  const join = (x: string) => [x, tail].filter(Boolean).join(" · ");
  if (join(r).length > max) r = r.split(/[,;/]/)[0].trim();
  if (join(r).length > max) r = r.slice(0, Math.max(0, max - (tail ? tail.length + 3 : 0))).trim();
  return join(r);
};
export const yearsLabel = (years: string): string => {
  const s = years.trim();
  const open = s.match(/^(?:b\.?\s*|born\s+)?(\d{4})\s*[–-]?\s*$/i);
  if (open) return `${DS.words.born} ${open[1]}`;
  return s;
};
const W = 1920, H = 1080, PAD = T.pad, TOP = 86, BOTTOM = H - 86, PLATE = 150, GAP = 24;
const PLATE_OUT = 18;   // = наплыв следующей богатой сцены (XFADE_RICH_SEC 0.6 с): плашки уходят ровно под наплывом, а не раньше него

const columns = (d: any, slots: SlotT[]): { person: Person; portrait?: SlotT; activity?: SlotT }[] => {
  const persons: Person[] = (d.persons ?? []).slice(0, 3);
  const portraits = slots.filter((s) => s.role !== "activity" && s.role !== "backdrop");
  const acts = slots.filter((s) => s.role === "activity");
  const cols = persons.map((p, i) => {
    const por = typeof p.portrait === "number" ? slots[p.portrait] : p.portrait === null ? undefined : portraits[i];   // null — портрета нет: не подставлять чужой (Клара получала фото Пола)
    const act = typeof p.activity === "number" ? slots[p.activity] : p.activity === null ? undefined : acts[i];
    return { person: p, portrait: por?.image || por?.src ? por : undefined, activity: act?.image || act?.src ? act : undefined };
  });
  // «она слева, он справа» — по side; без side — порядок persons
  const left = cols.filter((c) => c.person.side === "left"), right = cols.filter((c) => c.person.side === "right");
  const rest = cols.filter((c) => c.person.side !== "left" && c.person.side !== "right");
  return persons.length > 1 && (left.length || right.length) ? [...left, ...rest, ...right] : cols;
};

export const People: React.FC<{ d: any; slots: SlotT[]; delay?: number; sceneStart?: number }> = ({ d, slots, delay = 0, sceneStart = 0 }) => {
  const f0 = useCurrentFrame(); const { fps, durationInFrames } = useVideoConfig();
  const D = Math.max(0, Math.round(delay * fps));
  // под карточкой композиция стоит уже собранной (колонки въехали, портреты положены — кадр HOLD), пустого ink-фона под вуалью нет;
  // после проявления хореография продолжается с HOLD: плашки поднимаются, красная линия, шторка
  const HOLD = 26;
  const f = D > 0 ? (f0 < D ? HOLD : f0 - D + HOLD) : f0;
  const cols = columns(d, slots);
  if (!cols.length) return <AbsoluteFill style={{ background: DS.dark }} />;
  const layout: string = d.layout ?? (cols.length === 1 ? "solo" : cols.length === 2 ? "duo" : "trio");
  const solo = layout === "solo" || cols.length === 1;
  const n = cols.length;
  const inner = W - 2 * PAD;
  const gap = n === 3 ? 80 : 120;
  const colW = solo ? Math.round(inner * 0.4) : (inner - gap * (n - 1)) / n;
  const wipeAt = Math.max(70, Math.round(0.45 * (durationInFrames - D)));
  const plateOut = interpolate(f0, [durationInFrames - PLATE_OUT, durationInFrames - 2], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ background: DS.dark }}>
      {solo && cols[0].activity && (
        <SoloActivity slot={cols[0].activity} x={PAD + colW + 48} w={W - PAD - (PAD + colW + 48)} hasPortrait={!!cols[0].portrait} f={f} />
      )}
      {cols.map((c, i) => (
        <Column key={i} c={c} i={i} x={PAD + i * (colW + gap)} w={colW} wipeAt={solo ? -1 : wipeAt} f={f} plateOut={plateOut} noImage={solo && !c.portrait && !!c.activity}
          ageFrame={c.person.age && c.person.age_t != null ? Math.round((c.person.age_t - sceneStart) * fps) : null} f0={f0} />
      ))}
      {!solo && cols.slice(1).map((_, i) => {
        const x = PAD + (i + 1) * (colW + gap) - gap / 2;
        const o = interpolate(f, [12 + i * 10, 30 + i * 10], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
        return (
          <div key={i} style={{ position: "absolute", left: x - 1, top: TOP + 40, bottom: H - BOTTOM + 40, width: 2, background: DS.rule, opacity: 0.6 * o }}>
            {n === 2 && <div style={{ position: "absolute", top: -34, left: "50%", transform: "translateX(-50%)", fontFamily: DS.mono, fontSize: 22, letterSpacing: 4,
              color: DS.muted, opacity: 0.8 * o, background: DS.dark, padding: "0 12px" }}>{DS.words.and.toUpperCase()}</div>}
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

/** Колонка: въезжает clip-path слева (f0–18, правая с f10), портрет «кладётся» с f14/f24, плашка с f28/f38. f — кадр хореографии (с учётом delay). */
const Column: React.FC<{ c: { person: Person; portrait?: SlotT; activity?: SlotT }; i: number; x: number; w: number; wipeAt: number; f: number; plateOut: number;
  noImage?: boolean;   // solo без портрета: иллюстрация занятия уже стоит справа (SoloActivity) — в колонке бумажная карточка, а не дубль картинки
  ageFrame?: number | null; f0?: number }> =   // возраст появляется в плашке своей колонки в кадр, когда диктор его называет
  ({ c, i, x, w, wipeAt, f, plateOut, noImage, ageFrame, f0 = 0 }) => {
  const { fps } = useVideoConfig();
  const d = i * 10;
  const enter = spring({ frame: f - d, fps, config: { damping: 200, stiffness: 110 } });
  const clip = `inset(0 ${((1 - enter) * 100).toFixed(2)}% 0 0)`;
  const areaH = BOTTOM - TOP - PLATE - GAP;
  const hasP = !!c.portrait;
  const place = spring({ frame: f - 14 - d, fps, config: { damping: 16, stiffness: 150 } });
  const placeO = interpolate(f, [14 + d, 22 + d], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const plateO = interpolate(f, [28 + d, 38 + d], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  // шторка на занятие: портрет уходит вверх за 18 кадров, иллюстрация проявляется кросс-диссолвом 0.6 с
  const wiping = false && hasP && !!c.activity && wipeAt > 0;   // владелец 16.09: сцена мельтешила — портрет стоит всю сцену
  const wipe = wiping ? interpolate(f, [wipeAt, wipeAt + 18], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) : 0;
  const roleLine = spring({ frame: f - (wiping ? wipeAt : 40 + d), fps, config: { damping: 200, stiffness: 120 } });
  // бокс портрета — рамка обнимает фото (contain), не колонку
  const aspect = c.portrait?.aspect ?? 0.8;
  const mW = w - 20, mH = areaH - 20;
  const [bw, bh] = aspect >= mW / mH ? [mW, mW / aspect] : [mH * aspect, mH];
  const tilt = i % 2 ? 1 : -1.2;   // фото «брошены» на стол досье
  const p = c.person;
  const portraitNote = c.portrait?.caption && /historical portrait|\b\d{4} portrait/i.test(c.portrait.caption)
    ? c.portrait.caption.replace(`${p.name}, `, "").replace(/historical portrait/i, "Historical portrait · undated") : "";
  const FR = 16, FRB = 46;          // белая рамка фотографии: поля и нижнее поле, как у отпечатка
  const [pw, ph] = [Math.min(bw, w - 2 * FR), Math.min(bh, areaH - FR - FRB)];
  const age = p.age && ageFrame != null ? spring({ frame: f0 - Math.max(0, ageFrame), fps, config: { damping: 200, stiffness: 140 } }) : 0;
  return (
    <div style={{ position: "absolute", left: x, top: TOP, width: w, height: BOTTOM - TOP, clipPath: clip }}>
      <div style={{ position: "absolute", left: 0, top: 0, width: w, height: areaH }}>
        {noImage && (
          <div style={{ position: "absolute", left: 10, top: 10, right: 10, bottom: 10, background: DS.cream, boxShadow: "0 18px 50px rgba(0,0,0,.45)", opacity: placeO,
            transform: `scale(${0.94 + 0.06 * place}) rotate(${tilt}deg)`, display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden" }}>
            <div style={{ fontFamily: DS.serif, fontSize: Math.round(w * 0.5), lineHeight: 1, color: DS.brown, opacity: 0.14, userSelect: "none" }}>
              {(p.name ?? "?").trim().charAt(0).toUpperCase()}
            </div>
          </div>
        )}
        {!noImage && c.activity && (hasP ? wipe > 0 : true) && (
          <div style={{ position: "absolute", left: (w - pw) / 2 - FR, top: FR / 2, width: pw + 2 * FR, height: areaH - FR, background: DS.photo, opacity: hasP ? wipe : placeO,
            boxShadow: "0 18px 50px rgba(0,0,0,.45)", transform: `scale(${0.94 + 0.06 * place}) rotate(${tilt}deg)` }}>
            <div style={{ position: "absolute", left: FR, top: FR, right: FR, bottom: FRB, overflow: "hidden" }}>
              <Slot slot={c.activity} fit="cover" w={pw} h={areaH - FR - FRB} push={[1, 1.05]} matte={false} vignette={false} />
            </div>
          </div>
        )}
        {hasP && wipe < 1 && (
          <div style={{ position: "absolute", left: (w - pw) / 2 - FR, top: (areaH - ph) / 2 - FR, width: pw + 2 * FR, height: ph + FR + FRB, background: DS.photo,
            boxShadow: "0 18px 50px rgba(0,0,0,.45)", opacity: placeO, transform: `scale(${0.94 + 0.06 * place}) rotate(${tilt}deg)` }}>
            <div style={{ position: "absolute", left: FR, top: FR, width: pw, height: ph, overflow: "hidden" }}>
              <Slot slot={c.portrait!} fit="cover" w={pw} h={ph} push={[1, 1.05]} matte={false} vignette={false} />
            </div>
            {portraitNote && <div style={{ position: "absolute", left: FR, right: FR, bottom: 7, fontFamily: DS.mono, fontSize: 17, lineHeight: 1.1, color: DS.brown, textAlign: "center" }}>{portraitNote}</div>}
          </div>
        )}
      </div>
      <div style={{ position: "absolute", left: 0, top: areaH + GAP - 6, opacity: plateO * plateOut, transform: `translateY(${(1 - plateO) * 12}px)` }}>
        <Tag rotate={-tilt / 2} style={{ padding: "14px 24px 14px", minWidth: Math.min(420, w), maxWidth: Math.min(640, w) }}>
          <div style={{ fontFamily: DS.serif, fontSize: 38, lineHeight: 1.1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{p.name ?? ""}</div>
          {(p.role || p.years) && (
            <div style={{ fontFamily: DS.mono, fontSize: 20, letterSpacing: 1, marginTop: 6, textTransform: "uppercase", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {fitRole(p.role, p.years ? yearsLabel(p.years) : "")}
            </div>
          )}
          {p.age && ageFrame != null && (
            <div style={{ fontFamily: DS.mono, fontWeight: 700, fontSize: 28, color: DS.ox, marginTop: 8, opacity: age, transform: `translateY(${(1 - age) * 8}px)` }}>AGE {p.age}</div>
          )}
        </Tag>
      </div>
    </div>
  );
};

/** Solo: иллюстрация занятия справа во всю высоту, появляется вместе с портретом (или сразу, если портрета нет). */
const SoloActivity: React.FC<{ slot: SlotT; x: number; w: number; hasPortrait: boolean; f: number }> = ({ slot, x, w, hasPortrait, f }) => {
  const { fps } = useVideoConfig();
  const d = hasPortrait ? 10 : 0;
  const enter = spring({ frame: f - d, fps, config: { damping: 200, stiffness: 110 } });
  return (
    <div style={{ position: "absolute", left: x, top: TOP, width: w, height: BOTTOM - TOP, clipPath: `inset(0 ${((1 - enter) * 100).toFixed(2)}% 0 0)` }}>
      <Slot slot={slot} fit="cover" w={w} h={BOTTOM - TOP} push={[1, 1.05]} matte={false} />
    </div>
  );
};
