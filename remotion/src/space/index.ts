// Отдельная точка входа космического канала (23.10.2026): общий Root.tsx английского канала не трогаем,
// чтобы рендер Origins of Giants не зависел от этих файлов. Запуск: remotion render src/space/index.ts Space out.mp4 --props …
import { registerRoot } from "remotion";
import { SpaceRoot } from "./Root";
registerRoot(SpaceRoot);
