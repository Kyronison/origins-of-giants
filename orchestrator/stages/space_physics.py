"""Космический канал: справочник величин и расчёты для схем и сценария (23.10.2026).

Всё, что звучит в ролике числом или рисуется в масштабе, берётся отсюда: опубликованные значения (с источником в
facts.json выпуска) и производные величины, посчитанные кодом. check_script() до озвучки сверяет каждое число сценария
со списком разрешённых значений выпуска, а check_calcs() — каждое производное утверждение с пересчётом (допуск 5%).
"""
import math
import re

# --- постоянные (CODATA / IAU 2015) ---
C_KM_S = 299_792.458
G = 6.674_30e-11
GM_SUN = 1.327_124_400_18e20          # м³/с², IAU 2015 B3 номинал
AU_KM = 149_597_870.7
LY_KM = 9.460_730_472_5808e12
PC_KM = 3.085_677_581e13
R_SUN_KM = 695_700.0                  # IAU 2015 B3, NASA NSSDC Sun fact sheet
R_EARTH_KM = 6_371.0                  # NSSDC Earth fact sheet, объёмный средний
R_JUPITER_KM = 69_911.0               # NSSDC Jupiter fact sheet, объёмный средний
G0 = 9.806_65
AIR_DENSITY = 1.2                     # кг/м³, у поверхности, ~20 °C
SUN_DENSITY = 1408.0                  # кг/м³, NSSDC

# --- звёзды: радиус в радиусах Солнца; source — ключ источника в facts.json выпуска ---
STARS = {
    "earth": {"name": "Earth", "r_sun": R_EARTH_KM / R_SUN_KM, "color": "#4f8fd6"},
    "jupiter": {"name": "Jupiter", "r_sun": R_JUPITER_KM / R_SUN_KM, "color": "#d9a066"},
    "sun": {"name": "The Sun", "r_sun": 1.0, "color": "#ffd34d"},
    "sirius": {"name": "Sirius A", "r_sun": 1.711, "color": "#cfe3ff"},
    "arcturus": {"name": "Arcturus", "r_sun": 25.4, "color": "#ffb36b"},
    "rigel": {"name": "Rigel", "r_sun": 74.1, "color": "#b9d3ff"},
    "antares": {"name": "Antares", "r_sun": 680.0, "color": "#ff7a45"},
    "betelgeuse": {"name": "Betelgeuse", "r_sun": 764.0, "color": "#ff8a3d"},
    "uy_sct_2013": {"name": "UY Scuti (2013)", "r_sun": 1708.0, "color": "#ff6b3d"},
    "uy_sct_2024": {"name": "UY Scuti (2024)", "r_sun": 909.0, "color": "#ff6b3d"},
    "vy_cma": {"name": "VY Canis Majoris", "r_sun": 1420.0, "color": "#ff5a36"},
    "st2_18_2012": {"name": "Stephenson 2-18 (2012)", "r_sun": 2150.0, "color": "#ff4b33"},
    "woh_g64_2009": {"name": "WOH G64 (2009)", "r_sun": 1540.0, "color": "#ff5236"},
    "hd_limit": {"name": "Theory limit", "r_sun": 1500.0, "color": "#888888"},
    # NASA: красный гигант поглотит Меркурий и Венеру, возможно Землю — рисуем ~1 а.е. с пометкой «примерно»
    "sun_red_giant": {"name": "Red giant Sun (approx.)", "r_sun": 215.0, "color": "#ff7a45"},
}

# --- орбиты Солнечной системы, большие полуоси, а.е. (NSSDC) ---
ORBITS_AU = {"Mercury": 0.387, "Venus": 0.723, "Earth": 1.0, "Mars": 1.524, "Jupiter": 5.203, "Saturn": 9.537,
             "Uranus": 19.19, "Neptune": 30.07}

# --- чёрные дыры: масса в массах Солнца ---
BLACK_HOLES = {
    "stellar10": {"name": "10-Sun black hole", "m_sun": 10.0},
    "gaia_bh1": {"name": "Gaia BH1", "m_sun": 9.62},
    "sgr_a": {"name": "Sagittarius A*", "m_sun": 4.297e6},
    "m87": {"name": "M87*", "m_sun": 6.5e9},
}


def r_au(key):
    return STARS[key]["r_sun"] * R_SUN_KM / AU_KM


def light_around_s(r_sun):
    """Время, за которое свет обходит экватор шара радиусом r_sun радиусов Солнца, с."""
    return 2 * math.pi * r_sun * R_SUN_KM / C_KM_S


def jet_around_days(r_sun, kmh=900.0):
    return 2 * math.pi * r_sun * R_SUN_KM / kmh / 24


def volume_ratio(r_sun_a, r_sun_b=1.0):
    return (r_sun_a / r_sun_b) ** 3


def mean_density(m_sun, r_sun):
    """Средняя плотность шара, кг/м³ (масса / объём)."""
    m = m_sun * GM_SUN / G
    r = r_sun * R_SUN_KM * 1000
    return m / (4 / 3 * math.pi * r ** 3)


def schwarzschild_km(m_sun):
    return 2 * m_sun * GM_SUN / (C_KM_S * 1000) ** 2 / 1000


def tidal_stretch_g(m_sun, r_km, length_m=2.0):
    """Ньютонова разница ускорений голова–ноги (радиальное падение), в g."""
    r = r_km * 1000
    return 2 * m_sun * GM_SUN * length_m / r ** 3 / G0


def tidal_radius_km(m_sun, g_limit=10.0, length_m=2.0):
    """Расстояние, где разница голова–ноги достигает g_limit (ньютоново приближение)."""
    return (2 * m_sun * GM_SUN * length_m / (g_limit * G0)) ** (1 / 3) / 1000


def horizon_to_singularity_s(m_sun, mode="max"):
    """Собственное время от горизонта до сингулярности (Шварцшильд): max = π·GM/c³ (лучшее, что можно сделать двигателем),
    infall = 4/3·GM/c³ (свободное падение из покоя на бесконечности)."""
    t = m_sun * GM_SUN / (C_KM_S * 1000) ** 3
    return math.pi * t if mode == "max" else 4 / 3 * t


def horizon_mean_density(m_sun):
    """Масса, делённая на объём шара радиусом горизонта (наглядная величина, не «плотность вещества»), кг/м³."""
    return mean_density(m_sun, schwarzschild_km(m_sun) / R_SUN_KM)


CALCS = {
    # имя: функция без аргументов → число; утверждения в facts.json ссылаются на них полем "calc"
    "sun_earths_across": lambda: R_SUN_KM / R_EARTH_KM,
    "sun_earth_volume": lambda: volume_ratio(R_SUN_KM / R_EARTH_KM),
    "jupiter_earths_across": lambda: R_JUPITER_KM / R_EARTH_KM,
    "light_around_sun_s": lambda: light_around_s(1.0),
    "jet_around_sun_days": lambda: jet_around_days(1.0),
    "betelgeuse_au": lambda: r_au("betelgeuse"),
    "vy_cma_au": lambda: r_au("vy_cma"),
    "uy_2013_au": lambda: r_au("uy_sct_2013"),
    "st2_18_au": lambda: r_au("st2_18_2012"),
    "light_around_vy_h": lambda: light_around_s(STARS["vy_cma"]["r_sun"]) / 3600,
    "jet_around_vy_years": lambda: jet_around_days(STARS["vy_cma"]["r_sun"]) / 365.25,
    "vy_cma_suns_volume": lambda: volume_ratio(STARS["vy_cma"]["r_sun"]),
    "vy_cma_density_vs_air": lambda: AIR_DENSITY / mean_density(17, STARS["vy_cma"]["r_sun"]),
    "betelgeuse_suns_volume": lambda: volume_ratio(STARS["betelgeuse"]["r_sun"]),
    "uy_shrink_ratio": lambda: STARS["uy_sct_2013"]["r_sun"] / STARS["uy_sct_2024"]["r_sun"],
    "rs_per_sun_km": lambda: schwarzschild_km(1),
    "rs_10_km": lambda: schwarzschild_km(10),
    "rs_sgr_km": lambda: schwarzschild_km(4.297e6),
    "rs_sgr_au": lambda: schwarzschild_km(4.297e6) / AU_KM,
    "rs_sgr_suns": lambda: schwarzschild_km(4.297e6) / R_SUN_KM,
    "rs_m87_au": lambda: schwarzschild_km(6.5e9) / AU_KM,
    "rs_m87_neptunes": lambda: schwarzschild_km(6.5e9) / AU_KM / ORBITS_AU["Neptune"],
    "rs_earth_mm": lambda: schwarzschild_km(3.003e-6) * 1e6,
    "tidal_radius_10_km": lambda: tidal_radius_km(10),
    "tidal_radius_sgr_km": lambda: tidal_radius_km(4.297e6),
    "tidal_at_sgr_horizon_g": lambda: tidal_stretch_g(4.297e6, schwarzschild_km(4.297e6)),
    "tidal_at_10_horizon_g": lambda: tidal_stretch_g(10, schwarzschild_km(10)),
    "fall_sgr_max_s": lambda: horizon_to_singularity_s(4.297e6),
    "fall_sgr_infall_s": lambda: horizon_to_singularity_s(4.297e6, "infall"),
    "fall_10_max_ms": lambda: horizon_to_singularity_s(10) * 1000,
    "density_sgr_horizon_vs_water": lambda: horizon_mean_density(4.297e6) / 1000,
    "density_m87_horizon_vs_air": lambda: horizon_mean_density(6.5e9) / AIR_DENSITY,
}


def check_calcs(facts, tol=0.05):
    """Каждое утверждение с полем calc: заявленное value совпадает с пересчётом в пределах tol (или округлением, если указано rounding)."""
    errors = []
    for f in facts:
        if not f.get("calc"): continue
        got = CALCS[f["calc"]]()
        want = float(f["value"])
        if not math.isclose(got, want, rel_tol=f.get("tol", tol)):
            errors.append(f"{f['id']}: в тексте {want}, расчёт {got:.4g} ({f['calc']})")
    return errors


_WORDNUM = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)(?:\s*(million|billion|trillion|thousand))?", re.I)
SMALL_OK = {str(n) for n in range(0, 13)}   # «two stars», «one second» и т. п. — счёт, не измерение


def numbers_in(text):
    out = []
    for m in _WORDNUM.finditer(text):
        n = m.group(1).replace(",", "")
        out.append((n + (" " + m.group(2).lower() if m.group(2) else "")).strip())
    return out


def check_script(text, facts):
    """Каждое число сценария должно быть в facts[*].say выпуска (кроме счёта 0–12 и годов публикаций из facts)."""
    allowed = set(SMALL_OK)
    for f in facts:
        for s in f.get("say", []): allowed.update(numbers_in(s) or [s])
    return [n for n in numbers_in(text) if n not in allowed]
