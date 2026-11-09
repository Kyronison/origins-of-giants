"""Ассеты плёнки для Film.tsx (лежат в remotion/src/film и импортируются как модули — public dir при рендере = папка видео).
1) grain_{0..3}.png — четыре тайла 512×512, серый шум 128±50, Gaussian 0.6 px (Remotion растягивает до 896 px → зерно ≈ 3 px).
2) frame_mask.png — «кадровое окно» проектора 1920×1080 RGBA: прозрачный центр, тёмные скруглённые размытые края с неровностью,
   чуть асимметричные (плёнка в гейте никогда не стоит ровно). Статичная картинка = ноль стоимости на кадр.
Запуск один раз: python -m orchestrator.tools.make_film
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "remotion" / "src" / "film"
SIZE, MEAN, SIGMA, BLUR, N = 512, 128, 50, 0.6, 4
W, H = 1920, 1080


def tile(seed: int) -> Image.Image:
    rng = np.random.default_rng(1000 + seed)
    a = rng.normal(MEAN, SIGMA, (SIZE, SIZE)).clip(0, 255).astype(np.uint8)
    img = Image.fromarray(a, "L").filter(ImageFilter.GaussianBlur(BLUR))
    # после блюра разброс падает — растягиваем обратно к ±SIGMA, чтобы зерно читалось
    b = np.asarray(img).astype(np.float32)
    b = (b - b.mean()) * (SIGMA / max(b.std(), 1e-6)) + MEAN
    return Image.fromarray(b.clip(0, 255).astype(np.uint8), "L")


def frame_mask() -> Image.Image:
    """Альфа = затемнение: 0 внутри окна, ~0.9 у самого края; скруглённые углы r≈90, перо ~110 px, низкочастотная неровность ±20 %."""
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    # окно чуть смещено и чуть уже по краям, как плёнка в гейте
    left, right, top, bottom = 24.0, W - 30.0, 18.0, H - 26.0
    r = 90.0
    # расстояние до скруглённого прямоугольника (со знаком: <0 внутри)
    cx = np.clip(x, left + r, right - r); cy = np.clip(y, top + r, bottom - r)
    d = np.sqrt((x - cx) ** 2 + (y - cy) ** 2) - r          # ≥0 снаружи скругления, внутри прямоугольника → отрицательно ближе к центру
    inside = np.minimum(np.minimum(x - left, right - x), np.minimum(y - top, bottom - y))
    d = np.where((x > left + r) & (x < right - r) | (y > top + r) & (y < bottom - r), -inside, d)
    feather = 110.0
    a = np.clip(1 - (-d) / feather, 0, 1)                    # 0 глубоко внутри, 1 на краю окна
    a = a ** 1.8 * 0.9
    a = np.where(d > 0, 0.9 + 0.1 * np.clip(d / 40, 0, 1), a)   # за окном — почти чёрно
    # неровность края: низкочастотный шум
    rng = np.random.default_rng(7)
    noise = rng.normal(0, 1, (12, 20)).astype(np.float32)
    noise = np.asarray(Image.fromarray(((noise - noise.min()) / (noise.max() - noise.min()) * 255).astype(np.uint8), "L").resize((W, H), Image.BICUBIC)).astype(np.float32) / 255
    a = np.clip(a * (0.8 + 0.4 * noise), 0, 1)
    rgba = np.zeros((H, W, 4), np.uint8)
    rgba[..., 0] = 8; rgba[..., 1] = 6; rgba[..., 2] = 4
    rgba[..., 3] = (a * 255).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA").filter(ImageFilter.GaussianBlur(6))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for i in range(N):
        p = OUT / f"grain_{i}.png"
        if not p.exists(): tile(i).save(p, optimize=True)
        print(f"[film] {p.name}: {p.stat().st_size // 1024} КБ")
    p = OUT / "frame_mask.png"; frame_mask().save(p, optimize=True)
    print(f"[film] {p.name}: {p.stat().st_size // 1024} КБ")


if __name__ == "__main__":
    main()
