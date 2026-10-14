<p align="center">
  <img src="docs/images/readme-banner.svg" alt="idlink — поиск публичных профилей и объяснение связей" width="100%">
</p>

<p align="center">
  <a href="https://github.com/tzr7ybdfky-dotcom/idlink/actions/workflows/ci.yml"><img src="https://img.shields.io/badge/CI-GitHub_Actions-333333?logo=githubactions&amp;logoColor=white" alt="CI"></a>
  <img src="https://img.shields.io/badge/Python-3.11%2B-333333?logo=python&amp;logoColor=white" alt="Python 3.11+">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-333333" alt="License: MIT"></a>
</p>

<p align="center">
  Поиск публичных профилей по нику — в терминале.
</p>

<p align="center">
  <a href="#quick-start">Запуск из папки проекта</a> ·
  <a href="#installation">Установка</a> ·
  <a href="#usage">Команды</a> ·
  <a href="#filters">Фильтры</a> ·
  <a href="#documentation">Документация</a> ·
  <a href="https://github.com/tzr7ybdfky-dotcom/idlink/issues">Сообщить об ошибке</a>
</p>

<a id="installation"></a>

## Скачать и установить

Нужны **Python 3.11+** и **Git**. Если проект уже скачан, откройте терминал в его папке и пропустите первые две команды.

### macOS / Linux

```bash
git clone https://github.com/tzr7ybdfky-dotcom/idlink.git
cd idlink
python3 -m venv .venv
.venv/bin/python -m pip install .
```

### Windows · PowerShell

```powershell
git clone https://github.com/tzr7ybdfky-dotcom/idlink.git
cd idlink
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
```

<a id="quick-start"></a>

## Открыть терминал и запустить

- **macOS:** откройте «Терминал» через Spotlight (`⌘ + пробел`). Введите `cd `, перетащите папку проекта в окно и нажмите Enter.
- **Linux:** откройте папку проекта в файловом менеджере → правая кнопка мыши → «Открыть в терминале».
- **Windows:** откройте папку проекта в Проводнике, в адресной строке введите `powershell` и нажмите Enter.

Активируйте окружение в открытом терминале:

**macOS / Linux:**

```bash
source .venv/bin/activate
```

**Windows · PowerShell:**

```powershell
.\.venv\Scripts\Activate.ps1
```

Если PowerShell запрещает запуск скрипта, выполните `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` и повторите активацию. Настройка действует только в текущем окне.

Теперь запускайте поиск:

```bash
idlink search YOUR_USERNAME
```

Замените `YOUR_USERNAME` на ник без `@`. Для следующего поиска повторите команду с другим ником. В новом окне терминала снова активируйте окружение. Остановить поиск — **Ctrl+C**.

## Что умеет idlink

- **Поиск по каталогу из 6800+ источников:** соцсети, форумы, игры, разработка и другие категории.
- **Терминальный поиск:** `idlink search НИК` выводит найденные ссылки.
- **Понятный прогресс:** шкала 0–100%, итоговый список названий площадок и URL.
- **Объяснение связей:** оценка, сигналы и контрдоводы по клику на ребро.
- **Автономный HTML:** отчёт открывается без интернета; D3 и данные встроены в файл.

Ник проверяется на площадках; домен — как публичный сайт, почта или её хеш — через Gravatar.
Поиск по почте не проверяет регистрацию на всех соцсетях.

> Совпадение ника не доказывает, что профили принадлежат одному человеку.
> Оценки связей — эвристика. Недоступный сайт не означает отсутствие аккаунта.

<a id="usage"></a>

## Использование

**Найти страницы в терминале:**

```bash
idlink search YOUR_USERNAME
```

Во время проверки отображается шкала прогресса. После завершения остаётся список
`Platform: URL`, без повторов и ошибок отдельных сайтов. Предупреждение о ложных
совпадениях выводится перед поиском. При перенаправлении вывода шкала скрывается.

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
| `--timeout 12` | Сетевой таймаут; по умолчанию 6 с. Доступен в `search`. |
| `--depth 0` | Не переходить по опубликованным ссылкам на другие профили. Только `search`, по умолчанию 1. |
| `--respect-robots` | Проверять robots.txt; в `search` по умолчанию выключено. |
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
Несколько категорий объединяются. Фильтры доступны в `search` для ников.

```bash
idlink search YOUR_USERNAME --forums
idlink search YOUR_USERNAME --social --gaming
idlink search YOUR_USERNAME --dev --blogs
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

Каталог содержит **6893 записи**, из них **6859** автоматически выбираются для ника.
Наличие правила не гарантирует доступность сайта или правильность каждой проверки.
В выводе — прямые ссылки на страницы аккаунтов, без API-адресов.
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
Отдельные файлы `wmn_platforms.json` и `wmn_probe_rules.json` адаптированы из
[WhatsMyName](https://github.com/WebBreacher/WhatsMyName) и распространяются под
[CC BY-SA 4.0](idlink/data/WMN-LICENSE); авторы — Micah Hoffman и участники проекта.
Граф строится на [D3](https://d3js.org/) под [ISC](idlink/assets/D3-LICENSE).
Дерево источников вдохновлено [OSINT Framework](https://osintframework.com/).
