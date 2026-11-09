/** Детерминированный шум по кадру. Remotion рендерит в нескольких вкладках — Math.random запрещён:
 *  один и тот же кадр обязан выглядеть одинаково в любом воркере. */

/** 32-битный хеш целого → [0, 1). */
export const hash32 = (n: number): number => {
  let x = (n | 0) ^ 0x9e3779b9;
  x = Math.imul(x ^ (x >>> 16), 0x85ebca6b);
  x = Math.imul(x ^ (x >>> 13), 0xc2b2ae35);
  x ^= x >>> 16;
  return (x >>> 0) / 4294967296;
};

/** Хеш от нескольких целых (кадр, канал, индекс). */
export const hashN = (...ns: number[]): number => {
  let h = 0x811c9dc5;
  for (const n of ns) h = Math.imul(h ^ (n | 0), 0x01000193) ^ (h >>> 15);
  return hash32(h);
};

/** Seeded PRNG: одна и та же последовательность для одного seed (жизнь царапины, пылинки кадра). */
export const mulberry32 = (seed: number) => {
  let a = seed | 0;
  return (): number => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
};

/** Число из [lo, hi) по seed. */
export const rangeOf = (r: number, lo: number, hi: number) => lo + r * (hi - lo);
