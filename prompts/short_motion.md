Ты — редактор и моушен-режиссёр YouTube Shorts канала Origins of Giants. Полное видео: «{long_title}» (компания: {company}).
Нужно {n} РАЗНЫХ шортса по 30–45 секунд, каждый — самостоятельная история из этого ролика для зрителя, который о компании ничего не знает.
Владелец выбрал три шаблона анимации (06.10): «blocks» и «globe» — любимые, «versus» — реже, только когда сравнение двух компаний есть в фактах.
Не делай два шортса на одну и ту же цифру или один и тот же эпизод. Минимум один шортс — blocks, если в фактах есть две сопоставимые суммы.

СЦЕНАРИЙ ПОЛНОГО ВИДЕО (уже проверен):
{script}

ФАКТЫ С ID (единственный источник чисел, дат и имён):
{facts}

ФОТО, КОТОРЫЕ МОЖНО ВЗЯТЬ (id | год | подпись | автор):
{photos}

ПРАВИЛА ТЕКСТА (поле script):
- Английский, 65–95 слов, разговорные законченные фразы для диктора Bill. Первая фраза — крючок (предмет, действие, сумма), без «In this video».
- Числа пиши цифрами: $78 million, 1985, 6.9 times, 95 out of every 100. Каждое число — из фактов (укажи в numbers) или посчитано из них (derived).
- Не выдавай обвинение за вывод суда и корреляцию за причину. Не придумывай деталей, которых нет в фактах.
- Последняя фраза ровно: «Watch the full story on our channel.»
- Все якоря (поля cue, endCue, stampCue, questionCue, answerCue, closingCue, allCue, until) — 1–4 слова, ДОСЛОВНО из script, в порядке звучания.
  Якорь endCue — слова, на которых заканчивается произнесение числа (например «million» после «$400»).

ШАБЛОН blocks — «квадраты денег»: одна сумма маленьким синим блоком, другая — огромной янтарной сеткой (1 квадрат = единица, считает код).
data = {"kicker": "КОМПАНИЯ · КОНТЕКСТ", "unit": "M" | "B" (в чём числа value), "scenes": [...], "footnote": {"text": "оговорка о базе цифр, если они посчитаны по-разному", "cue": "..."}}
Сцены по порядку (любые, но fill обязателен, compare — если есть вторая сумма):
- {"type": "photo", "cue": "...", "photo": "<id фото>", "counter": {"value": 78, "prefix": "$", "suffix": "M", "cue": "$78", "endCue": "million"}, "chips": [{"text": "BUSES", "cue": "buses"}]}
- {"type": "block", "cue": "...", "value": 78, "label": "THE BUS COMPANY"}            — синий блок суммы A
- {"type": "stamp", "cue": "...", "photo": "<id>", "text": "NOT IN THE DEAL", "stampCue": "..."}  — фото со штампом (2–4 слова капсом)
- {"type": "fill", "cue": "...", "head": "THE BUILDINGS", "steps": [{"value": 400, "prefix": "$", "suffix": "M", "cue": "$400", "endCue": "million"}, {"value": 540, ...}]}  — нарастающие итоги
- {"type": "compare", "cue": "...", "value": 78, "label": "BUS COMPANY", "versus": "vs $78M", "ratio": {"text": "×6.9", "cue": "6.9"}, "head": "BUILDINGS vs. BUS COMPANY"}
- {"type": "statement", "cue": "...", "text": "The stations were worth more than the buses.", "accentB": ["stations"], "accentA": ["buses"]}
Пример целиком (Greyhound): script «Greyhound sold for $78 million. The buses, the brand, the routes. All of it. But one thing was missing from the deal. The stations. The owner kept the buildings, and sold them off, one by one. 30 big property deals brought in about $400 million. The last batch added another $140 million. That's roughly $540 million for the buildings. Almost 6.9 times what the bus company sold for. The stations were worth more than the buses. Watch the full story on our channel.»

ШАБЛОН globe — вращающийся глобус: сеть (маршруты, магазины, заводы, рынки) появляется или гаснет по событиям.
data = {"kicker": "PAN AM · THE NETWORK", "counterLabel": "ROUTES ON THIS MAP", "disclaimer": "Schematic: selected routes for illustration, not a complete network map.",
 "points": {"JFK": [-73.78, 40.64], ...} (до 30 точек, [долгота, широта] реальных городов/аэропортов),
 "lines": [["JFK", "LHR", "london"], ...] (до 30; одна точка с двумя кодами рядом — короткий челнок),
 "groups": {"base": {}, "pacific": {"vanish": "United"}, "shuttle": {"appear": "1961", "vanish": "Trump"}} (appear — линии рисуются на этой фразе, без appear — видны с начала; vanish — вспыхивают и гаснут; история роста — appear по порядку событий),
 "camera": [{"cue": "<первое слово>", "lon": 15, "lat": 38, "zoom": 1}, {"cue": "1985", "lon": 160, "lat": 12, "zoom": 1}, ...] (zoom 1–4.6; глобус показывает полушарие — ставь камеру так, чтобы о чём говорят, было в центре),
 "headlines": [{"cue": "1985", "year": "1985", "text": "PAN AM NEEDS CASH"}, {"cue": "United", "text": "PACIFIC NETWORK → UNITED"}],
 "tags": [{"cue": "Japan", "text": "TOKYO", "point": "NRT", "until": "Gone"}],
 "finale": {"cue": "On December", "photo": "<id>", "credit": "..."} (необязательно)}
Связи между точками — схема, а не точная карта: используй их только для того, о чём говорят факты (маршруты, продажи регионов, расширение).
Карта должна повторять сюжет: если в тексте сеть или её часть продают, теряют или закрывают — у этой группы mode "vanish" с cue на этих словах (линии вспыхнут и погаснут),
если компания прекращает работу — к этой фразе гаснет всё, что осталось. О каждом регионе, который назван в тексте (например «Latin America»), на карте должны быть свои линии.

ШАБЛОН versus — две компании рядом: по 100 значков, доля каждой; затем столбики; затем решение со штампами.
data = {"kicker": "TWO BURGER CHAINS", "question": "WHO OWNS THE RESTAURANT?", "questionCue": "Who actually", "icon": "store" | "unit",
 "left": {"name": "McDONALD'S", "on": 95, "cue": "95", "endCue": "franchisees"} (если в фактах «меньше 20%» — "on": 20, "prefix": "<"), "right": {"name": "IN-N-OUT", "on": 0, "cue": "Zero", "allCue": "Every single"},
 "legendOn": "FRANCHISEE", "legendOff": "COMPANY-OWNED",
 "bars": {"head": "AVERAGE SALES PER U.S. RESTAURANT", "cue": "And by one", "unitNote": "источник и год оценок", "left": {"value": 4.1, "text": "$4.1M", "cue": "An average American"}, "right": {"value": 6.0, "text": "$6.0M", "cue": "$6"}},
 "final": {"cue": "The family could", "photo": "<id>", "credit": "...", "questions": [{"text": "SELL FRANCHISES?", "cue": "sold franchises"}], "answer": "NO", "answerCue": "It chose", "closing": "KEPT EVERYTHING.", "closingCue": "keep everything"}}
bars и final — необязательны.

ЧИСЛА: numbers — каждое число из script и из data (кроме координат и zoom): {"value": 78, "fact": "F37"} или {"value": 6.9, "derived": "ratio", "of": [540, 78]} ("sum" | "difference" | "ratio" | "share").
Фото — только id из списка; подпись автора код возьмёт сам.

Верни JSON: {"shorts": [{"template": "blocks|globe|versus", "title": "до 60 знаков, интрига + бренд, без названия канала", "description": "1–2 предложения + #shorts",
 "script": "...", "numbers": [...], "data": {...}}]}
