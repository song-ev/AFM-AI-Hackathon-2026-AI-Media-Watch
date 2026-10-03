# Техническая документация AI Media Watch

Система для АФМ РК: автоматическое выявление нелегальных казино / финансовых
пирамид / инвест-мошенничества в видео Instagram / TikTok / YouTube.

Документ описывает **техническую часть**: стек, архитектуру, модели данных,
пайплайн анализа и четыре функции, добавленные в этой итерации (NLP-анализ
комментариев, QR-коды, PDF-досье, детекция аномалий трендов).

---

## 1. Стек и инфраструктура

| Слой | Технология |
| --- | --- |
| Backend | Django + Django REST Framework |
| Очереди задач | Celery (chord/group), брокер — Redis |
| БД | PostgreSQL (собственный экземпляр, `DATABASE_URL`) |
| LLM | OpenRouter / Qwen через единый клиент `core/llm.py` (`call_llm` / `call_llm_json`) |
| ML / CV | Whisper (ASR), OpenCV (кадры, QR), Tesseract (OCR), ultralytics, resemblyzer/face_recognition (отпечатки), numpy/scipy |
| PDF | ReportLab + matplotlib (графики) |
| Frontend | Next.js (App Router) + React 18 + TypeScript |
| Карты / графики | react-leaflet v4, recharts |
| Данные на фронте | TanStack Query (`@tanstack/react-query`) |

**Ключевые ограничения окружения** (важны для понимания кода):
- БД общая → тестовую БД создать нельзя; медиа-файлы скачивались на других
  машинах, локально их часто нет (`Video.resolved_file_path` ре-рутит путь).
- React 18 → только `react-leaflet@4`; карты рендерятся client-only через
  `dynamic(..., { ssr: false })`.
- **Fail-loud**: модуль без зависимости пишет ошибку и не вносит вклад в
  вердикт — никогда не выдаёт выдуманный «чистый» результат.

---

## 2. Django-приложения (домены)

| App | Назначение |
| --- | --- |
| `ingestion` | Сбор видео, платформы, аккаунты, комментарии, пакеты, эфиры |
| `screening` | Stage-1 быстрый скрининг (микросервисы-модули) |
| `deepanalysis` | Stage-2 глубокий анализ, синтез риска, граф рассуждений |
| `incidents` | Карточки инцидентов, цепочка доказательств, дашборды, **досье** |
| `learning` | Само-обучение словаря, ML-модель риска, **детекция аномалий** |
| `accounts` | Пользователи, роли, метки аналитиков |
| `bankapi` | Внешний API для риск-чека платёжных реквизитов |
| `core` | Общие модели/утилиты, `llm.py`, права, пагинация |

Все доменные модели наследуют `core.models.TimeStampedModel`
(`created_at` / `updated_at`).

---

## 3. Архитектура анализа: 4 стадии

```
СБОР (ingestion)
   │  yt-dlp скачивает, EvidenceChainEntry фиксирует SHA-256 в момент сбора
   ▼
STAGE-1 СКРИНИНГ (screening, Celery chord)
   │  8 модулей-сигналов + гео + запись наблюдений ключевых слов
   │  вердикт: CLEAN / SUSPICIOUS / ERROR
   ▼ (только SUSPICIOUS)
STAGE-2 ГЛУБОКИЙ АНАЛИЗ (deepanalysis)
   │  транскрипция → лексика → семантика, фейк-скрин, отпечаток личности
   │  синтез риск-скора + граф рассуждений → создание Incident
   ▼
ИНЦИДЕНТ + ДАШБОРДЫ (incidents)
   карточка, ДОСЬЕ PDF, тренды, гео-карта, аномалии
```

### 3.1 Stage-1 — оркестрация
[screening/tasks.py](screening/tasks.py): `run_stage1_screening` собирает **chord** —
4 модуля в `group()` параллельно, затем callback `aggregate_stage1_results`,
который добавляет ещё 4 модуля и считает вердикт.

| Модуль (`ScreeningSignal.Module`) | Сервис | Что делает |
| --- | --- | --- |
| `frame_analysis` | `visual_analysis.py` | кадры + OCR + логотипы |
| `quick_audio` | `audio_analysis.py` | быстрый аудио-скрининг |
| `metadata` | `metadata_analysis.py` | описание/хэштеги/профиль |
| `social_context` ⭐ | `social_context_analysis.py` | **NLP комментариев / накрутка** |
| `adversarial` | `adversarial_defense.py` | кросс-проверка обхода |
| `payment` | `payment_extraction.py` | реквизиты Kaspi/карта/IBAN/крипто |
| `brand_link` ⭐ | `brand_link_analysis.py` | казино-бренды + ссылки + **QR** |
| `audio_forensics` | `audio_forensics.py` | просодия, синтетический голос |

Каждый сигнал — строка `ScreeningSignal` ([screening/models.py](screening/models.py)) с
`is_triggered`, `confidence ∈ [0,1]`, `error`, `raw_output` (JSON-деталь).

### 3.2 Stage-2 — глубокий анализ
[deepanalysis/tasks.py](deepanalysis/tasks.py) `run_stage2_analysis`, шаги fail-loud,
ошибки копятся в `DeepAnalysisResult.step_errors`:
- **E1** транскрипция (Whisper) → `Transcript`; лексический разбор → `TranscriptFlag`;
  семантика (LLM) → флаги ложной срочности.
- **E2** детекция фейковых скриншотов выплат → `FakeScreenshotDetection`.
- **E3** дактилоскопия личности → `IdentityFingerprint` / `IdentityLink` (рецидив).
- **E4** синтез: `compute_risk_score` → `DeepAnalysisResult.risk_score`,
  `build_and_save_reasoning_graph` → `ReasoningNode`/`ReasoningEdge`, создание
  `Incident` с авто-резюме (LLM) и извлечением промокодов/Telegram.

### 3.3 Формула риска ([synthesis.py](deepanalysis/services/synthesis.py))
`compute_risk_score` суммирует вклады (нормировка к 0–100, порог триггера 60):

| Источник | Вклад |
| --- | --- |
| payment | 25 |
| brand_link | 22, до **50** при явном бренде/QR |
| audio_forensics | 20 |
| **social_context** ⭐ | **10 + 20 · manipulation_index** |
| frame/quick_audio/metadata | 15 / 15 / 12 |
| транскрипт-флаг | 5 / 10 / 20 по важности |
| фейк-скриншот | 30 |
| рецидив личности | 40 |

**Порог уверенности (floor).** Явный бренд казино / ставочный QR / ≥3 азартных
термина — почти достоверный признак нелегального гэмблинга. Чтобы аддитивная
сумма не «разбавляла» блатантное казино до ~65-70, после агрегации применяется
пол: **75** при явном гэмблинге и **90** при подтверждении вторым независимым
сигналом (реквизиты / аудио-форензика / сильный транскрипт-флаг / фейк-скриншот /
рецидив). Пол только повышает балл (разница добавляется как отдельный вклад) и
срабатывает лишь на сильном бренд-сигнале — слабые/неоднозначные не инфлируются.

`priority_score = risk × log(подписчики+1) × e^(−часы/48)` — сортировка очереди.

---

## 4. Функция 1 — NLP-анализ комментариев и накрутки (офлайн)

**Файл:** [screening/services/social_context_analysis.py](screening/services/social_context_analysis.py)
**Решение:** офлайн-правила (без LLM) — быстро, бесплатно, детерминированно.

### Алгоритм
`analyze_comment_section(comments)` — чистая функция, считает по каждому
комментарию bot-score ∈ [0,1] из взвешенных эвристик:

| Признак | Реализация | Вклад |
| --- | --- | --- |
| Шаблон бот-похвалы | regex `BOT_TEMPLATE_PATTERNS` (благодарность + выплата) | +0.55 |
| Сумма + благодарность | `_MONEY_RE` + лексикон | +0.3 |
| Эмодзи-спам | плотность эмодзи в коротком тексте | +0.2 |
| Автосгенерированный ник | `_BOT_USERNAME_RE` (`user1428573`, `id7740…`) | +0.2 |
| Реальный скепсис | лексикон `SKEPTIC_TERMS` (`скам/развод`) → потолок 0.15 | сброс |

**Индекс накрутки** (степень фальсификации секции):
```
manipulation_index = 0.6·доля_ботов + 0.35·доля_дублей + скепсис_среди_похвалы
```
Дубли ловятся нормализацией текста (снятие эмодзи/пунктуации) и группировкой
идентичных строк. Тональность — лексиконный счёт positive/negative/neutral.

### Выход (`raw_output`)
`manipulation_index`, `bot_count/human_count`, `sentiment`,
`duplicate_clusters`, `bot_comments[]`, `skeptic_comments[]`, `verdict`.
Та же функция переиспользуется в PDF-досье.

### Интеграция
- Триггер при `manipulation_index ≥ 0.45` или наличии реальных скептиков.
- Вклад в риск через ветку `social_context` в `compute_risk_score`.
- Выводится в `categories` и в карточке инцидента, и на странице анализа
  (карточка `CommentsCard` в `CategoryFindings.tsx`).

---

## 5. Функция 2 — QR-коды (декод + репутация домена)

**Файл:** [screening/services/brand_link_analysis.py](screening/services/brand_link_analysis.py)
**Решение:** декод + оценка репутации домена, **без** сетевых запросов
(безопасно — не обращаемся к мошенническим доменам с сервера).

- `decode_qr_from_frames(frames)` — `cv2.QRCodeDetector` по извлечённым кадрам;
  OpenCV опционален (если нет — QR помечается недоступным, остальное работает).
- Декодированная ссылка прогоняется через `score_link()`: подозрительные TLD
  (`.win/.bet/.casino/...`), сократители ссылок, бренд-домены, Telegram → балл 0–1
  с причинами.
- В UI ([CategoryFindings.tsx](frontend/components/analyze/CategoryFindings.tsx) BrandCard)
  показывается декод, конечный домен, % репутации и причины.

---

## 6. Функция 3 — PDF-досье «Собрать досье»

**Файл:** [incidents/dossier.py](incidents/dossier.py) · **Эндпоинт:**
`GET /api/incidents/<id>/dossier/` (`IncidentDossierView`)
**Решение:** backend ReportLab (стабильно на Windows, без системных зависимостей).

### Реализация
- `build_incident_dossier(incident) -> bytes` — один самодостаточный PDF.
- **Кириллица:** регистрируется `DejaVuSans` из данных matplotlib
  (`matplotlib.get_data_path()/fonts/ttf`) — ReportLab сам по себе кириллицу
  не рендерит.
- **Графики:** matplotlib (Agg) → PNG в память → встраивается:
  гейдж риск-скора (donut) + горизонтальный бар-чарт факторов из `ReasoningNode`.
- **Содержимое:** вердикт + статус, резюме, аккаунт/видео, гео, факторы риска,
  все категории (реквизиты / бренды / QR / аудио / накрутка комментариев),
  подозрительные фразы транскрипта, скриншоты кадров, промокоды/Telegram,
  цепочка SHA-256, дисклеймер.
- **Скриншоты** встраиваются только если файл есть локально (общее хранилище
  может отсутствовать на узле) — иначе примечание.
- **Фронтенд:** кнопка на карточке инцидента качает blob через `apiClient`.

`reportlab` добавлен в `requirements.txt`.

---

## 7. Функция 4 — Детекция аномалий трендов (прогноз)

**Сервис:** [learning/anomaly.py](learning/anomaly.py) · **Эндпоинт:**
`GET /api/dashboard/keyword-anomalies/` (`KeywordAnomaliesView`, кэш)

### Новые модели ([learning/models.py](learning/models.py), миграция `learning 0003`)

**`KeywordObservation`** — одно появление термина в видео, датированное и с
регионом. Источник временного ряда частот.
| Поле | Назначение |
| --- | --- |
| `term`, `category` | нормализованный термин и его тип |
| `region` | регион из `Video.geo_region` (для анализа «по региону») |
| `observed_on` (Date) | дата видео (`posted_at`/`collected_at`) |
| `source` | brand / gambling_term / hashtag / keyword |
| `video` (FK, SET_NULL) | привязка к видео для сэмплов |

Индексы: `(term, observed_on)`, `(region, observed_on)`, `(observed_on)`.

**`KeywordAnomaly`** — один зафиксированный всплеск `(term, region, day)`.
| Поле | Назначение |
| --- | --- |
| `current_count` | частота в день всплеска |
| `baseline_avg` | средняя частота базового периода |
| `pct_change`, `z_score` | % прироста и z-оценка |
| `severity` | low / medium / high |
| `status` | new / acknowledged / dismissed |
| `sample_video_ids` (JSON) | примеры видео |

Уникальность `(term, region, observed_on)`.

### Алгоритм детекции
1. `record_keyword_observations(video)` — вызывается в
   `aggregate_stage1_results` после скрининга: берёт бренды + азартные термины
   из сигнала `brand_link` и хэштеги, дедупит, идемпотентно пишет наблюдения.
2. `detect_anomalies(...)` — для каждого `(term, region)`, появившегося в
   референс-день:
   - базовая линия = частоты по дням за `baseline_days` (по умолчанию 7),
     пропущенные дни = 0 (новое слово стартует с нуля);
   - `mean`, `std` (чистый Python, без numpy);
   - `pct_change = (current − mean)/mean·100`, `z = (current − mean)/std`;
   - **всплеск**, если `current ≥ 3` И `pct ≥ 100%` И (`z ≥ 2` или база = 0);
   - severity по порогам pct/z; результат upsert-ится в `KeywordAnomaly`.
3. `keyword_series(term, ...)` — дневной ряд для спарклайна.

Эндпоинт запускает детектор «вживую» (кэш на несколько минут) и добавляет
спарклайн к топ-всплескам.

### UI
[components/trends/AnomalyAlerts.tsx](frontend/components/trends/AnomalyAlerts.tsx) на
странице «Тренды»: лента алертов «'Авиатор' +400% за 24ч · Алматы» со
спарклайнами (recharts AreaChart) и цветовой severity.

### Команды управления
```bash
python manage.py backfill_keyword_observations [--limit N]   # из отскринённых видео
python manage.py detect_keyword_anomalies [--no-region]      # запуск детектора
python manage.py seed_keyword_spike --term авиатор --region Алматы --current 24  # демо
```

---

## 8. Эфир (live) — анализ в реальном времени

**Файлы:** [ingestion/services/live_capture.py](ingestion/services/live_capture.py),
задача `monitor_live_session`. **Модели:** `LiveSession`, `LiveAlert`.

```
yt-dlp резолвит манифест эфира
  → ffmpeg пишет чанк (по умолчанию 30с, -c copy без перекодирования)
  → регистрируется как Video
  → проходит ТОТ ЖЕ Stage-1 скрининг (включая накрутку, QR, бренды)
  → при срабатывании создаётся LiveAlert (риск + причины), пока стрим идёт
```
`max_chunks` (по умолчанию 120) — предохранитель; остановка кнопкой «Стоп» или
`DELETE /api/ingestion/live/<id>/`. Сессия копит `max_risk_score`, `alerts_count`.

---

## 9. API (основные эндпоинты)

| Эндпоинт | Назначение |
| --- | --- |
| `POST /api/ingestion/videos/` | одиночное видео по ссылке |
| `POST /api/ingestion/{bulk,parse,folder}/` | пакетный сбор → `BatchJob` |
| `GET /api/ingestion/batches/<id>/` | прогресс пакета |
| `POST/GET/DELETE /api/ingestion/live/...` | эфиры |
| `GET /api/ingestion/videos/<id>/status/` | статус пайплайна + категории |
| `GET /api/incidents/` · `/<id>/` | очередь и карточка инцидента |
| `GET /api/incidents/<id>/dossier/` ⭐ | **PDF-досье** |
| `GET /api/incidents/<id>/reasoning-graph/` | граф рассуждений |
| `GET /api/incidents/<id>/evidence-chain/` | цепочка доказательств |
| `GET /api/dashboard/trends/` · `geography/` · `geo-points/` | дашборды |
| `GET /api/dashboard/keyword-trends/` | словарь сленга |
| `GET /api/dashboard/keyword-anomalies/` ⭐ | **всплески ключевых слов** |
| `GET /api/dashboard/roi/` | ROI системы |
| `GET/POST /api/learning/...` | словарь, ML-модель риска |

Права: `IsAnalystOrAbove` (аналитик+) и `IsAfmLeadOrAbove` (руководство) —
дашборды трендов под руководством, гео-точки и инциденты под аналитиком.

---

## 10. Frontend (структура)

- App Router: `app/(dashboard)/` — `analyze`, `incidents/[id]`, `trends`,
  `queue`, `connections`.
- API-слой: `lib/api/*` (хуки TanStack Query): `incidents.ts`, `dashboard.ts`,
  `ingestion.ts`, `batch.ts`, `live.ts`.
- Компоненты по доменам: `components/analyze` (пайплайн, категории, batch/live),
  `components/incident` (карточка, граф, таймлайн), `components/trends`
  (графики, **AnomalyAlerts**), `components/geo`, `components/ui` (примитивы).

Изменения этой итерации на фронте:
- `CategoryFindings.tsx` — карточка `CommentsCard` (накрутка) + расширенный
  вывод QR (домен + репутация + причины).
- `AnomalyAlerts.tsx` — новая панель всплесков на «Трендах».
- Кнопка «Собрать досье (PDF)» на карточке инцидента.
- Типы в `lib/api/ingestion.ts` (+`social_context`), `lib/api/dashboard.ts`
  (`useKeywordAnomaliesQuery`).

---

## 11. Сводка изменений этой итерации

**Backend**
- `screening/services/social_context_analysis.py` — переписан (офлайн NLP).
- `screening/tasks.py` — вызов `record_keyword_observations`.
- `deepanalysis/services/synthesis.py` — ветка риска `social_context`.
- `learning/models.py` — `KeywordObservation`, `KeywordAnomaly` (+миграция 0003).
- `learning/anomaly.py` — сервис детекции (новый).
- `learning/management/commands/` — `backfill_keyword_observations`,
  `detect_keyword_anomalies`, `seed_keyword_spike`.
- `learning/admin.py` — админка новых моделей.
- `incidents/dossier.py` — генератор PDF (новый).
- `incidents/views.py` + `urls.py` — `IncidentDossierView`.
- `incidents/dashboard_views.py` + `dashboard_urls.py` — `KeywordAnomaliesView`.
- `incidents/serializers.py`, `ingestion/views.py` — `social_context` в категориях.
- `requirements.txt` — `reportlab`.

**Frontend**
- `components/analyze/CategoryFindings.tsx`, `components/trends/AnomalyAlerts.tsx`,
  `app/(dashboard)/incidents/[id]/page.tsx`, `app/(dashboard)/trends/page.tsx`,
  `lib/api/dashboard.ts`, `lib/api/ingestion.ts`.

**Проверки:** `manage.py check` — чисто; `tsc --noEmit` — чисто; досье рендерит
валидный `%PDF`; детектор ловит сид-всплеск `+999% / z≈19 / high`.
