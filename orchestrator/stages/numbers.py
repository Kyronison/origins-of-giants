"""Цифры озвучки → flash-титры ровно на своих словах (владелец 16.09: каждая цифра выносится на экран, когда о ней говорят).
Ищем по words.json, а не просим модель: суммы ($3.50, $101 million → $101M), проценты, количества (50 computers, 300 employees),
возраст (Jobs is 21 → «21 · years old»), числа словами от тринадцати (fifty, three hundred, half a million, twenty-one).
Годы, даты, порядковые и номера моделей (December 12, 1980; 1st; Altair 8800; Bandley 3) — не цифры для выноса."""
import re

ONES = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
        "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
SCALE = {"hundred": 100, "thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000, "trillion": 1_000_000_000_000}
SCALE_SUFFIX = {"thousand": "K", "million": "M", "billion": "B", "trillion": "T"}
MONTHS = {"january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"}
AGE_PREV = {"is", "was", "age", "aged", "turned", "turns", "turning", "at"}
STOP = {"and", "but", "that", "which", "who", "whom", "was", "were", "is", "are", "had", "has", "have", "the", "of", "to", "in", "on", "at", "by", "for",
        "with", "from", "as", "it", "its", "this", "these", "those", "he", "she", "they", "his", "her", "their", "when", "while", "then", "than", "or",
        "into", "over", "after", "before", "so", "not", "no", "would", "could", "will", "did", "do", "does", "be", "been", "being",
        "versus", "vs", "roughly", "about", "nearly", "almost", "around", "some", "if", "because", "since", "until", "though", "although",
        # наречия — не подпись (Amazon 18.09: «$100 just two years earlier» давал плашку «$100 / JUST», «$10—down from» — «$10 / DOWN»)
        "just", "down", "up", "only", "even", "still", "already", "again", "back", "earlier", "later", "ago", "now", "today", "yet", "too", "also"}
FRACTIONS = {"one-third": "⅓", "two-thirds": "⅔", "one-quarter": "¼", "three-quarters": "¾", "one-half": "½"}
SENT_END = re.compile(r"[.!?;:]$")
DASH = re.compile(r"--|—|–")

def _core(w: str) -> str:
    return w.strip("\"'“”‘’()[]").rstrip(".,!?;:").lower()

def _fmt_int(n: float) -> str:
    return f"{int(round(n)):,}"

def _scale_display(num: str, scale: str | None, money: bool) -> str:
    """«101 million» → 101M, «3.4 billion» → 3.4B, «500 thousand» → 500K; без scale — число как есть (с запятыми)."""
    if scale in SCALE_SUFFIX:
        return ("$" if money else "") + num.replace(",", "") + SCALE_SUFFIX[scale]
    if scale == "hundred":
        return ("$" if money else "") + _fmt_int(float(num.replace(",", "")) * 100)
    if "." in num or "," in num or len(num) <= 3: return ("$" if money else "") + num
    return ("$" if money else "") + _fmt_int(float(num))

def _spelled(cores: list[str], i: int):
    """Число словами с позиции i: (значение, сколько токенов). «half a million», «a million», «three hundred», «twenty-one», «fifty».
    Одиночные слова до двенадцати без масштаба — не число для экрана («two Steves», «one of them»)."""
    w = cores[i]
    if w == "half" and i + 2 < len(cores) and cores[i + 1] in ("a", "an") and cores[i + 2] in SCALE and cores[i + 2] != "hundred":
        return SCALE[cores[i + 2]] / 2, 3
    if w in ("a", "an") and i + 1 < len(cores) and cores[i + 1] in ("million", "billion", "trillion"):
        return SCALE[cores[i + 1]], 2
    total, cur, j, seen_scale = 0, 0, i, False
    while j < len(cores):
        t = cores[j]
        if "-" in t and all(p in ONES or p in TENS for p in t.split("-")):
            cur += sum(ONES.get(p, TENS.get(p, 0)) for p in t.split("-")); j += 1; continue
        if t in ONES: cur += ONES[t]; j += 1; continue
        if t in TENS: cur += TENS[t]; j += 1; continue
        if t in SCALE and j > i:
            if t == "hundred": cur = (cur or 1) * 100
            else: total += (cur or 1) * SCALE[t]; cur = 0; seen_scale = True
            j += 1; continue
        break
    n = j - i
    if n == 0: return None
    val = total + cur
    if not seen_scale and val < 13: return None
    return val, n

DIGIT = {"zero": "0", "oh": "0", "o": "0", **{k: str(v) for k, v in ONES.items() if v < 10}}

def _spelled_decimal(cores: list[str], i: int):
    """Десятичное число словами: «forty-five point one eight billion [dollars]», «thirteen point three percent».
    Возвращает (готовая подпись, сколько токенов) или None. Целая часть — любое число словами, в т.ч. меньше тринадцати («two point five million»)."""
    total, j = 0, i
    while j < len(cores):
        t = cores[j]
        if "-" in t and all(p in ONES or p in TENS for p in t.split("-")): total += sum(ONES.get(p, TENS.get(p, 0)) for p in t.split("-"))
        elif t in ONES: total += ONES[t]
        elif t in TENS: total += TENS[t]
        elif t == "hundred" and j > i: total = (total or 1) * 100
        elif t == "zero" and j == i: pass
        else: break
        j += 1
    if j == i or j >= len(cores) or cores[j] != "point": return None
    k, frac = j + 1, ""
    while k < len(cores) and cores[k] in DIGIT and len(frac) < 3: frac += DIGIT[cores[k]]; k += 1
    if not frac: return None
    num = f"{total}.{frac}"
    scale = cores[k] if k < len(cores) and cores[k] in SCALE_SUFFIX else None
    if scale: k += 1
    money = k < len(cores) and cores[k] in ("dollars", "dollar", "bucks")
    pct = k < len(cores) and cores[k] in ("percent", "per cent")
    if money or pct: k += 1
    disp = ("$" if money else "") + num + (SCALE_SUFFIX[scale] if scale else "") + ("%" if pct else "")
    return disp, k - i

def _expand(words: list[dict]) -> tuple[list[str], list[int]]:
    """Токены озвучки; «million--one» и «15%--worth» режем по длинному тире на отдельные токены (тайминг — исходного слова)."""
    toks, idx = [], []
    for k, w in enumerate(words):
        for part in DASH.split(w["w"]):
            if part: toks.append(part); idx.append(k)
    return toks, idx

def _label(toks: list[str], j: int) -> str:
    """Подпись под цифрой: 1–3 следующих слова («computers», «per share», «an hour»), до конца предложения."""
    out = []
    if j < len(toks) and _core(toks[j]) in ("per", "an", "a", "each", "apiece"):
        out = [toks[j].strip(",")]
        if SENT_END.search(toks[j]) or j + 1 >= len(toks): return out[0].rstrip(".!?;:")
        out.append(toks[j + 1].strip(",")); return " ".join(out).rstrip(".!?;:")
    while j < len(toks) and len(out) < 3:
        c = _core(toks[j])
        if not c or c in STOP or c in ONES or c in TENS: break   # «$101 million — one of…»: «one» не подпись
        out.append(toks[j].strip(","))
        if SENT_END.search(toks[j]): break
        j += 1
    return " ".join(out).rstrip(".!?;:")

def _is_model_number(toks: list[str], i: int) -> bool:
    """«Altair 8800», «Bandley 3», «Apple II»-подобные: перед числом имя собственное не в начале предложения."""
    if i == 0: return False
    prev = toks[i - 1].strip("\"'“”‘’()")
    camel = len(prev) > 1 and prev[0].islower() and prev[1].isupper()   # «iPhone 18 Pro», «iPad 2» — тоже имя модели
    if not (prev[:1].isupper() or camel) or _core(prev) in ("i", "in", "at", "by", "of", "on", "to", "the", "a", "an", "and", "but", "as", "for", "with", "from"): return False
    return not (i >= 2 and SENT_END.search(toks[i - 2]))

def flashes(words: list[dict], seconds: float = 2.6, dedupe_sec: float = 25.0) -> list[dict]:
    toks, idx = _expand(words); cores = [_core(w) for w in toks]
    out, i, last_seen = [], 0, {}
    while i < len(toks):
        c, display, n_used = cores[i], None, 1
        prev = cores[i - 1] if i else ""
        nxt = cores[i + 1] if i + 1 < len(cores) else ""
        m_money = re.match(r"^\$(\d[\d,]*(?:\.\d+)?)$", c)
        m_pct = re.match(r"^(\d+(?:\.\d+)?)%$", c)
        m_num = re.match(r"^(\d[\d,]*(?:\.\d+)?)$", c)
        if m_money:
            scale = nxt if nxt in SCALE else None
            display = _scale_display(m_money.group(1), scale, True); n_used = 2 if scale else 1
        elif m_pct:
            display = m_pct.group(1) + "%"
        elif m_num:
            raw = m_num.group(1); digits = raw.replace(",", "")
            is_year = re.fullmatch(r"(1[6-9]|20)\d\d", digits) is not None
            is_date = prev in MONTHS or nxt in MONTHS or (nxt and re.fullmatch(r"(1[6-9]|20)\d\d", nxt) is not None)
            scale = nxt if nxt in SCALE else None
            small = "." not in raw and "," not in raw and float(digits) < 10 and not scale and prev not in AGE_PREV
            if not (is_year or is_date or small or _is_model_number(toks, i)):
                display = _scale_display(raw, scale, False); n_used = 2 if scale else 1
        elif c in FRACTIONS:
            display = FRACTIONS[c]
        else:
            dec = _spelled_decimal(cores, i)   # «forty-five point nine billion dollars» → $45.9B одной плашкой (владелец 21.09: было «45 / POINT» и отдельно «9B»)
            sp = None if dec else _spelled(cores, i)
            if dec:
                display, n_used = dec
            elif sp:
                val, n_used = sp
                display = _fmt_int(val) if val < 1_000_000 else (f"{val / 1_000_000:g}M" if val < 1_000_000_000 else f"{val / 1_000_000_000:g}B")
        if display is None:
            i += 1; continue
        last_tok = toks[i + n_used - 1]
        label = "" if SENT_END.search(last_tok) else _label(toks, i + n_used)
        try:
            if prev in AGE_PREV and float(display.replace(",", "")) < 100 and not label: label = "years old"
        except ValueError: pass
        w0 = idx[i]; t0 = words[w0]["s"]
        key = display.lower()
        if key in last_seen and t0 - last_seen[key] < dedupe_sec:
            i += n_used; continue
        last_seen[key] = t0
        out.append({"type": "flash", "anchor": " ".join(x["w"] for x in words[w0:w0 + 5]), "value": display, "label": label, "seconds": seconds,
                    "start": round(t0, 3), "_idx": w0, "auto": True})
        i += n_used
    merged = []
    for o in out:   # диапазон: две цифры через to/and/or/– в пределах трёх слов → одна плашка «$51–51.4B»
        p = merged[-1] if merged else None
        if p and 0 < o["_idx"] - p["_idx"] <= 5:
            between = [_core(w["w"]) for w in words[p["_idx"] + 1:o["_idx"]]]
            link = [w for w in between if w in ("to", "and", "or", "through")]
            rest = [w for w in between if w not in ("to", "and", "or", "through") and w not in ONES and w not in TENS and w not in SCALE and w not in ("point", "dollars", "percent")]
            if link and not rest:
                lo = re.sub(r"[KMBT%]$", "", p["value"]); hi = o["value"].lstrip("$")
                p["value"] = ("$" if o["value"].startswith("$") and not lo.startswith("$") else "") + lo + "–" + hi; p["label"] = o["label"] or p["label"]
                p["seconds"] = max(p["seconds"], 3.2); continue
        merged.append(o)
    out = merged
    for a, b in zip(out, out[1:]):   # соседние цифры: предыдущая уходит до появления следующей
        gap = b["start"] - a["start"]
        if gap < a["seconds"] + 0.2: a["seconds"] = round(max(1.4, gap - 0.2), 2)
    return out
