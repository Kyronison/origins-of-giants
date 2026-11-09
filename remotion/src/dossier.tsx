import { loadFont as loadCaslon } from "@remotion/google-fonts/LibreCaslonText";
import { loadFont as loadCourier } from "@remotion/google-fonts/CourierPrime";
import { loadFont as loadGrotesk } from "@remotion/google-fonts/SpaceGrotesk";

/** «Архивное досье» — оформление story-формата, выбор владельца 16.09 (вариант 2 со доски стилей):
 *  машинопись Courier Prime на кремовых бумажных ярлыках, имена и цифры — антиква Libre Caslon, фото в белых рамках с лёгким наклоном,
 *  акцент — тёмно-красный (оксблад) вместо яркого красного. Legacy-форматы и бренд остаются на T (theme.ts). */
const cs = loadCaslon("normal", { weights: ["400", "700"], subsets: ["latin"] });
const cp = loadCourier("normal", { weights: ["400", "700"], subsets: ["latin"] });
const gk = loadGrotesk("normal", { weights: ["500", "700"], subsets: ["latin"] });

export const D = {
  cream: "#EFE6D2",      // бумага ярлыка
  photo: "#F6F1E6",      // рамка фотографии
  brown: "#2B2118",      // чернила машинописи
  ox: "#7A2E1F",         // акцент: возраст, годы, подписи цифр
  dark: "#1B1511",       // фон композиций (тёплый почти чёрный)
  muted: "#A8977F",      // вторичный текст на тёмном
  rule: "#5A4A3C",       // тонкие линии на тёмном
  land: "#D3C4A7", coast: "#8A7760", grid: "#B9A98E",   // карта
  serif: cs.fontFamily,
  mono: cp.fontFamily,
  pad: 96,
  flat: false,           // neon: без наклона ярлыков и бумажной разлиновки
  text: "#EFE6D2",       // светлый текст на тёмном фоне (цитаты, пара, леджер)
  sans: undefined as string | undefined,   // neon: гротеск для субтитров и цифр
  words: { and: "and", quote: "QUOTE", file: "FILE No.", born: "born" },   // служебные слова в кадре — по языку канала
};

const DOSSIER = { ...D };
/** Второй канал, направление «Neón» (владелец 22.09): синие карточки с жёлтой рамкой, гротеск вместо антиквы и машинописи. */
const NEON = { cream: "#0B1B33", photo: "#FFD500", brown: "#FFFFFF", ox: "#FFD500", dark: "#071224", muted: "#9FB0C8", rule: "#24406A",
  land: "#1E3A5F", coast: "#FFD500", grid: "#2C4A75", serif: gk.fontFamily, mono: gk.fontFamily, pad: 96, flat: true,
  text: "#FFFFFF", sans: gk.fontFamily, words: { and: "y", quote: "CITA", file: "CAPÍTULO", born: "n." } };
/** Палитра переключается один раз на рендер в Main (timeline.theme); D — общий объект, его читают все сцены и титры при отрисовке. */
/** Испанский мультфильм (владелец 13.10): бумажное досье под рисунок, служебные слова по-испански. */
const DOSSIER_ES = { ...DOSSIER, words: { and: "y", quote: "CITA", file: "CAPÍTULO", born: "n." } };
export const applyTheme = (theme?: string) => { Object.assign(D, theme === "neon" ? NEON : theme === "dossier_es" ? DOSSIER_ES : DOSSIER); };

/** Бумажный ярлык: кремовая бумага с едва заметной разлиновкой, тень, наклон. */
export const Tag: React.FC<{ children: React.ReactNode; style?: React.CSSProperties; rotate?: number }> = ({ children, style, rotate = 0 }) => (
  <div style={{ background: D.cream, color: D.brown, boxShadow: "0 12px 34px rgba(0,0,0,.42)", padding: "16px 24px",
    backgroundImage: D.flat ? undefined : "linear-gradient(rgba(122,46,31,.06) 1px, transparent 1px)", backgroundSize: "100% 30px",
    border: D.flat ? `3px solid ${D.ox}` : undefined, borderRadius: D.flat ? 10 : undefined,
    transform: rotate && !D.flat ? `rotate(${rotate}deg)` : undefined, ...style }}>{children}</div>
);

/** Двойная линия под заголовком (как на машинописном бланке). */
export const DoubleRule: React.FC<{ width: number; color?: string; style?: React.CSSProperties }> = ({ width, color = D.brown, style }) => (
  <div style={{ borderTop: `2px solid ${color}`, borderBottom: `2px solid ${color}`, height: 5, width, ...style }} />
);
