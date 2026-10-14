<p align="center">
  <img src="docs/images/readme-banner.svg" alt="idlink — поиск публичных профилей и объяснение связей" width="100%">
</p>

<p align="center">
  <a href="https://github.com/tzr7ybdfky-dotcom/idlink/actions/workflows/ci.yml"><img src="https://img.shields.io/badge/CI-GitHub_Actions-333333?logo=githubactions&amp;logoColor=white" alt="CI"></a>
  <img src="https://img.shields.io/badge/Python-3.11%2B-333333?logo=python&amp;logoColor=white" alt="Python 3.11+">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-333333" alt="License: MIT"></a>
</p>

<p align="center">
  Поиск публичных профилей по нику — в терминале и на интерактивном графе.
</p>

<p align="center">
  <a href="#quick-start">Запуск из папки проекта</a> ·
  <a href="#installation">Установка</a> ·
  <a href="#usage">Команды</a> ·
  <a href="#filters">Фильтры</a> ·
  <a href="#documentation">Документация</a> ·
  <a href="https://github.com/tzr7ybdfky-dotcom/idlink/issues">Сообщить об ошибке</a>
</p>

<a id="quick-start"></a>

## Запуск поиска в терминале

Откройте терминал в папке с `pyproject.toml`. Если проект уже скачан,
повторять `git clone` и `cd idlink` не нужно.

### macOS / Linux

Если окружение уже настроено, выполните:

```bash
.venv/bin/python -m idlink search YOUR_USERNAME
```

Замените `YOUR_USERNAME` на нужный ник, без символа `@`.
Прогресс и найденные ссылки появятся прямо в терминале. Дождитесь завершения;
чтобы прервать поиск, нажмите **Ctrl+C**. При следующем поиске повторите команду
с другим ником. Активация окружения и запуск сервера не требуются.

Используйте именно `.venv/bin/python`: отметка `(.venv)` в терминале сама по себе
не гарантирует, что команда `python` запускает окружение этого проекта.

**Только при первой установке**, если `.venv` ещё не настроена (нужен Python 3.11+):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

После установки выполните команду поиска выше.

### Windows · PowerShell

Поиск из папки проекта:

```powershell
.\.venv\Scripts\python.exe -m idlink search YOUR_USERNAME
```

Только при первой установке:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

### Выбор площадок и справка

Без фильтров поиск идёт по всем подходящим источникам каталога. Для проверки
только GitHub и Telegram или просмотра параметров на macOS/Linux:

```bash
.venv/bin/python -m idlink search YOUR_USERNAME --platforms github,telegram
.venv/bin/python -m idlink search --help
```

В PowerShell замените `.venv/bin/python` на `.\.venv\Scripts\python.exe`.

### Если не запускается

- `No such file or directory` для `.venv`: проверьте папку проекта и выполните первоначальную установку выше.
- `No module named typer` при запуске через `python`: повторите команду через `.venv/bin/python`. Если ошибка остаётся, установите зависимости командой `.venv/bin/python -m pip install -e .`.
- `No module named idlink` или ошибка другой отсутствующей зависимости: выполните `.venv/bin/python -m pip install -e .`.
- `Missing argument 'USERNAME'`: добавьте ник после `search`.
- `idlink: command not found`: используйте `.venv/bin/python -m idlink` из примеров выше.
- `Address already in use` при запуске `serve`: это ошибка веб-сервера. Для поиска в терминале используйте `search`; запускать `serve` не нужно.

Копируйте только команды из блоков, без приглашения терминала и сообщений об ошибках.

## Что умеет idlink

- **Поиск по каталогу из 2000+ источников:** соцсети, форумы, игры, разработка и другие категории.
- **Две команды:** `search` выводит найденные ссылки, `visual` открывает сайт с графом.
- **Понятный прогресс:** шкала 0–100%, итоговый список названий площадок и URL.
- **Объяснение связей:** оценка, сигналы и контрдоводы по клику на ребро.
- **Автономный HTML:** отчёт открывается без интернета; D3 и данные встроены в файл.

Ник проверяется на площадках; домен — как публичный сайт, почта или её хеш — через Gravatar.
Поиск по почте не проверяет регистрацию на всех соцсетях.

> Совпадение ника не доказывает, что профили принадлежат одному человеку.
> Оценки связей — эвристика. Недоступный сайт не означает отсутствие аккаунта.

<a id="installation"></a>

## Установка

Нужны **Python 3.11+** и **Git**. Замените `YOUR_USERNAME` на нужный ник.

### Linux / macOS

```bash
git clone https://github.com/tzr7ybdfky-dotcom/idlink.git
cd idlink
python3 -m venv .venv
.venv/bin/python -m pip install .
source .venv/bin/activate
idlink search YOUR_USERNAME
```

### Windows · PowerShell

```powershell
git clone https://github.com/tzr7ybdfky-dotcom/idlink.git
cd idlink
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\idlink.exe search YOUR_USERNAME
```

В PowerShell используйте `.\.venv\Scripts\idlink.exe` вместо `idlink` в примерах ниже.
Если репозиторий уже скачан, выполняйте установку из папки с `pyproject.toml`.

<a id="usage"></a>

## Использование

**Найти страницы в терминале:**

```bash
idlink search YOUR_USERNAME
```

Во время проверки отображается шкала прогресса. После завершения остаётся список
`Platform: URL`, без повторов и ошибок отдельных сайтов. Предупреждение о ложных
совпадениях выводится перед поиском. При перенаправлении вывода шкала скрывается.

**Открыть граф в браузере:**

```bash
idlink visual YOUR_USERNAME
```

Браузер открывается автоматически, порт выбирается свободный. Масштабируйте граф,
перетаскивайте узлы и нажимайте на связи для разбора. Остановка сервера — `Ctrl+C`.

<details>
<summary><strong>Посмотреть интерфейс</strong></summary>

Пример поиска публичного Telegram-канала `durov`, ограниченный одной площадкой:

```bash
idlink visual durov --platforms telegram
```

![Интерфейс idlink: поиск durov на Telegram](docs/images/web-search.png)

</details>

**Выбрать площадки, сохранить отчёт или получить справку:**

```bash
idlink search YOUR_USERNAME --platforms github,telegram
idlink search YOUR_USERNAME --out report.html
idlink explain EDGE_ID --report report.html
idlink help
idlink search --help
```

`search --out` сохраняет статусы проверок и связи в HTML, а также выводит подробности
в терминале. `EDGE_ID` — идентификатор связи из этого вывода.

### Скорость и регистр

```bash
idlink search YOUR_USERNAME --request-interval 0.5
idlink search YOUR_USERNAME --exact-case
idlink search YOUR_USERNAME --timeout 12
```

| Параметр | Поведение |
|---|---|
| `--request-interval 0.5` | Интервал запросов к одному hostname; по умолчанию 2 с, минимум 0,25 с. Только `search`. |
| `--exact-case` | Только введённое написание. Без флага `search` проверяет до четырёх вариантов регистра. |
| `--timeout 12` | Сетевой таймаут; по умолчанию 6 с. Доступен в `search` и `visual`. |
| `--depth 0` | Не переходить по опубликованным ссылкам на другие профили. Только `search`, по умолчанию 1. |
| `--respect-robots` | Проверять robots.txt; в `search`, `visual` и `serve` по умолчанию выключено. |
| `--purpose "Описание цели"` | Необязательная непустая цель поиска в `search`. |

Варианты регистра: введённый ник, строчный, ЗАГЛАВНЫЙ и С заглавной буквы.
На известных регистронезависимых площадках достаточно одного запроса.
После находки проверка площадки прекращается. Перебора всех комбинаций и исправления опечаток нет.

Выбирайте частоту, разрешённую площадкой. HTTP 403/429 останавливают запросы к домену;
более строгие серверные задержки имеют приоритет. Уменьшение интервала не гарантирует
ускорение всей проверки. Необязательный [Go-транспорт](docs/performance.md) ускоряет сетевую часть.

<a id="filters"></a>

## Фильтры площадок

Без фильтров проверяются все подходящие автоматические источники.
Несколько категорий объединяются. Фильтры доступны в `search` и `visual` для ников.

```bash
idlink search YOUR_USERNAME --forums
idlink search YOUR_USERNAME --social --gaming
idlink visual YOUR_USERNAME --dev --blogs
```

<details>
<summary><strong>Все 17 категорий</strong></summary>

| Флаг | Категория |
|---|---|
| `--forums` | Форумы |
| `--social` | Соцсети и мессенджеры |
| `--dev` | Разработка и технологии |
| `--gaming`, `--games` | Игры |
| `--music` | Музыка |
| `--video` | Видео и стримы |
| `--photo` | Фотография |
| `--art` | Искусство и дизайн |
| `--blogs` | Блоги и тексты |
| `--news` | Новости |
| `--science` | Наука |
| `--education` | Образование |
| `--business` | Работа и бизнес |
| `--shopping` | Магазины |
| `--sport` | Спорт |
| `--travel` | Путешествия |
| `--wikis` | Вики |

</details>

## Точность и данные

Каталог содержит **2161 источник**, из них **2154** автоматически выбираются для ника.
Наличие правила не гарантирует доступность сайта или правильность каждой проверки.
HTTP 200 сам по себе не считается найденным профилем; заглушки и неясные ответы
отделяются от находок. [Результаты аудита каталога →](docs/catalog-audit.md)

Оценка связи не калибрована на реальных вероятностях. Максимальная формулировка —
**«вероятно связаны»**; без сигнала ссылок действует ограничение 85%.
[Формула, веса и ограничения →](docs/scoring.md)

Используются публичные страницы и открытые API без входа в аккаунт. CAPTCHA не обходятся.
Исходные тексты профилей и изображения не записываются; в кэше остаются только URL,
pHash, токены, гистограмма активности и время запроса. Не используйте результаты
для преследования, обвинений или решений о доступе к работе и услугам.
[Правила доступа и хранения →](docs/privacy.md)

<a id="documentation"></a>

## Документация

| Раздел | Содержание |
|---|---|
| [Руководство](docs/usage.md) | Типы ввода, audit, отчёты, коды выхода и типичные ошибки |
| [Источники](docs/sources.md) | Адаптеры, критерии находок и происхождение каталога |
| [Скорость](docs/performance.md) | Go-транспорт, параллелизм, дедлайны и замеры |
| [Оценка связей](docs/scoring.md) | Формула, сигналы и ограничения точности |
| [Приватность](docs/privacy.md) | Сетевые ограничения и хранение данных |
| [Разработка](CONTRIBUTING.md) | Установка зависимостей, тесты и добавление площадок |

## Участие в проекте

Нашли ложное совпадение или сломанный адаптер? [Создайте issue](https://github.com/tzr7ybdfky-dotcom/idlink/issues)
с командой, версией и описанием ожидаемого результата. Перед публикацией удалите
из логов личные данные. Исправления и новые адаптеры принимаются через pull request;
порядок проверок описан в [CONTRIBUTING.md](CONTRIBUTING.md).

## Лицензия и благодарности

[MIT](LICENSE) · idlink contributors.

Каталог использует правила [Sherlock](https://github.com/sherlock-project/sherlock)
и [Maigret](https://github.com/soxoj/maigret) под MIT.
Граф строится на [D3](https://d3js.org/) под [ISC](idlink/assets/D3-LICENSE).
Дерево источников вдохновлено [OSINT Framework](https://osintframework.com/).
