import { RICH, Scene, Slot as SlotT, slotsOf, stripFactsDeep, stripFacts } from "../theme";
import { Title } from "./Title";
import { Stat } from "./Stat";
import { BarChart } from "./BarChart";
import { LineChart } from "./LineChart";
import { Compare } from "./Compare";
import { Quote, QuoteScene } from "./Quote";
import { Broll } from "./Broll";
import { Outro } from "./Outro";
import { Backdrop } from "./Backdrop";
import { People } from "./People";
import { MapScene } from "./MapScene";

const WIDE = new Set(["bar_chart", "line_chart", "compare"]);

/** Маршрутизация по scene.type (§6.1). Story: broll/people/map/chart (+ заглушки (B): split/montage/timeline/object → Broll на первом слоте);
 *  старые плоские сцены и неизвестный type → Broll на slotsOf(scene); vertical (Shorts) — богатые типы показывают slots[0] как Broll.
 *  Форматы news/anatomy (title/stat/bar_chart/line_chart/compare/quote/outro) — как раньше. */
export const SceneRouter: React.FC<{ scene: Scene; vertical?: boolean; words?: { w: string; s: number }[] }> = ({ scene, vertical, words }) => {
  const d = stripFactsDeep(scene.data ?? {}); const caption = scene.caption ? stripFacts(scene.caption) : undefined;
  const slots = slotsOf(scene);
  const first = slots.find((s) => s.src || s.image) ?? slots[0];
  const type = scene.type;
  const broll = (slot?: SlotT, cap?: string) => (
    <Broll slot={slot} caption={cap} captionDelay={scene.caption_delay} motion={scene.motion} vertical={vertical} />
  );
  if (type.startsWith("broll")) return broll(first, caption ?? first?.caption ?? undefined);
  if (vertical && RICH.has(type) && first) return broll(first, first.caption ?? caption);
  switch (type) {
    // первый кадр главы (dip): хореография богатой сцены стартует после карточки (caption_delay), под вуалью — статичная композиция
    case "people": return <People d={d} slots={slots} delay={scene.transition === "dip" ? scene.caption_delay : 0} sceneStart={scene.start} />;
    case "map": return <MapScene d={d} slots={slots} delay={scene.transition === "dip" ? scene.caption_delay : 0} />;
    case "chart": {
      const img = first?.image ?? scene.image;
      const inner = d.kind === "line" ? <LineChart d={d} caption={caption} card={!!img} vertical={vertical && !img} /> : <BarChart d={d} caption={caption} card={!!img} vertical={vertical && !img} />;
      return img ? <Backdrop image={img} wide>{inner}</Backdrop> : inner;
    }
    case "split": return broll(first, first?.caption ?? d.left?.label ?? caption);   // (B) Split.tsx
    case "montage": case "timeline": case "object": return broll(first, first?.caption ?? d.title ?? caption);   // (B)
    case "quote":   // story: портрет автора + текст печатается вслед за голосом (владелец 21.09); без текста — обычный кадр
      if (!d.text && first) return broll(first, first.caption ?? caption);
      if (d.text && d.persons) return <QuoteScene d={d} slots={slots} words={words} sceneStart={scene.start} sceneEnd={scene.end} />;
      break;
  }
  // фон-картинка + карточка: узкие сцены в «вертикальной» раскладке, широкие — в card (news/anatomy)
  if (scene.image && !vertical && OLD.has(type)) {
    const wide = WIDE.has(type);
    const inner = { d, caption, ...(wide ? { card: true } : { vertical: true }) };
    return <Backdrop image={scene.image} wide={wide}><Inner type={type} p={inner} /></Backdrop>;
  }
  if (!OLD.has(type) && first) return broll(first, first.caption ?? caption);   // неизвестный тип с медиа
  return <Inner type={type} p={{ d, caption, vertical }} />;
};

const OLD = new Set(["title", "stat", "bar_chart", "line_chart", "compare", "quote", "outro"]);

const Inner: React.FC<{ type: string; p: any }> = ({ type, p }) => {
  switch (type) {
    case "title": return <Title {...p} />;
    case "stat": return <Stat {...p} />;
    case "bar_chart": return <BarChart {...p} />;
    case "line_chart": return <LineChart {...p} />;
    case "compare": return <Compare {...p} />;
    case "quote": return <Quote {...p} />;
    case "outro": return <Outro {...p} />;
    default: return <Title {...p} />;   // неизвестный тип без медиа — хотя бы текст, а не пустой кадр
  }
};
