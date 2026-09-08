# Препроцессинг МТР: Excel → ResourceItem → NormalizedItem

Пайплайн нормализации позиций материально-технических ресурсов для пилота мониторинга цен.

```
Excel ведомость ──► Стадия 0 ──► ResourceItem JSON
                         │         regex КСР + lookup в справочнике
                         ▼
                   Стадия 1a ──► + characteristics (regex)
                         │
                         ▼
                   Стадия 1b ──► NormalizedItem JSON
                                 LLM-название + material + каталог
```

Сквозной ключ — `item_id` (`raw-0001`, `raw-0002`, …). Его генерирует стадия 0.

---

## Что нужно на вход

Положите Excel-файлы **в корень репозитория** (рядом с `run_pipeline.py`):

| Файл | Роль | Обязателен |
|------|------|------------|
| `Тестовый.xlsx` | Тестовая выборка (~60 позиций) | для тестового прогона |
| `6_Пример отчета мониторинга цен.xlsx` | Полная ведомость (~1589 строк) **и** каталог (колонки P/V/AB) | для полного прогона и для стадии 1b |
| `Выгрузка КСР.xlsx` | Справочник Классификатора строительных ресурсов | да |

Ожидаемые колонки исходной ведомости (лист 1, строка 1 — заголовок):

| Колонка Excel | Поле JSON | Обязательно |
|---------------|-----------|-------------|
| № КС | `ks_number` | нет |
| Шифр сметы | `estimate_code` | нет |
| 1-Труд / 2-ЭММ / 3-МАТ | `resource_type` | нет |
| Обоснование | `justification_source` | нет (из него regex достаёт КСР) |
| Наименование | `name_raw` | **да** |
| Ед. изм. | `unit_raw` | **да** |
| Расход | `consumption` | нет |
| Базовая цена | `base_price` | нет |
| Стоимость | `total_cost` | нет |

Подробный маппинг: [`docs/field_mapping.md`](docs/field_mapping.md). Схема объектов: [`json_schema_v05.md`](json_schema_v05.md).

---

## Установка

Python 3.10+.

```bash
cd Preprocessing
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Токен нейрошлюза (только для стадии 1b)

1. Скопируйте шаблон:
   ```bash
   cp .env.local.example .env.local
   ```
2. В `.env.local` укажите Bearer-токен `ai.rt.ru`:
   ```
   NEIROSHLYUZ_TOKEN=eyJ...
   ```
3. Файл `.env.local` в git не попадает.

Без токена работают стадии 0 и 1a (парсинг + regex). Стадия 1b (`--stage1b`) без токена упадёт.

---

## Как запускать

По умолчанию пайплайн читает **тестовый** Excel и пишет файлы с суффиксом `_test`.

### 1. Тестовый прогон: стадии 0 + 1a (без LLM)

```bash
python run_pipeline.py --stats
```

**Вход:** `Тестовый.xlsx` + `Выгрузка КСР.xlsx`  
**Выход в `output/`:**

- `resource_items_test.json` — ResourceItem (10 полей + КСР)
- `resource_items_characteristics_test.json` — то же + `characteristics`

### 2. Тестовый прогон: + стадия 1b (LLM)

```bash
python run_pipeline.py --stage1b --stats
```

**Дополнительный вход:** каталог `6_Пример отчета мониторинга цен.xlsx` (колонки «Наименование 1/2/3»).  
**Дополнительный выход:** `output/normalized_items_test.json`

Смоук на нескольких позициях:

```bash
python run_pipeline.py --stage1b --limit 3 --stats
```

Только LLM по уже готовому 1a:

```bash
python run_pipeline.py \
  --from-characteristics output/resource_items_characteristics_test.json \
  --suffix _test \
  --stage1b --stats
```

### 3. Полный прогон (~1589 позиций)

```bash
python run_pipeline.py \
  --input "6_Пример отчета мониторинга цен.xlsx" \
  --suffix "" \
  --stage1b --stats
```

**Выход (без суффикса):**

- `output/resource_items.json`
- `output/resource_items_characteristics.json`
- `output/normalized_items.json` (если указан `--stage1b`)

Полная 1b — порядка 1589 вызовов модели (десятки минут).

Полезные флаги:

| Флаг | Смысл |
|------|--------|
| `--input` | Excel ведомости |
| `--ksr` | Справочник КСР |
| `--catalog` | Каталог для поиска похожих имён (P/V/AB) |
| `--suffix` | `_test` или `""` для имён файлов |
| `--stage1b` | Включить LLM |
| `--limit N` | Обработать только первые N позиций в 1b |
| `--stats` | Печать покрытия полей |
| `--from-resource-items` | Пропустить Excel, взять готовый JSON стадии 0 |
| `--from-characteristics` | Пропустить 0+1a, взять JSON стадии 1a |

---

## Что ожидать на выходе

Все файлы — JSON-массивы объектов. Каталог `output/` создаётся автоматически.

### Стадия 0 — `resource_items*.json`

```json
{
  "item_id": "raw-0001",
  "ks_number": 1,
  "estimate_code": "ЛСР-03-05-602Э",
  "resource_type": 3,
  "justification_source": "ТЦ_20.2.07.00_...",
  "ksr_code": "08.4.03.03-0009",
  "ksr_name": "Прокат арматурный ...",
  "name_raw": "Конструкции кабельные ...",
  "unit_raw": "кг",
  "consumption": 27000.0,
  "base_price": 398.56,
  "total_cost": 10761120.0
}
```

- `ksr_code` — regex `\d+\.\d+\.\d+\.\d+-\d+` из «Обоснования»; нет кода → `null`.
- `ksr_name` — наименование из `Выгрузка КСР.xlsx`; код не найден → `null`.

Ориентир на тесте (60 строк): ~47/60 с кодом КСР, ~32/47 найдены в справочнике.  
На полной выборке (1589): ~1370/1589 (86%) с кодом, ~896/1370 (65%) найдены в справочнике.

### Стадия 1a — `resource_items_characteristics*.json`

Те же поля + объект `characteristics` из `name_raw` (только regex, без LLM):

`grade`, `dn`, `peak_pressure`, `max_temperature`, `working_medium`, `safety_class`, `connection_type`, `control_type`, `dimensions`, `standards`, `material` (если в тексте есть `материал - …`).

Нет в тексте → `null` / `[]`. `material_type` на этой стадии всегда `null`.

Ориентир (1589 строк): ~43% позиций имеют хотя бы одну характеристику.

### Стадия 1b — `normalized_items*.json`

Добавляется:

| Поле | Источник |
|------|----------|
| `name_normalized` | LLM: короткое имя без хвоста ТХ |
| `characteristics.material` | LLM: вещество/сплав **только из `name_raw`** |
| `characteristics.material_type` | LLM: вид изделия (кабель, трубопровод, …) |
| `catalog_matches` | CODE: похожие имена из каталога P/V/AB |
| `unit_normalized` | CODE: `шт.` → `шт`, `м3` → `м³` |
| `confidence` | оценка LLM |
| `normalization_method` | `code+llm` или `code` при ошибке вызова |
| `catalog_used` | `true`, если каталог что-то нашёл |
| `notes` | комментарий LLM |

Regex-поля (`dn`, `pmax`, …) **не перезаписываются** моделью.

Ориентир на тесте (60 строк): 60/60 `code+llm`; `material_type` ~97%; `material` ~68%.

---

## LLM (стадия 1b)

| | |
|--|--|
| Шлюз | `https://ai.rt.ru/api/1.0` |
| Метод | `POST /lleopold/chatMulti` |
| Модель | `Qwen/Qwen3-Next-80B-A3B-Instruct-FP8` |
| temperature | 0.2 |
| max_new_tokens | 512 |

Промпт и клиент: `preprocessing/stage1b_llm.py`, `preprocessing/neuro_gateway.py`.

Правила для модели: `material` — вещество/сплав из текста (`нж`, `угл.ст.`, «нержавеющая сталь»), не вид изделия. Вид изделия — только `material_type`. Нельзя додумывать ТХ, которых нет в `name_raw`.

---

## Структура репозитория

```
run_pipeline.py              CLI
requirements.txt
preprocessing/
  stage0_parser.py           Excel → ResourceItem
  ksr_lookup.py              regex КСР + справочник
  stage1a_characteristics.py regex характеристик
  characteristics.py         паттерны
  stage1b_llm.py             LLM-нормализация
  catalog.py                 поиск по каталогу
  neuro_gateway.py           клиент ai.rt.ru
  models.py
docs/field_mapping.md
json_schema_v05.md
```
