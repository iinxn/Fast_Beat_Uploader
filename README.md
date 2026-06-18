# Fast Beats Render

Десктоп-приложение (Windows) для создания видео из **одной картинки + аудиофайла**
с последующей загрузкой на **YouTube** по расписанию.

Видео собирается через `ffmpeg`: статичная картинка растягивается на кадр, поверх
накладывается звук. Можно сразу сгенерировать **горизонтальную и вертикальную**
версии и загрузить каждую на YouTube как отложенную публикацию.

---

## Возможности

- Рендер видео из картинки и аудио (MP4, кодек H.264 + AAC).
- Горизонтальный и вертикальный варианты — по отдельности или **оба сразу**.
  - Вертикаль: картинка обрезается по кадру (без чёрных полос).
  - Горизонталь: картинка вписывается в кадр.
- **Drag & Drop**: перетащи файлы в окно — приложение само определит, где картинка,
  а где аудио (по расширению).
- **Прогресс-бар** рендера и кнопка **отмены** (с удалением недописанного файла).
- Пресеты разрешения (480p…4K), настройка FPS, CRF, скорости сжатия, битрейта/частоты аудио.
- Загрузка на YouTube с расписанием публикации, тегами, языком и категорией.
- **Шаблоны загрузки** (пресеты) для быстрого заполнения полей.
- **Умная маршрутизация загрузки**: при блокировках/DPID автоматически пробует
  несколько хостов и режимов прокси, понятные сообщения об ошибках сети, автоповторы
  при обрывах.
- **Запоминание папки по умолчанию** между запусками (`settings.json`).
- Токен YouTube хранится отдельно от проекта и шифруется через Windows DPAPI.

---

## Структура проекта

Плоская структура: точка входа `app.py` в корне, код разложен по папкам
`ui` / `services` / `utils`.

```
fastbeatuplouder/             ← корень проекта
├── app.py                    ← точка входа: главное окно и main()
├── ui/
│   └── dialogs.py            ← окна: дата, пресеты, загрузка на YouTube
├── services/
│   ├── ffmpeg.py             ← команда ffmpeg, длительность аудио, разбор прогресса
│   ├── youtube.py            ← авторизация, загрузка, маршруты, токен
│   ├── presets.py            ← UploadPreset, PresetStore → presets.json
│   └── settings.py           ← SettingsStore → settings.json
├── utils/
│   ├── consts.py             ← статические значения (без путей и I/O)
│   └── paths.py              ← пути и общие хелперы (см. ниже)
├── assets/                   ← icon.ico (необязательно)
├── ffmpeg/                   ← ffmpeg.exe, ffprobe.exe (вшиваются в exe)
├── FastBeatsRender.spec      ← конфиг сборки PyInstaller
├── build.ps1                 ← сборка одной командой
├── requirements.txt
└── README.md
```

| Модуль | За что отвечает |
|--------|-----------------|
| `app.py` | Главное окно и логика: форма ввода, запуск рендера, прогресс-бар, отмена, drag & drop, точка входа `main()`. |
| `ui/dialogs.py` | Модальные окна: выбор даты/времени (`DateTimePickerDialog`), управление пресетами (`PresetManagerDialog`), окно загрузки (`YouTubeUploadDialog`). |
| `services/youtube.py` | Работа с YouTube: токен (`TokenStorage`), авторизация и загрузка (`YoutubeService`), перебор маршрутов, понятные ошибки сети. |
| `services/ffmpeg.py` | Сборка команды рендера, длительность аудио, разбор прогресса, поиск `ffmpeg`/`ffprobe`. |
| `services/presets.py` | Модель и хранилище пресетов загрузки (`UploadPreset`, `PresetStore`) → `presets.json`. |
| `services/settings.py` | Настройки приложения (`SettingsStore`) → `settings.json` (например, папка по умолчанию). |
| `utils/consts.py` | Статические значения: заголовки, пресеты разрешений, опции аудио/видео, языки/категории, расширения файлов. |
| `utils/paths.py` | Общие хелперы и расположение файлов: `app_base_dir`, `resource_path`, `safe_filename` и пути (`BASE_DIR`, `PRESETS_FILE`, `TOKEN_FILE`, …). |

### Как устроены ключевые блоки

- **Общие хелперы** вынесены в `utils/paths.py` — там собрано всё про «где лежат
  файлы» (`app_base_dir`, `resource_path`) и санитайзер имён (`safe_filename`), что
  раньше было размазано по разным модулям.
- **Рендер** (`app.py` → `_start_render` → `worker`): валидирует поля, через
  `_get_render_jobs` формирует список задач (1 или 2 файла), запускает `ffmpeg` в
  отдельном потоке, парсит вывод (`services/ffmpeg.py: parse_ffmpeg_progress` /
  `parse_ffmpeg_duration`) и двигает прогресс-бар. Отмена завершает процесс и удаляет
  недописанный файл.
- **Команда ffmpeg** (`services/ffmpeg.py: build_ffmpeg_command`): два режима фильтра —
  `scale+crop` (вертикаль, заполнение) и `scale+pad` (горизонталь).
- **Загрузка** (`services/youtube.py: YoutubeService.upload_video`): возобновляемая
  загрузка чанками с автоповторами; перебирает маршруты `UPLOAD_STRATEGIES`, пока один
  не сработает; ошибки переводятся в понятный текст (`friendly_upload_error`).
- **Токен** (`services/youtube.py: TokenStorage`): на Windows шифруется DPAPI, лежит в
  `%USERPROFILE%\.fast_beats_render\`. Кнопка «Сбросить вход» удаляет токен.

---

## Запуск из исходников (разработка)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Рядом с проектом нужны:
- папка `ffmpeg` с `ffmpeg.exe` и `ffprobe.exe`;
- `client_secret.json` (см. ниже) — только для загрузки на YouTube.

---

## Сборка в один .exe

Приложение собирается в **один самодостаточный файл** `FastBeatsRender.exe`. Внутрь
него упакованы Python, все библиотеки и `ffmpeg`/`ffprobe` — отдельно ставить ничего
не нужно.

### Требования к сборке
- Установленный Python и виртуальное окружение `.venv` с зависимостями.
- В `.venv` должен быть `pyinstaller`:
  ```powershell
  .\.venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller
  ```
- Папка `ffmpeg` с `ffmpeg.exe` и `ffprobe.exe` рядом с проектом (они вшиваются в exe).

### Способ 1 — одной командой (рекомендуется)
```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

### Способ 2 — вручную
```powershell
.\.venv\Scripts\pyinstaller.exe FastBeatsRender.spec --noconfirm --clean
```

Готовый файл появится в `dist\FastBeatsRender.exe` (≈ 105 МБ — внутри лежит ffmpeg).

> Если пересборка падает с `Access is denied: dist\FastBeatsRender.exe` — значит
> приложение запущено. Закрой все окна `FastBeatsRender` и собери заново.

### Добавление иконки

1. Подготовь файл иконки в формате **`.ico`** и назови его **`icon.ico`**.
2. Положи `icon.ico` в папку **`assets/`** (`assets/icon.ico`).
3. Пересобери (`build.ps1` или команда выше).

Спека сама подхватит `assets/icon.ico`, если он есть (строка `_icon` в
`FastBeatsRender.spec`); если файла нет — используется стандартная иконка. Менять
сам `.spec` не нужно.

**Где взять `.ico`:** хороший `.ico` содержит несколько размеров (16, 32, 48, 256 px).
Если есть только PNG — сконвертируй. Например, через Pillow:

```powershell
.\.venv\Scripts\python.exe -m pip install pillow
.\.venv\Scripts\python.exe -c "from PIL import Image; Image.open('icon.png').save('assets/icon.ico', sizes=[(16,16),(32,32),(48,48),(256,256)])"
```

Либо любым онлайн-конвертером PNG → ICO.

> Иконка в проводнике может обновиться не сразу из-за кэша значков Windows. Если
> старая иконка «залипла» — переименуй exe или перезапусти проводник.

---

## Что класть рядом с .exe

Внутрь exe **нельзя** зашивать личные ключи Google, поэтому один файл должен лежать
в той же папке, что и `.exe`:

| Файл | Обязателен? | Зачем |
|------|-------------|-------|
| `client_secret.json` | только для загрузки на YouTube | OAuth-ключ из Google Cloud Console (тип «Desktop app»). Без него рендер работает, а загрузка — нет. |

Создаются приложением автоматически (трогать не обязательно):
- `presets.json` — шаблоны загрузки (рядом с .exe);
- `settings.json` — настройки, например папка по умолчанию (рядом с .exe);
- `%USERPROFILE%\.fast_beats_render\youtube_token.dat` — зашифрованный токен входа.

> Если хочешь, чтобы `client_secret.json` тоже был внутри exe, можно добавить его в
> `datas` в `FastBeatsRender.spec`. Приложение сначала ищет файл рядом с .exe, и
> только потом — внутри сборки.

---

## Как получить client_secret.json

1. [Google Cloud Console](https://console.cloud.google.com/) → создай проект.
2. Включи **YouTube Data API v3**.
3. **Credentials → Create credentials → OAuth client ID → Desktop app**.
4. Скачай JSON, переименуй в `client_secret.json`, положи рядом с `.exe`.

---

## Возможные проблемы

- **«client_secret.json не найден»** — положи файл рядом с `.exe`.
- **«Не удаётся найти серверы YouTube» / «нет интернета»** — проверь подключение.
- **Обрыв во время загрузки** — приложение само повторит передачу до 5 раз.
- **«YouTube отклонил запрос (403)»** — проверь, что включён YouTube Data API v3 и
  не исчерпана дневная квота.
- **Доступ Google отозван / истёк** — нажми «Сбросить вход» в окне загрузки и
  авторизуйся заново.

### `[WinError 10054] ... forcibly closed` при загрузке

Это разрыв TCP-соединения извне (провайдер/DPI, VPN или фаервол), а не ошибка
приложения. У многих провайдеров `youtube.googleapis.com` режется по DPI, а старый
хост `www.googleapis.com` остаётся доступным напрямую.

Поэтому загрузка **сама перебирает маршруты** (`UPLOAD_STRATEGIES` в
[youtube.py](youtube.py)):
1. `www.googleapis.com` напрямую (минуя системный прокси);
2. `www.googleapis.com` через системный прокси/VPN;
3. `youtube.googleapis.com` через прокси/VPN.

Если всё равно не грузит:
- **Не держи несколько VPN-клиентов одновременно** (например v2rayN/xray + nekobox) —
  они конфликтуют и повреждают TLS-поток (`DECRYPTION_FAILED_OR_BAD_RECORD_MAC`,
  тот же `10054`). Оставь один или выключи VPN.
- Часто YouTube грузится **лучше вообще без VPN** — приложение пробует прямой
  маршрут первым.
- Если используешь VPN — **смени сервер (ноду)** и **отключи Mux** в клиенте.
