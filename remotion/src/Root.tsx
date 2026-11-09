import { Composition, Still } from "remotion";
import { Main } from "./Main";
import { CartoonES, CartoonSpec } from "./CartoonES";
import { Short } from "./Short";
import { ShortHook, HookSpec } from "./ShortHook";
import { ThumbV } from "./ThumbV";
import { Thumb } from "./Thumb";
import { StyleBoard } from "./StyleBoard";
import { Avatar, Banner, Watermark, Brand } from "./Brand";
import { AvatarES, BannerES, WatermarkES } from "./BrandES";
import { T, Props, Timeline, Word } from "./theme";
import sampleTimeline from "../../data/videos/sample/timeline.json";
import sampleWords from "../../data/videos/sample/words.json";

/** Демо-раскадровка для Studio (`npm run studio` отдаёт data/videos/sample как public dir). */
const sample: Props = { timeline: sampleTimeline as Timeline, words: sampleWords as Word[] };

/** Холст всегда 1920×1080 / 1080×1920 — вся раскладка в абсолютных пикселях.
 *  Другое разрешение (720p, 4K) — через `--scale` при рендере, см. orchestrator/stages/render.py. */
const brand: Brand = { name: "Backsolve", mark: "B", tagline: "How the business actually makes money" };

export const Root = () => (
  <>
    <Composition id="Main" component={Main} fps={T.fps} width={1920} height={1080} defaultProps={sample}
      calculateMetadata={({ props }) => ({ durationInFrames: Math.ceil(props.timeline.duration * T.fps) })} />
    {/* испанский канал, конвейер es_cartoon (владелец 13.10): рисунок во весь кадр, смена ~4 с, без титров */}
    <Composition id="CartoonES" component={CartoonES} fps={T.fps} width={1920} height={1080}
      defaultProps={{ spec: { duration: 5, voice: "voice.mp3", shots: [] } as CartoonSpec }}
      calculateMetadata={({ props }) => ({ durationInFrames: Math.ceil(props.spec.duration * T.fps) })} />
    <Composition id="Short" component={Short} fps={T.fps} width={1080} height={1920}
      defaultProps={{ ...sample, segment: sample.timeline.shorts[0] ?? { start: 0, end: 10 } }}
      calculateMetadata={({ props }) => ({
        durationInFrames: Math.ceil(((props.segment?.end ?? 30) - (props.segment?.start ?? 0)) * T.fps),
      })} />
    {/* Shorts «новость → полное видео» (orchestrator/stages/shorts.py → shorts/sN/short.json) */}
    <Composition id="ShortHook" component={ShortHook} fps={T.fps} width={1080} height={1920}
      defaultProps={{ spec: { duration: 5, voice: "voice.mp3", shots: [], captions: [], flashes: [], end: { start: 3, line1: "FULL STORY", line2: "ON OUR CHANNEL" }, channel: "Origins of Giants" } as HookSpec }}
      calculateMetadata={({ props }) => ({ durationInFrames: Math.ceil(props.spec.duration * T.fps) })} />
    <Still id="ThumbV" component={ThumbV} width={1280} height={720}
      defaultProps={{ variant: "money", bw: "archive/thumb_src_bw1976.jpg", color: "archive/thumb_src_color1976.jpg", now: "shorts/s1/now_00.jpg", jobs: "archive/v3_1_2_p1.jpg", woz: "archive/v2_2_1_p2.jpg" }} />
    <Still id="Thumb" component={Thumb} width={1280} height={720}
      defaultProps={{ ...sample, concept: { headline: "75% margin", visual: "", emotion: "" }, image: "" }} />
    {/* оформление канала: data/channel/brand.props.json → `npm run brand` (см. data/channel/brand.md) */}
    <Still id="StyleBoard" component={StyleBoard} width={1920} height={1080}
      defaultProps={{ style: "ledger", scene: "people", left: "archive/board_jobs.jpg", right: "archive/v1_1_4_p2.jpg", photo: "archive/v3_2_1_p1.jpg" }} />
    <Still id="Avatar" component={Avatar} width={800} height={800} defaultProps={brand} />
    <Still id="Banner" component={Banner} width={2560} height={1440} defaultProps={brand} />
    <Still id="Watermark" component={Watermark} width={150} height={150} defaultProps={brand} />
    {/* второй канал, направление «Neón» (владелец 22.09) */}
    <Still id="AvatarES" component={AvatarES} width={800} height={800} defaultProps={{ name: "Orígenes de Gigantes", tagline: "Documentales sobre cómo se hizo el dinero" }} />
    <Still id="BannerES" component={BannerES} width={2560} height={1440} defaultProps={{ name: "Orígenes de Gigantes", tagline: "Documentales sobre cómo se hizo el dinero" }} />
    <Still id="WatermarkES" component={WatermarkES} width={150} height={150} defaultProps={{ name: "Orígenes de Gigantes", tagline: "" }} />
  </>
);
