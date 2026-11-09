import { T } from "../theme";
import { Frame, RedRule, useEnter, Caption, Layout } from "./common";

/** Заголовок берётся из первого непустого поля — модель кладёт текст под разными ключами; если нет ничего — подпись становится заголовком. */
export const titleText = (d: any, caption?: string) =>
  [d?.text, d?.title, d?.headline, d?.label, d?.value, caption].find((x) => typeof x === "string" && x.trim()) ?? "";

export const Title: React.FC<{ d: any; caption?: string } & Layout> = ({ d, caption, vertical, card }) => {
  const s = useEnter();
  const text = titleText(d, caption);
  const showCaption = caption && caption !== text;
  return (
    <Frame vertical={vertical} card={card}>
      <div style={{ fontFamily: T.display, fontWeight: 500, fontSize: vertical || card ? 84 : 120, lineHeight: 1.02, letterSpacing: -3,
        maxWidth: vertical || card ? 900 : 1500, opacity: s, transform: `translateY(${(1 - s) * 24}px)` }}>
        {text}
      </div>
      <RedRule />
      <Caption text={showCaption ? caption : undefined} vertical={vertical} card={card} />
    </Frame>
  );
};
