Раскадровка части {part_no} документального рассказа уже составлена, но в ней не хватает сцен нужных типов. Ниже — фразы-кандидаты из текста этой части с подсказками (люди из реестра PERSON, места PLACE, сравнения COMPARE). Для каждого запроса верни ОДНУ сцену указанного типа, стоящую на одной из фраз-кандидатов (anchor — первые 5 слов той фразы, дословно).

Нужно:
{requests}

Фразы-кандидаты:
{candidates}

Факты (для fact_id):
{facts_json}

Схема сцены и слота — как в основной раскадровке:
{"id":"r1","anchor":"первые 5 слов фразы","type":"people|map|split","slots":[{"source":"archive|image|stock","query":"…","query_alt":"…","media":"photo|video|any","caption":"кто/что, год (archive)","prompt":"≤20 слов, англ., без букв — обязателен","focus":"одна вещь"}],"data":{…},"motion":"slow push in|static|…"}
- people: data {"layout":"solo|duo|trio","persons":[{"name":"как в реестре","role":"…","years":"…","side":"left|right|center","activity_prompt":"≤20 слов: ПРЕДМЕТЫ и руки его дела, без людей, без букв"}]}; slots — по одному archive-слоту-портрету на персону в том же порядке. Если в запросе названо, про кого нужна сцена, — persons только эти люди (solo), anchor — первые слова той полуфразы, где он назван («Jobs, charismatic and restless»).
- map: data {"title":"регион","zoom":"region|country|world","points":[{"name":"…","country":"US","admin1":"California","lat":0,"lon":0,"label":"≤3 слов","anchor":"первые слова фразы про место"}],"route":[0,1] или null,"distance_label":"…" или null}; slots — 0–1 слот inset с архивным видом города.
- split: data {"mode":"vs|then_now","left":{"label":"…"},"right":{"label":"…"}}; slots — ровно два.

Верни JSON: {"shots":[...]}
