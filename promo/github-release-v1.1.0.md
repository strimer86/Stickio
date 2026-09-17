# Релиз v1.1.0 на GitHub — готовый текст

Файл для вставки в веб-интерфейс GitHub. Тег ставится локально (отправка по
SSH), релиз создаётся на сайте — через ssh его создать нельзя.

## 1. Тег

Ставим на коммит выпуска `801b654` — из его дерева собран установщик.
Коммиты после него меняли только страницы и тесты, exe они не касались.

```bash
git tag -a v1.1.0 801b654 -m "Версия 1.1.0"
git push origin v1.1.0
```

Проверка: `git ls-remote --tags origin` должен показать `v1.1.0`.

## 2. Что прикладывать к релизу

Файл: `dist\Stickio_Setup_1.1.0.exe`, 35 068 947 байт (33,4 МБ).

```
SHA-256  c4067e9bedd5a8e733cfda8b195e0e74ce2ab221f493a1a5ef2a7919cf773203
```

Сумма совпадает у локального файла, у файла на сервере и в `CHANGELOG.md` —
проверено 17.09.2026.

## 3. Заголовок релиза

```
Stickio 1.1.0
```

## 4. Текст по-русски

````markdown
Stickio — стикеры на рабочем столе Windows: заметки поверх всех окон,
без облака, без телеметрии и без единого сетевого запроса.

**Скачать:** `Stickio_Setup_1.1.0.exe` — 33,4 МБ

```
SHA-256  c4067e9bedd5a8e733cfda8b195e0e74ce2ab221f493a1a5ef2a7919cf773203
```

### Что нового

- **Английский язык интерфейса.** Переключается в настройках и применяется
  сразу, перезапуск не нужен. Язык запоминается, а при первом запуске
  подставляется язык системы, если он поддерживается.
- Выгрузка заметок в HTML стала на языке интерфейса: и заголовок страницы,
  и подписи под заметками.
- Строки перевода лежат словарём в `services/i18n.py`. Тесты сверяют словарь
  с исходниками в обе стороны и обходят английский интерфейс по живому дереву
  виджетов — непереведённая подпись не останется незамеченной.
- Сайт тоже стал двуязычным: английская версия на
  [stickio.tumioai.ru/en/](https://stickio.tumioai.ru/en/).

### Установка

Скачать `Stickio_Setup_1.1.0.exe` и запустить. Windows 10 и 11, 64-бит,
около 130 МБ на диске. Интернет не нужен, права администратора не обязательны.

Заметки хранятся локально, в `%LOCALAPPDATA%\Stickio\notes.db`, рядом с ними
лежат автокопии.

### Ссылки

- Сайт: https://stickio.tumioai.ru
- Исходники: https://github.com/strimer86/Stickio
- История изменений: [CHANGELOG.md](https://github.com/strimer86/Stickio/blob/main/CHANGELOG.md)
````

## 5. Текст по-английски

Пригодится, если релиз решим вести на английском — аудитория у репозитория
внешняя.

````markdown
Stickio — sticky notes for the Windows desktop: notes stay on top of every
window, no cloud, no telemetry, not a single network request.

**Download:** `Stickio_Setup_1.1.0.exe` — 33.4 MB

```
SHA-256  c4067e9bedd5a8e733cfda8b195e0e74ce2ab221f493a1a5ef2a7919cf773203
```

### What's new

- **English interface.** Switch languages in Settings — it applies
  immediately, no restart needed. The choice is remembered, and on first run
  the system language is used when it is supported.
- HTML export now follows the interface language: both the page title and the
  captions under the notes.
- Translations live in a plain dictionary in `services/i18n.py`. Tests check
  the dictionary against the source in both directions and walk the live
  widget tree of the English interface, so an untranslated label cannot slip
  through.
- The website is bilingual now as well: the English version is at
  [stickio.tumioai.ru/en/](https://stickio.tumioai.ru/en/).

### Install

Download `Stickio_Setup_1.1.0.exe` and run it. Windows 10 and 11, 64-bit,
about 130 MB on disk. No internet connection required, administrator rights
optional.

Notes are stored locally in `%LOCALAPPDATA%\Stickio\notes.db`, with automatic
backups kept alongside.

### Links

- Website: https://stickio.tumioai.ru
- Source: https://github.com/strimer86/Stickio
- Changelog: [CHANGELOG.md](https://github.com/strimer86/Stickio/blob/main/CHANGELOG.md)
````

## 6. После релиза

- Проверить, что установщик во вложении скачивается и сумма совпадает.
- Обновить ссылку в `CHANGELOG.md`, если адрес вложения релиза отличается от
  записанного (сейчас он уже указывает на
  `.../releases/download/v1.1.0/Stickio_Setup_1.1.0.exe`).
- Отправить адреса через IndexNow: страницы менялись.
