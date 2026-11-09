import os, re, shutil
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA = ROOT / os.getenv("DATA_DIR", "data")
VIDEOS = DATA / "videos"
MUSIC = ROOT / os.getenv("MUSIC_DIR", "data/music")
PROMPTS = ROOT / "prompts"
REMOTION = ROOT / "remotion"

CHANNEL_NAME = os.getenv("CHANNEL_NAME", "Unit Economics")
RENDER_HEIGHT = int(os.getenv("RENDER_HEIGHT", 1080))
VIDEOS_PER_WEEK = int(os.getenv("VIDEOS_PER_WEEK", 2))
SHORTS_PER_VIDEO = int(os.getenv("SHORTS_PER_VIDEO", 3))
AI_BROLL_MAX_CLIPS = int(os.getenv("AI_BROLL_MAX_CLIPS", 0))
PUBLISH_HOUR_ET = int(os.getenv("PUBLISH_HOUR_ET", 17))
PUBLISH_WEEKDAYS_ET = [int(x) for x in os.getenv("PUBLISH_WEEKDAYS_ET", "").split(",") if x.strip()]   # 28.09 владелец: 3–4 ролика в неделю;
# дни выхода по времени US East, 0 — понедельник; пусто — каждый день. Запас AUTO_BACKLOG сам притормаживает производство под этот ритм
PUBLISH_NOT_BEFORE = os.getenv("PUBLISH_NOT_BEFORE", "").split("#")[0].strip()   # 29.09 STRATEGY.md: старт блока — раньше этой даты (ISO, UTC) слоты не выдаются
FINAL_KEEP_DAYS = int(os.getenv("FINAL_KEEP_DAYS", 14))            # владелец 29.09: готовый final.mp4 уходит с диска данных через столько дней после выхода
FINAL_RETENTION = os.getenv("FINAL_RETENTION", "move").split("#")[0].strip().lower()   # move — перенос в архив; delete — удаление (включает только владелец); off
FINAL_ARCHIVE_DIR = os.getenv("FINAL_ARCHIVE_DIR", "G:/OriginsOfGiants_archive").split("#")[0].strip()
ARCHIVE_MIN_FREE_GB = float(os.getenv("ARCHIVE_MIN_FREE_GB", 15))  # на диске архива должно оставаться не меньше
MIN_FREE_GB_START = float(os.getenv("MIN_FREE_GB_START", 20))   # 29.09 STRATEGY.md: автостарт не берёт новую тему, если на диске данных свободно меньше
REQUIRE_FINAL_APPROVAL = os.getenv("REQUIRE_FINAL_APPROVAL", "1") == "1"   # просмотр final.mp4 перед загрузкой
UPLOAD_MODE = os.getenv("UPLOAD_MODE", "api")                              # api | manual (см. README)

# --- голос ---
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")
TTS_CHUNK_CHARS = int(os.getenv("TTS_CHUNK_CHARS", 2500))                  # лимит модели 10k символов; 2500 — файлы меньше, обрывы CDN реже
TTS_STABILITY = float(os.getenv("TTS_STABILITY", 0.35))                     # ниже = живее
TTS_STYLE = float(os.getenv("TTS_STYLE", 0.45))
TTS_SIMILARITY = float(os.getenv("TTS_SIMILARITY", 0.75))
TTS_MODE = os.getenv("TTS_MODE", "v3_chain")                                 # v3_chain — v3 цепочкой, манера не прыгает между главами (владелец 17.09: «делай полную пересборку»); v3_tags — по запросу на главу; v2 — multilingual v2
TTS_CHAIN_MODEL = os.getenv("TTS_CHAIN_MODEL", "eleven_v4").split("#")[0].strip()   # модель озвучки цепочкой для НОВЫХ роликов (владелец 01.10: v4); начатые ролики остаются на своей (voice_settings.json)
TTS_V3_STABILITY = float(os.getenv("TTS_V3_STABILITY", 0.0))                # v3 принимает 0 (Creative, живее) / 0.5 / 1
TTS_V3_MAX_CHARS = int(os.getenv("TTS_V3_MAX_CHARS", 4800))                # глава целиком одним запросом v3, если не длиннее (лимит модели 5000)
TTS_TEMPO = float(os.getenv("TTS_TEMPO", 1.0))  # Post-process narration tempo and pauses with ffmpeg atempo.
TTS_TARGET_WPM = float(os.getenv("TTS_TARGET_WPM", 0))  # Optional narration words-per-minute target; zero disables retiming.

# --- LLM через OpenRouter ---
LLM_MODEL = os.getenv("LLM_MODEL", "qwen/qwen3.8-max-0902")                       # лёгкие задачи (починка JSON)
LLM_MODEL_HEAVY = os.getenv("LLM_MODEL_HEAVY", "qwen/qwen3.8-max-0902")           # темы, ресёрч, сценарий, QC, аналитика
LLM_MODEL_VISION = os.getenv("LLM_MODEL_VISION", "anthropic/claude-sonnet-5")   # визуальный QC: Qwen-VL пропускает пустые кадры, Sonnet ловит за ~$0.01
ANTHROPIC_MODEL, ANTHROPIC_MODEL_HEAVY = LLM_MODEL, LLM_MODEL_HEAVY         # старые имена — для совместимости
LLM_MODEL_VISION_CHEAP = os.getenv("LLM_MODEL_VISION_CHEAP", "google/gemini-2.5-flash-lite")   # отбор кандидатов архива (сетки превью, раскадровки): в 60 раз дешевле Sonnet; подтверждение вырезки и preflight — Sonnet
LLM_MODEL_VISION_FALLBACK = os.getenv("LLM_MODEL_VISION_FALLBACK", "qwen/qwen3.7-flash")   # если дешёвая перегружена (429), до Sonnet
AUTO_PIPELINE = os.getenv("AUTO_PIPELINE", "1") == "1"                         # очередь сама берёт следующую историю из stories.txt, когда в работе пусто
AUTO_PIPELINE_HOUR = int(os.getenv("AUTO_PIPELINE_HOUR", 8))                   # во сколько по местному времени начинать ролик дня: к вечернему слоту 19:00 ET он должен быть готов
AUTO_PIPELINE_UNTIL = int(os.getenv("AUTO_PIPELINE_UNTIL", 14))                # позже этого часа новый ролик за сегодня не начинаем — не успеет к слоту
AUTO_PIPELINE_PER_DAY = int(os.getenv("AUTO_PIPELINE_PER_DAY", 1))             # сколько роликов в сутки запускать самостоятельно (режим «ролик дня»)
ES_VOICE_ID = os.getenv("ES_VOICE_ID", "")                                     # голос второго (испанского) канала; пусто — тот же голос, что у английского (v3 читает испанский тем же тембром)
ES_AUTO = os.getenv("ES_AUTO", "1") == "1"                                     # каждый готовый английский ролик → испанская версия на второй канал (stages/localize.py)
ES_QUEUE_SHARE = float(os.getenv("ES_QUEUE_SHARE", 0.5))                       # доля автостартов из stories_es.txt (темы для испаноговорящих): 0.5 — через одну
AUTO_BACKLOG = int(os.getenv("AUTO_BACKLOG", 0))                               # >0 — режим запаса (владелец 22.09): делать наперёд, пока запланированных и не вышедших роликов меньше N; окно часов и лимит в сутки не действуют
AUTO_SCRIPT_APPROVE = os.getenv("AUTO_SCRIPT_APPROVE", "1") == "1"             # сценарий уходит в производство сам: контрольная точка владельца перенесена на бриф
SHORT_HOUR_ET = int(os.getenv("SHORT_HOUR_ET", 12))                            # шортсы — в обеденный пик США, чтобы не делить стартовый показ с длинным роликом (19:00 ET)
SHORT_HOURS_ET = [int(x) for x in os.getenv("SHORT_HOURS_ET", "8,21").split(",") if x.strip()]   # 26.09: два шортса в день — утро и вечер США
SHORT_DAYS = [int(x) for x in os.getenv("SHORT_DAYS", "1,2,4").split(",")]      # на какие сутки после ролика выходят шортсы
SHORTS_SOURCE = os.getenv("SHORTS_SOURCE", "story")                      # story — сюжеты из самой документалки, news — свежие новости компании
AUTO_APPROVE = os.getenv("AUTO_APPROVE", "1") == "1"                         # финал уходит в загрузку сам, если чисты техпроверка, QC, комплект публикации и превью в ленте
PREFLIGHT_MAX_FIX = int(os.getenv("PREFLIGHT_MAX_FIX", 45))                    # сколько слотов максимум переснимать за проход: каждая замена — платная картинка
PREFLIGHT_CHEAP_FIRST = os.getenv("PREFLIGHT_CHEAP_FIRST", "1") == "1"         # первый проход смотрит дешёвая модель, Sonnet подтверждает только помеченное
OPENING_GATE = os.getenv("OPENING_GATE", "1") == "1"  # Check the narrated opening before purchasing visual assets.
OPENING_WPS = float(os.getenv("OPENING_WPS", 2.3))                            # слов в секунду у диктора (Bill: Microsoft 2.41, Google 2.38) — окна первой минуты по тексту до раскадровки
STILLCHECK = os.getenv("STILLCHECK", "1") == "1"                               # кадры-пробы из композиции до рендера, блокер = рендер не начинается (stages/stillcheck.py)
THUMBV_AUTO = os.getenv("THUMBV_AUTO", "1") == "1"                             # обложка «до → после» в стиле канала собирается сама (stages/thumbv.py); 0 — генерированная картинка с заголовком
QC_SHIP_ANYWAY = os.getenv("QC_SHIP_ANYWAY", "1") == "1"  # Advisory QC behavior; review together with STRICT_GATES and release checks.
# класс BLOCK по разбору Astra 21.09: не только права, но и достоверность — чужое лицо, документ другой компании, не тот человек
# 08.10: «сток» и «stock» — только с начала слова: Spirit заблокировала «карта северо-востока США» (во-СТОК-а), а «stock certificate» — не сток
QC_HARD = re.compile(os.getenv("QC_HARD", r"водян|watermark|\bсток|\bstock(?!\s+(certificate|market|price|offering))|логотип банка|чуж(ой|ая|ое) (компан|лиц|человек)|не т(а|от) (компан|человек)|"
                                         r"друг(ой|ая|ого) (компан|человек)|однофамил|другой человек|wrong (person|company)|not the (person|company)|"
                                         r"неверн(ая|ый) (подпис|атрибуц)|misattribut"), re.I)
PREFLIGHT_WORKERS = int(os.getenv("PREFLIGHT_WORKERS", 6))                   # замены кадров идут параллельно: 96% времени этапа — ожидание сети и генерации
PREFLIGHT_PASSES = int(os.getenv("PREFLIGHT_PASSES", 3))                       # проходов проверки кадров; со 2-го прохода проверяются только заменённые слоты
LLM_MODEL_FACTCHECK = os.getenv("LLM_MODEL_FACTCHECK", "openai/gpt-6-astra")   # проверка сценария на выдуманные детали (решение владельца 15.09): №1 AA-Omniscience на 18.09
# роли по аудиту 18.09 (владелец: «каждый этап — лучшая модель»); пусто в .env — LLM_MODEL_HEAVY, как было
LLM_MODEL_RESEARCH = os.getenv("LLM_MODEL_RESEARCH", "openai/gpt-5.6-sol")     # всё с веб-поиском (:online): ресёрч, новости шортсов; нативный поиск OpenAI, №1 Search Arena
# 24.09: Opus 5.5 вместо Opus 5 — $4/$20 за млн токенов против $5/$25 при том же контексте 1M (проверено по прайсу OpenRouter)
LLM_MODEL_WRITER = os.getenv("LLM_MODEL_WRITER", "anthropic/claude-opus-5.5")    # текст диктора: план, части, правка после фактчека; EQ-Bench Longform 86.3 / штампы 5.6 (Qwen3-Max 66.2 / 49.2)
STORY_WORDS = int(os.getenv("STORY_WORDS", 3300))
# 12.10 владелец: испанский канал — мультфильм как у Built On You («La historia COMPLETA de X en N minutos», ~20 мин), темы из stories_es.txt
ES_CARTOON = os.getenv("ES_CARTOON", "0") == "1"
ES_CARTOON_WORDS = int(os.getenv("ES_CARTOON_WORDS", 2900))       # английский черновик; испанский выходит ~на 15% длиннее → ~20–22 мин
ES_CARTOON_UPLOAD = os.getenv("ES_CARTOON_UPLOAD", "0") == "1"
ES_FIRST = os.getenv("ES_FIRST", "1") == "1"
ES_NEW = os.getenv("ES_NEW", "1") == "1"
ES_LANE = os.getenv("ES_LANE", "1") == "1"   # 13.10 владелец «ускорь»: испанская полоса — отдельный процесс `watch-es`, параллельно с английской   # 13.10 владелец: «совсем по-новому» — испанские темы идут в stages/es_cartoon.py   # 13.10 владелец: перевод до раскадровки, озвучка сразу по-испански (без английской)    # 0 — испанский ролик ждёт «да» владельца перед загрузкой
# 13.10: как у Built On You (разбор их кадров work/builtonyou/frames_*.jpg, проба work/es-cartoon/style_v2)
CARTOON_STYLE = (". Hand-drawn editorial illustration in ink and muted watercolor: loose pencil-and-ink linework with light cross-hatching, "
                 "muted earthy palette (warm greys, olive, ochre, faded blue, brick red), soft paper texture. The picture is a vignette with "
                 "rough painterly edges fading into a plain off-white paper background. Ordinary people are simple figures with plain round "
                 "white heads, two dot eyes and expressive eyebrows, normal clothes and bodies; only named real people are drawn as recognizable "
                 "caricatures with real faces, and never add any other celebrity or famous person who is not named in the description. Text appears ONLY where the description gives it in quotes (hand-lettered Spanish capitals, "
                 "spelled exactly); otherwise no words, letters, logos or signs anywhere, no watermark")   # 27.09: ~22–23 мин вместо 32–34 (Astra + владелец: меньше «воды», дешевле); доли частей из плана
if os.getenv("CHANNEL_PROFILE") == "ancestors":
    CARTOON_STYLE = '. Original simple 2D explainer drawing on a pure white background (#FFFFFF). Thick slightly irregular black outlines, flat solid fills, very limited palette: tan and brown, charcoal grey, muted blue, small orange fire accents. Clean large readable shapes, generous empty white space, one clear action or object. People, only when requested, are our own simple round-headed figures with white circular heads, dot eyes, a short mouth line, thin limbs and simple historically plausible layered garments; no copied mascot or celebrity. Night, sky, smoke and firelight are small flat graphic shapes within the white composition, never a painted full-frame backdrop. No watercolor, paper texture, cross-hatching, gradients, painterly edges, cinematic lighting, realistic shading, 3D or photographs. No text, letters, logos, captions or watermarks. Still illustration; no motion blur or camera movement.'
OPEN_WORDS = int(os.getenv("OPEN_WORDS", 300))      # первые ~2 минуты: строже проверка кадров, чаще смена кадров
WRITER_WORDS_FACTOR = float(os.getenv("WRITER_WORDS_FACTOR", 1.0 if "claude" in LLM_MODEL_WRITER else 1.3))   # запас на недописывание: Amazon 18.09 при заказе 819/793 слов Qwen дал 440/455, Opus — 735/764
LLM_MODEL_POLISH = os.getenv("LLM_MODEL_POLISH", "anthropic/claude-sonnet-5")  # вычитка: только удалить/склеить, без новых фактов
LLM_MODEL_SHOTS = os.getenv("LLM_MODEL_SHOTS", "")                            # раскадровка и добивка кадров; пусто — LLM_MODEL_HEAVY (Qwen). Тест 18.09 на 3 кусках Amazon:
                                                                               # Gemini 3.8 Flash — якоря верные, но меньше people/map/split (1 из 3 нарушил «не-broll ≥ 2») и ×4 дороже из-за рассуждений
LLM_MODEL_VISION_FINAL = os.getenv("LLM_MODEL_VISION_FINAL", "anthropic/claude-opus-5.5")   # финальный визуальный QC по контакт-листу (анахронизмы, пустые кадры): Arena Vision №10 против №33 у Sonnet
SHORT_SCRIPT_MODEL = os.getenv("SHORT_SCRIPT_MODEL", LLM_MODEL_WRITER)          # текст шортса: 70 слов; Opus 5 пишет лучше Astra и вдвое дешевле (аудит 18.09)
SHORT_TAGS_PROMPT = os.getenv("SHORT_TAGS_PROMPT", "voice_tags_short_v2")     # 2–4 спокойных тега на шортс (с [excited]/[intense] подача скакала между фразами)
SHORT_TTS_STABILITY = float(os.getenv("SHORT_TTS_STABILITY", 0.5))
SHORT_SPEED = float(os.getenv("SHORT_SPEED", 1.25))                          # речь шортса быстрее (владелец 18.09: «шортс должен быть очень динамичным»); паузы по смыслу выставляются ПОСЛЕ ускорения и не сжимаются
STRICT_GATES = os.getenv("STRICT_GATES", "0") == "1"   # 07.10 владелец «как раньше»: брак кадров/архива — в отчёт, а не стоп (1 — строгий режим 02–06.10)
# 19.10 владелец «пилот да»: четыре EN-ролика пилота (STRATEGY.md, раздел 0.4). Только для них кадр сверяется с текстом
# в preflight, а подмена человека/компании/события до рендера заменяется; глобальный STRICT_GATES не меняется.
PILOT_VIDEOS = [x.strip().lower() for x in os.getenv("PILOT_VIDEOS", "").split(",") if x.strip()]
ES_WEEKDAYS_MSK = [int(x) for x in os.getenv("ES_WEEKDAYS_MSK", "").split(",") if x.strip()]   # дни выхода испанского по МСК, 0 — пн; пусто — раз в два дня

def is_pilot(vid) -> bool:
    v = str(vid or "").lower()
    return bool(v) and "__es" not in v and "-es-" not in v and any(k in v for k in PILOT_VIDEOS)
SHORTS_MOTION = os.getenv("SHORTS_MOTION", "1") == "1"   # 06.10 владелец: шортсы — моушен-шаблоны Blocks/Globe/Versus (stages/motion_shorts.py)
SHORT_STYLE = os.getenv("SHORT_STYLE", "calm-story-v1")  # владелец 05.10: спокойные сцены, без дублирования цифр
FACTCHECK = os.getenv("FACTCHECK", "1") == "1"

# --- картинки и музыка ---
SCENE_IMAGES = os.getenv("SCENE_IMAGES", "1") == "1"                        # фон-картинка на каждую сцену
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "fal-ai/flux-2")                     # FLUX.2 [dev]: вдвое дешевле flux/dev ($0.012/MP) и выше по аренам (аудит 18.09)
IMAGE_MODEL_CHEAP = "fal-ai/flux/schnell"
IMAGE_WIDTH, IMAGE_HEIGHT = int(os.getenv("IMAGE_WIDTH", 1536)), int(os.getenv("IMAGE_HEIGHT", 864))
IMAGE_PRICE_PER_MP = {"fal-ai/flux/dev": 0.025, "fal-ai/flux/schnell": 0.003, "fal-ai/flux-pro/v1.1": 0.04, "fal-ai/flux-2": 0.012,
                      "fal-ai/flux-2/klein/9b": 0.006, "fal-ai/z-image/turbo": 0.005}   # $ за мегапиксель; fal округляет МП ВВЕРХ (1536×864 = 2 МП)
IMAGE_PRICE_FLAT = {"openai/gpt-image-2.5/flare/text-to-image": 0.010, "openai/gpt-image-2.5/sunburst/text-to-image": 0.010,
                    "fal-ai/wan/v2.7/text-to-image": 0.03, "microsoft/mai-image-2.5": 0.05, "fal-ai/reve/text-to-image": 0.04,
                    "fal-ai/bytedance/seedream/v5/lite/text-to-image": 0.035, "fal-ai/flux-pro/v1.1-ultra": 0.06}   # $ за картинку (GPT — medium 1080p)
GPT_IMAGE_QUALITY = os.getenv("GPT_IMAGE_QUALITY", "medium")                 # сцены: medium ≈ $0.01 за 1080p
GPT_IMAGE_QUALITY_THUMB = os.getenv("GPT_IMAGE_QUALITY_THUMB", "high")       # обложка: high ≈ $0.04 за 1920×1080
# Обложка — одна картинка на ролик, на ней держится весь клик: берём лучшую модель, а не сценовую.
THUMB_IMAGE_MODEL = os.getenv("THUMB_IMAGE_MODEL", "openai/gpt-image-2.5/sunburst/text-to-image")   # №1 LMArena, лица и крупный текст; было flux-pro/v1.1-ultra (№95)
THUMB_STYLE = os.getenv("THUMB_STYLE", "poster")   # 15.10 владелец: основной стиль «Плакат»; 19.10 — trio (stages/thumb_trio.py)
THUMB_TRIO_MAIN = os.getenv("THUMB_TRIO_MAIN", "10")   # trio: какой стиль основной (03 постер, 09 комикс, 10 график), два других — в A/B
THUMB_IMAGE_STYLE = (", photorealistic, highly detailed, sharp focus on the face, natural skin texture, cinematic lighting, "
                     "85mm portrait lens, high dynamic range, no text, no lettering, no captions, no watermark, no logos")
KLING_CLIP_PRICE = 0.35                                                     # $ за 5-секундный клип (оценка)
MUSIC_BELOW_DB = float(os.getenv("MUSIC_BELOW_DB", 22))                     # ambient на столько дБ тише голоса (считается по RMS для каждого видео)
MUSIC_VOLUME = float(os.getenv("MUSIC_VOLUME", 0.05))                       # запасное значение, если замер не удался
MUSIC_GENERATE = os.getenv("MUSIC_GENERATE", "0") == "1"
MUSIC_DIRECT = os.getenv("MUSIC_DIRECT", "1") == "1"
MUSIC_FAL_FALLBACK = os.getenv("MUSIC_FAL_FALLBACK", "0") == "1"   # 07.10: fal-музыка ~$0.60/мин (~$17 на ролик) — по умолчанию нет, берём треки music_tracks
RESTORE_ARCHIVE = os.getenv("RESTORE_ARCHIVE", "1") == "1"                  # реставрация архива перед рендером (stages/restore.py, аудит 18.09)
RESTORE_MIN_H = int(os.getenv("RESTORE_MIN_H", 720))                        # клипы ниже этой высоты → Topaz Precision ×2 ($0.20 за 10 с)
RESTORE_MIN_PHOTO = int(os.getenv("RESTORE_MIN_PHOTO", 1400))               # фото меньше по длинной стороне → Topaz Precision HF V3 ($0.08), лица не трогает
RESTORE_MIN_SEC = float(os.getenv("RESTORE_MIN_SEC", 5.0))                  # реставрируем только то, что реально висит на экране (разбор Astra 20.09: сплошной Topaz — $8 на ролик)
RESTORE_MAX_JOBS = int(os.getenv("RESTORE_MAX_JOBS", 18))                   # и не больше стольких файлов за ролик, самые заметные первыми
RESTORE_PHOTO_TARGET = int(os.getenv("RESTORE_PHOTO_TARGET", 2400))         # до какой длинной стороны тянуть фото: Ken Burns приближает кадр до ~1.25×                        # партитура — прямой API ElevenLabs ($0.15/мин), при ошибке — fal ($0.60/мин)                    # если библиотека data/music пуста — сгенерировать (fal stable-audio)

# --- формат story: кадры ---
CLIP_MAX_PER_VIDEO = int(os.getenv("CLIP_MAX_PER_VIDEO", 8))             # сгенерированных видеоклипов на видео (путь B: 8, путь A: 60+)
CLIP_MODEL = os.getenv("CLIP_MODEL", "fal-ai/minimax/hailuo-2.3/standard/image-to-video")   # $0.28 за 6 с 768p; сдержанная анимация фото с людьми (аудит 18.09; hailuo-02 вне топ-15)
CLIP_PRICE = float(os.getenv("CLIP_PRICE", 0.28))
CLIP_SECONDS = int(os.getenv("CLIP_SECONDS", 6))
STOCK_MIN_WIDTH = 1280
STOCK_MAX_SHARE = float(os.getenv("STOCK_MAX_SHARE", 0.15))                 # доля стоковых кадров в story; остальное — генерация
STOCK_MIN_RELEVANCE = float(os.getenv("STOCK_MIN_RELEVANCE", 0.67))        # доля слов запроса в описании клипа Pexels
STORY_SUBTITLES = os.getenv("STORY_SUBTITLES", "0") == "1"              # субтитры в story-формате (у референсов их нет)

# --- формат story: типизированные сцены (docs/scene-grammar.md) ---
SCENE_TYPES = ("broll", "people", "map", "split", "timeline", "montage", "quote", "object", "chart")   # весь каталог (модель может выдать любой)
SCENE_TYPES_RENDERED = ("broll", "people", "map", "quote", "chart")  # SceneRouter: остальные пока показывают только первый слот
SCENE_TYPES_ENABLED = tuple(t.strip() for t in os.getenv("SCENE_TYPES_ENABLED", "broll,people,map,quote").split(",") if t.strip() in SCENE_TYPES_RENDERED)
RICH_TYPES = tuple(t for t in SCENE_TYPES_RENDERED if t != "broll")
SHOT_MAX_BY_TYPE = {"broll": 24, "montage": 30, "split": 30, "people": 36, "map": 36, "timeline": 36, "object": 36, "quote": 36, "chart": 36}   # слов на сцену
SHOT_MAX_BROLL_STILL, SHOT_MIN_BROLL_STILL = 20, 8                          # картинка/архивное фото держит ≤ ~10 с (24 слова при медленном дикторе = 14 с)
SHOT_LATE_STILL = (14, 32)   # 27.09: после первых OPEN_WORDS слов кадр держится ~10 с (мин/макс слов), с медленным движением
SHOT_LATE_FACTOR = 1.35      # богатые сцены после вступления держатся на треть дольше
SHOT_MIN_RICH = 14                                                          # богатая сцена держит не меньше слов (анимация должна отыграть)
SCENE_MIN_SEC = 5.0                                                         # broll короче — сцена сдвигается к границе предложения или выбрасывается (_timeline)
STILL_MAX_SEC = 9.0                                                         # картинка дольше — наезд усиливается (push in hard), статичных кадров не бывает
FILL_LONG_SCENES = os.getenv("FILL_LONG_SCENES", "1") == "1"                 # добивка кадров в сценах длиннее потолка (stages/fill.py; владелец 17.09: кадр висел 35 с)
ARCHIVE_FIRST_BUDGET_SEC = int(os.getenv("ARCHIVE_FIRST_BUDGET_SEC", 1500))     # сумма времени проб «хроника вместо генерации» по всем потокам (≈4 мин по часам при 6 потоках): Netflix 21.09 искал 3,5 часа
ARCHIVE_FIRST_MISS_STOP = int(os.getenv("ARCHIVE_FIRST_MISS_STOP", 12))         # столько промахов подряд — по этой компании хроники нет, дальше сразу генерация
ARCHIVE_FIRST = os.getenv("ARCHIVE_FIRST", "1") == "1"                        # слот под генерацию сперва ищем в хронике: она бесплатна и отличает канал от конвейера (владелец 21.09)
ERA_FOOTAGE = os.getenv("ERA_FOOTAGE", "1") == "1"                          # обезличенная съёмка эпохи вместо генерации (stages/era_footage.py, владелец 17.09)
ERA_MAX_PER_VIDEO = int(os.getenv("ERA_MAX_PER_VIDEO", 45))                 # потолок таких слотов на ролик (каждый — отбор кадра и проверка на vision)
SOUND_SCORE = os.getenv("SOUND_SCORE", "1") == "1"                          # партитура вместо подложки (stages/sound.build): тема на главу, музыка −25 dB под голосом, мастеринг −14 LUFS (владелец 17.09)
MAP_AHEAD_SEC = 6.0                                                         # точка карты, чей якорь звучит позже конца сцены больше чем на столько, — не показывается
VIDEO_MIN_WIDTH = 640                                                       # исходник YouTube уже — не берём (320×240 на 1080p — каша)
XFADE_RICH_SEC = 0.6                                                        # наплыв богатой сцены (колонки people успевают въехать под наплывом — без провала в чернила)
PERSON_RESHOW_WORDS = 260                                                   # PERSON срабатывает снова через ≥ 2 мин текста после прошлого показа
MODERN_ERA_FROM = 1995                                                      # сцены раньше — в prompt «no modern devices, no screens», preflight ловит анахронизм
RICH_MIN_PER_PART = 2                                                       # богатых сцен на часть 2–7 — не меньше
RICH_MAX_SHARE = 0.5                                                        # и не больше половины кадров части
RICH_MAX_PER_VIDEO = {"people": 10, "montage": 5, "split": 6, "quote": 6}
RICH_MAX_PER_PART = {"map": 2, "split": 2, "timeline": 1, "montage": 1, "quote": 1, "object": 1, "chart": 1}
MAX_BIG_NUMBERS = 12                                                        # бюджет крупных цифр от модели (year/object/chart); flash при NUMBER_FLASHES — без лимита
NUMBER_FLASHES = os.getenv("NUMBER_FLASHES", "1") == "1"                    # владелец 16.09: каждая цифра озвучки выносится на экран на своих словах (numbers.py)
FLASH_COUNT = 0                                                             # count-up у flash выключен
ACTIVITY_MODEL = IMAGE_MODEL_CHEAP                                          # иллюстрации занятий в people — всегда schnell
ARCHIVE_SLOTS_MAX = 120                                                     # архивных слотов на видео; сверх — source image
ARCHIVE_VIDEO_MAX = int(os.getenv("ARCHIVE_VIDEO_MAX", -1))                # 08.10 дешёвый режим: видеоклип ищут только первые N архивных слотов (вступление), остальные — фото; -1 — без потолка
CITIES_CSV = ROOT / "orchestrator" / "data" / "cities.csv"                  # geonames cities15000: сверка координат карт
TEXTY_SLOT = r"\b(chart|graph|logo|document|ticker|sign|signage|screen with text|headline|newspaper)\b"   # такие слоты не резолвим как есть

# --- пауза диктора на главах (§3) ---
CHAPTER_LEAD = 0.4          # тишина до карточки: последнее слово части дозвучало
CHAPTER_SEC = 3.4           # карточка на экране
CHAPTER_TAIL = 0.2          # тишина после ухода карточки, затем голос
CHAPTER_GAP = round(CHAPTER_LEAD + CHAPTER_SEC + CHAPTER_TAIL, 3)   # = 4.0, вставляемая тишина
CHAPTER_MIN_CUT_GAP = 0.25  # минимальный зазор между словами, в который можно резать
SFX_BELOW_DB = 7.0          # стингер главы на столько дБ тише диктора (0.45 в тишине пиковал на 10 дБ громче голоса)
MUSIC_INTRO_DB = 6.0        # трек главы стартует с первого места, где его RMS ≥ среднего − столько дБ (тихое интро под карточкой = мёртвая тишина)

# --- плёнка и рендер ---
FILM_LOOK = float(os.getenv("FILM_LOOK", 0.8))                              # 0 → без плёнки
ARCHIVE_X264 = ["-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p"]   # вырезка архивных клипов: было veryfast/crf 23 — клип терял качество дважды (здесь и в рендере)
RENDER_FRAME_TIMEOUT = int(os.getenv("RENDER_FRAME_TIMEOUT", 3600000))   # таймаут кадра Remotion: при паузе на игру
# (tools/game_pause.py) процесс заморожен, а часы идут — со старыми 120 с кадр падал бы сразу после разморозки
RENDER_CRF = int(os.getenv("RENDER_CRF", 18))                               # зерно съедает битрейт: 16 → 33 Мбит/с (6 ГБ на 25 мин), 18 → 20 Мбит/с (4 ГБ), 20 → ~12 Мбит/с
THUMB_ILLUS = os.getenv("THUMB_ILLUS", "0") == "1"   # 29.09 STRATEGY.md: иллюстрация для Test & Compare не делается, пока ролик не набрал 3 500 показов за неделю
DESC_SOURCES = os.getenv("DESC_SOURCES", "0") == "1"   # источники в описании ролика; 20.09 владелец убрал их, возврат — только после его «да»
THUMB_REC = os.getenv("THUMB_REC", "1") == "1"   # 27.09: основная обложка по шаблонам разбора ниши Astra (stages/thumbrec.py); 0 — прежний сплит
RENDER_CONCURRENCY = int(os.getenv("RENDER_CONCURRENCY", 12))               # вкладок Chrome параллельно (i9-12900K: 24 потока, 32 ГБ; 0 — по умолчанию Remotion)
RENDER_TMP = Path(os.getenv("RENDER_TMP") or DATA / "render_tmp")            # промежуточный final и мастеринг (~4 ГБ каждый при crf 18) + TEMP Remotion
                                                                           # (копия папки ролика и загрузки ассетов, ещё ~4 ГБ). 18.09 на C: кончилось место на 96 % рендера → вынесено на E:
RENDER_GL = os.getenv("RENDER_GL", "angle")                                 # angle — GPU через ANGLE (RTX 4080) для фильтров плёнки; пусто — по умолчанию

def film_block(strength: float | None = None) -> dict | None:
    """Блок timeline.film для Remotion; None → слой не монтируется."""
    s = FILM_LOOK if strength is None else float(strength)
    if s <= 0: return None
    return {"strength": round(s, 2), "grain": True, "grain_strength": 0.55, "flicker": True, "scratches": True, "weave": True, "blur": True, "splice": False,
            "grade": True, "vignette": True, "fade": True, "leaks": False, "soft": True}   # «старая плёнка»: выцветание, мягкость; без засветок и вспышек (владелец, 16.09)

# --- бюджет ---
BUDGET_USD = float(os.getenv("BUDGET_USD", 30.0))  # Estimated variable generation budget per episode.

def read(p: Path) -> str: return Path(p).read_text(encoding="utf-8")
def write(p: Path, s: str): Path(p).write_text(s, encoding="utf-8")

def music_moods() -> list[str]:
    """Настроения из имён треков в data/music (calm_01.mp3 → calm)."""
    import re
    seen = []
    for p in sorted(MUSIC.glob("*")):
        if p.suffix.lower() not in (".mp3", ".wav", ".m4a", ".ogg"): continue
        m = re.match(r"([a-zA-Z]+)", p.stem)
        if m and m.group(1).lower() not in seen: seen.append(m.group(1).lower())
    return seen or ["calm", "dramatic", "bright"]

def image_price(model: str, w: int, h: int) -> float:
    import math
    if model in IMAGE_PRICE_FLAT: return IMAGE_PRICE_FLAT[model]
    return IMAGE_PRICE_PER_MP.get(model, 0.04) * math.ceil(w * h / 1e6)

MANIFEST_KEYS = ("AUTO_PIPELINE", "AUTO_PIPELINE_HOUR", "AUTO_PIPELINE_UNTIL", "AUTO_PIPELINE_PER_DAY", "AUTO_BACKLOG", "ES_AUTO", "ES_QUEUE_SHARE", "AUTO_SCRIPT_APPROVE", "AUTO_APPROVE",
                 "QC_SHIP_ANYWAY", "PREFLIGHT_PASSES", "PREFLIGHT_MAX_FIX", "PREFLIGHT_CHEAP_FIRST", "PREFLIGHT_WORKERS", "ARCHIVE_FIRST", "OPENING_GATE", "THUMBV_AUTO", "STILLCHECK",
                 "ERA_FOOTAGE", "ERA_MAX_PER_VIDEO", "ARCHIVE_VIDEO_MAX", "RESTORE_ARCHIVE", "RESTORE_MAX_JOBS", "RESTORE_MIN_SEC", "SHORTS_PER_VIDEO", "SHORTS_SOURCE",
                 "SHORT_HOUR_ET", "SHORT_HOURS_ET", "SHORT_DAYS", "PUBLISH_HOUR_ET", "PUBLISH_WEEKDAYS_ET", "PUBLISH_NOT_BEFORE", "MIN_FREE_GB_START", "FINAL_KEEP_DAYS", "FINAL_RETENTION", "FINAL_ARCHIVE_DIR", "STORY_WORDS", "TTS_MODE", "TTS_TARGET_WPM", "TTS_TEMPO", "IMAGE_MODEL",
                 "LLM_MODEL_WRITER", "LLM_MODEL_FACTCHECK", "LLM_MODEL_VISION", "LLM_MODEL_VISION_CHEAP", "LLM_MODEL_VISION_FINAL", "BUDGET_USD")

def manifest() -> dict:
    """Фактические значения настроек в этом процессе (разбор Astra 21.09: описание расходилось с defaults, потому что .env
    переопределяет их, а старые процессы жили со старым кодом). Печатается на старте очереди и сохраняется в payload ролика."""
    g = globals()
    m = {k: g.get(k) for k in MANIFEST_KEYS if k in g}
    m["ELEVENLABS_VOICE_ID"] = os.getenv("ELEVENLABS_VOICE_ID")
    m["DATA_DIR"] = str(DATA)
    try:
        import subprocess
        m["code"] = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        from datetime import datetime
        newest = max((p.stat().st_mtime for p in (ROOT / "orchestrator").rglob("*.py")), default=0)
        m["code"] = "orchestrator изменён " + datetime.fromtimestamp(newest).strftime("%d.%m %H:%M")
    return m

def prompt(name: str, **kw) -> str:
    """Подстановка {name} без str.format — в промптах есть литеральные JSON-скобки."""
    text = read(PROMPTS / f"{name}.md")
    for k, v in kw.items():
        text = text.replace("{" + k + "}", str(v))
    return text

def channel_prompt() -> str:
    from datetime import date
    if os.getenv("CHANNEL_PROFILE") == "ancestors":
        return ("You produce Ordinary Ancestors, an English illustrated history channel about ordinary daily life. "
                "Use only supplied archaeological evidence. Distinguish known finds from plausible reconstruction, "
                "and never invent precise facts, quotations or named prehistoric people. No corporate-history framing. "
                "Follow the requested JSON schema exactly.")
    base = prompt("channel")
    # модель не знает текущий год и считает свежие отчётности выдумкой — говорим дату явно
    base += (f"\n\nСЕГОДНЯ {date.today():%d.%m.%Y}. Твои знания могут отставать на год и больше: отчётности и события "
             "из результатов веб-поиска считай реальными и актуальными, не отвергай их как «будущее».")
    learnings = DATA / "learnings.md"
    if learnings.exists():
        base += "\n\nЧТО УЖЕ ВЫУЧИЛИ ПО ДАННЫМ КАНАЛА:\n" + read(learnings)
    return base

_TOOLS: dict = {}

def _runs(path: str) -> bool:
    """Бинарник не просто лежит, а запускается. На Windows копия ffprobe без соседних DLL падает с 3221225781
    (STATUS_DLL_NOT_FOUND) — 20.09 такая копия в data/bin попала в PATH и уронила QC уже после готового рендера."""
    import subprocess
    try: return subprocess.run([path, "-version"], capture_output=True, timeout=25).returncode == 0
    except Exception: return False

def _find_tool(name: str) -> str:
    """ffmpeg/ffprobe: PATH, затем бинарники Remotion (@remotion/compositor-*), затем полный ffmpeg из imageio.
    Каждый кандидат проверяется запуском — сломанный в PATH больше не побеждает рабочий."""
    if name in _TOOLS: return _TOOLS[name]
    cands = []
    p = shutil.which(name)
    if p: cands.append(p)
    for c in (REMOTION / "node_modules" / "@remotion").glob("compositor-*"):
        cands += [str(c / f"{name}{ext}") for ext in ("", ".exe") if (c / f"{name}{ext}").exists()]
    if name == "ffmpeg":
        try:
            import imageio_ffmpeg; cands.append(imageio_ffmpeg.get_ffmpeg_exe())
        except Exception: pass
    for c in cands:
        if _runs(c):
            if c != cands[0]: print(f"[config] {name}: {cands[0]} не запускается, беру {c}", flush=True)
            _TOOLS[name] = c; return c
    raise RuntimeError(f"{name} не найден или не запускается (проверено: {cands or 'ничего'}): "
                       f"поставь ffmpeg в PATH или сделай npm install в remotion/")

def ffprobe() -> str: return _find_tool("ffprobe")
def ffmpeg() -> str: return _find_tool("ffmpeg")

def npx() -> str:
    p = shutil.which("npx.cmd") if os.name == "nt" else None
    return p or shutil.which("npx") or "npx"
