// Кадры-пробы из композиции Main ДО полного рендера: node scripts/stills.mjs <publicDir> <props.json> <outDir> <frame1> <frame2> …
// Один бандл на все кадры (CLI `still` собирал бы бандл на каждый — по минуте на кадр).
import { bundle } from "@remotion/bundler";
import { renderStill, selectComposition } from "@remotion/renderer";
import fs from "node:fs";
import path from "node:path";

const [publicDir, propsPath, outDir, ...frames] = process.argv.slice(2);
const inputProps = JSON.parse(fs.readFileSync(propsPath, "utf-8"));
fs.mkdirSync(outDir, { recursive: true });
const serveUrl = await bundle({ entryPoint: path.resolve("src/index.ts"), publicDir: path.resolve(publicDir) });
try {
  const composition = await selectComposition({ serveUrl, id: "Main", inputProps, timeoutInMilliseconds: 180000 });
  for (const f of frames) {
    const frame = Math.max(0, Math.min(composition.durationInFrames - 1, Number(f)));
    await renderStill({ composition, serveUrl, output: path.join(outDir, `still_${f}.png`), inputProps, frame, scale: 0.5, chromiumOptions: { gl: "angle" }, timeoutInMilliseconds: 180000 });   // кадры видео тянутся долго, когда параллельно идёт рендер (23.09)
    console.log("still", f);
  }
} finally {
  fs.rmSync(serveUrl, { recursive: true, force: true });   // бандл несёт копию папки ролика — не оставлять на диске
}
