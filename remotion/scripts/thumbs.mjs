// Варианты обложки одним бандлом: node scripts/thumbs.mjs <publicDir> <props.json> <outDir> variant1 variant2 ...
import { bundle } from "@remotion/bundler";
import { renderStill, selectComposition } from "@remotion/renderer";
import fs from "node:fs";
import path from "node:path";

const [publicDir, propsPath, outDir, ...variants] = process.argv.slice(2);
const base = JSON.parse(fs.readFileSync(propsPath, "utf-8"));
fs.mkdirSync(outDir, { recursive: true });
const serveUrl = await bundle({ entryPoint: path.resolve("src/index.ts"), publicDir: path.resolve(publicDir) });
try {
  for (const variant of variants) {
    // вариант — имя (к базовым props добавляется variant) или путь к готовому props_<имя>.json: все варианты одним бандлом
    const isFile = variant.endsWith(".json");
    const inputProps = isFile ? JSON.parse(fs.readFileSync(variant, "utf-8")) : { ...base, variant };
    const name = isFile ? path.basename(variant, ".json").replace(/^props_/, "") : variant;
    const composition = await selectComposition({ serveUrl, id: "ThumbV", inputProps });
    // THUMB_SCALE=2 — обложка в 2560×1440 для загрузки на YouTube (композиция остаётся 1280×720)
    const scale = Number(process.env.THUMB_SCALE || 1);
    await renderStill({ composition, serveUrl, output: path.join(outDir, `thumb_${name}.png`), inputProps, scale, chromiumOptions: { gl: "angle" } });
    console.log("thumb", name);
  }
} finally {
  // бандл несёт копию всей папки ролика (1.3 ГБ) и сам не удаляется: 18.09 десять вызовов забили системный диск до нуля
  fs.rmSync(serveUrl, { recursive: true, force: true });
}
