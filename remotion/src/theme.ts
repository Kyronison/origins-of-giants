import { loadFont as loadFraunces } from "@remotion/google-fonts/Fraunces";
import { loadFont as loadInter } from "@remotion/google-fonts/InterTight";

const fr = loadFraunces("normal", { weights: ["500", "600"], subsets: ["latin"] });
const it = loadInter("normal", { weights: ["400", "500", "600"], subsets: ["latin"] });

/** Ledger-on-paper: светлый холодный фон, чернила, один красный для цифры, которая важна. */
export const T = {
  paper: "#EDEFF2",
  ink: "#16191F",
  slate: "#6E7784",
  rule: "#C7CCD3",
  red: "#E63B2E",
  display: fr.fontFamily,
  text: it.fontFamily,
  fps: 30,
  pad: 96,
};

/** Слот — одно медиа сцены (docs/scene-grammar.md §2). Python дописывает после резолва src/image/kind/aspect/…;
 *  поля source/query/prompt — то, что выдала модель, Remotion их не читает. */
export type Slot = {
  fit?: "auto" | "contain" | "cover";
  id?: string;
  role?: string;                // portrait|activity|hero|backdrop|left|right|item|inset|main
  src?: string | null;          // видео (архив/сток/клип), путь относительно папки видео (public dir)
  image?: string | null;        // картинка (архив/сгенерированная)
  kind?: string | null;         // archive|image|stock — грейд и рамка
  aspect?: number | null;       // ширина/высота исходника; < 1.5 → contain на размытой подложке
  clip_seconds?: number | null; // длительность видео — для зацикливания
  credit?: string | null;
  caption?: string | null;      // «кто/что, год»
  focus_xy?: [number, number] | null;   // точка фокуса 0..1 — transform-origin наезда
  year?: number | null;         // год снимка — грейд по эпохе
  src_px?: [number, number] | null;   // размер исходника видео — плёнка на апскейле 480p слабее
  at?: number | null;           // секунда появления элемента относительно начала сцены (montage/map/timeline)
  source?: string; query?: string; query_alt?: string; prompt?: string; media?: string; focus?: string; anchor?: string;
};
/** xfade — наплыв (0.5 с, богатые сцены 0.35); cut — склейка с gate-dip; dip — первый кадр главы стартует под карточкой. */
export type Transition = "xfade" | "cut" | "dip";
export type Scene = {
  id: string; type: string; start: number; end: number; anchor?: string; caption?: string;
  slots?: Slot[];               // story: медиа сцены; у старых timeline нет — берём зеркало верхнего уровня (slotsOf)
  transition?: Transition | string;
  src?: string | null;          // относительный путь внутри папки видео (она же public dir Remotion)
  clip_seconds?: number | null; // длительность B-roll клипа — для зацикливания
  image?: string | null;        // сгенерированный фон сцены (public dir) — инфографика идёт на карточке поверх
  motion?: string;              // story: движение камеры (slow push in | slow pull out | pan left | pan right | static)
  kind?: string | null;         // "archive" — реальный кадр (фото Commons или фрагмент YouTube): другой грейд и рамка под 4:3
  aspect?: number | null;       // ширина/высота исходника — узкие архивные кадры показываем на размытой подложке
  credit?: string | null;
  caption_delay?: number;      // подпись кадра появляется с задержкой (после карточки главы)
  focus_xy?: [number, number] | null;
  year?: number | null;
  data: any;
};
export type Word = { w: string; s: number; e: number };
export type Pause = { part: number; name?: string; at: number; gap: number; word_index?: number };
export type Overlay = {
  type: "caption" | "flash" | "chapter" | "year" | "pair"; start: number; end: number;
  then?: string; now?: string; tagL?: string; tagR?: string;   // pair: главная цифра ролика «было → стало» на весь экран
  source?: string;               // flash: источник справа в строке-леджере («10-K», «S-1»)
  text?: string; value?: string; label?: string; n?: number;
  count?: boolean;              // flash: count-up (B), по умолчанию выключен
  from?: string;                // year: с какого года кроссфейд
  pause?: { at: number; gap: number } | null;   // chapter: карточка стоит в тишине над первым кадром главы
};
export type MusicTrack = { src: string; start: number; end: number; volume: number; mood?: string;
  offset?: number | null };       // секунда файла, с которой стартует трек (тихое интро пропускаем — Python по огибающей)
/** Плёнка (§4): strength 0 или film:null — слой не монтируется. */
export type Film = {
  strength: number; grain?: boolean; flicker?: boolean; scratches?: boolean; weave?: boolean; blur?: boolean; splice?: boolean;
  grain_strength?: number;     // 0..1: сила только зерна; 1 сохраняет прежний вид
  grade?: boolean;              // выцветший грейд на медиа (Film.GRADE + эпоха в Slot.gradeOf)
  vignette?: boolean;           // виньетка и окно гейта
  warmth?: boolean;             // (устарело, оставлено для старых timeline)
  fade?: boolean;               // молочная вуаль — приподнятые тени выцветшего отпечатка
  leaks?: boolean;              // засветки раз в ~30 с
  soft?: boolean;               // лёгкая мягкость оптики (blur 0.35 px на медиа)
};
/** Звуковая партитура (orchestrator/stages/sound.py, владелец 17.09: «музыка монотонная и всё время идёт»):
 *  музыка кусками под повороты сюжета с общей кривой громкости (dt с шагом: под речью ниже, в паузах выше, 0 — тишина перед поворотом и под живым звуком),
 *  эффекты по таймкодам и живой звук архива (диктор в это время молчит — пауза вставлена в voice). */
export type Score = {
  music: { src: string; start: number; end: number; offset?: number; gain: number; fade_in?: number; fade_out?: number }[];
  curve: { dt: number; v: number[] };
  sfx: { src: string; at: number; volume: number; dur?: number }[];
  live: { src: string; at: number; dur: number; volume: number }[];
};
export type Timeline = {
  scenes: Scene[]; duration: number; shorts: { start: number; end: number }[]; channel: string; title: string;
  format?: string;
  theme?: string;               // "neon" — второй канал (dossier.applyTheme)
  voice?: boolean;              // false — рендер без voice.mp3 (демо в Studio)
  voice_src?: string;           // другой файл голоса (демо-окно со вставленными паузами под живой звук)
  score?: Score | null;         // есть — вместо music_tracks и стингеров глав
  music?: string | null;        // один ambient-трек на всё видео (старый режим)
  music_volume?: number;
  music_tracks?: MusicTrack[];  // story: свой трек на каждую главу, границы — pauses.at
  sfx_chapter?: string | null;  // короткий акцент на появлении карточки главы
  sfx_volume?: number | null;   // громкость стингера под паузой (Python: на SFX_BELOW_DB ниже диктора), нет → 0.15
  sfx_offset?: number | null;   // секунда файла стингера, с которой он стартует (тихое вступление пропускается — атака сразу)
  overlays?: Overlay[];         // story: титры поверх кадров
  subtitles?: boolean;          // false — без субтитров (story-формат)
  pauses?: Pause[];             // story: паузы диктора на главах ([] у старых видео)
  film?: Film | null;           // story: плёнка; null/отсутствует → без плёнки (news/anatomy)
};

export const FILM_DEFAULTS: Required<Film> = { strength: 0.8, grain: true, grain_strength: 1, flicker: true, scratches: true, weave: true, blur: true, splice: false, grade: true, vignette: true, warmth: false, fade: true, leaks: false, soft: true };
/** Нормализованная плёнка или null, если её нет / сила 0. */
export const filmOf = (f?: Film | null): Required<Film> | null =>
  !f || !(f.strength > 0) ? null : { ...FILM_DEFAULTS, ...Object.fromEntries(Object.entries(f).filter(([, v]) => v !== undefined && v !== null)) } as Required<Film>;

/** Слоты сцены; старый плоский shot (src/image на верхнем уровне) → один слот-зеркало. */
export const slotsOf = (s: Scene): Slot[] => {
  if (s.slots?.length) return s.slots;
  if (!s.src && !s.image) return [];
  return [{ id: `${s.id}_s1`, role: "hero", src: s.src ?? null, image: s.image ?? null, kind: s.kind ?? (s.src ? "stock" : "image"),
    aspect: s.aspect ?? null, clip_seconds: s.clip_seconds ?? null, credit: s.credit ?? null, caption: s.caption ?? null,
    focus_xy: s.focus_xy ?? null, year: s.year ?? null }];
};
/** Богатые типы story-формата (сами въезжают плашками). */
export const RICH = new Set(["people", "map", "split", "timeline", "montage", "quote", "object", "chart"]);
/** Сцены идут внахлёст на XFADE секунд: следующая проявляется поверх предыдущей — единый видеоряд без жёстких склеек.
 *  Богатые — 0.6 с (config.XFADE_RICH_SEC): колонки people въезжают 18 кадров, короче наплыв давал провал в чернила между двумя people. */
export const XFADE_SEC = 0.5;
export const XFADE_RICH_SEC = 0.6;
/** Длительность наплыва на входе сцены (§2.12): cut/dip — 0, богатые — 0.6 с, остальное 0.5 с; неизвестное значение → xfade. */
export const xfadeSecOf = (s: Scene): number =>
  s.transition === "cut" || s.transition === "dip" ? 0 : RICH.has(s.type) ? XFADE_RICH_SEC : XFADE_SEC;
export type Props = { timeline: Timeline; words?: Word[]; segment?: { start: number; end: number } };
export type Concept = { headline: string; visual?: string; emotion?: string };

export const stripFacts = (s: string) => s.replace(/\s*[(\[]\s*F\d+(?:\s*,\s*F\d+)*\s*[)\]]/g, "").trim();
/** Та же чистка для всего объекта data сцены (кроме служебных полей). */
export const stripFactsDeep = (x: any, key?: string): any => {
  if (key === "fact_id" || key === "fact_ids" || key === "id" || key === "type") return x;
  if (typeof x === "string") return stripFacts(x);
  if (Array.isArray(x)) return x.map((i) => stripFactsDeep(i, key));
  if (x && typeof x === "object") return Object.fromEntries(Object.entries(x).map(([k, v]) => [k, stripFactsDeep(v, k)]));
  return x;
};
