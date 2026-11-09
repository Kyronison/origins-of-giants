/** Импорт картинок модулями (webpack asset/resource в бандлере Remotion): тайлы зерна в src/film. */
declare module "*.png" {
  const src: string;
  export default src;
}
