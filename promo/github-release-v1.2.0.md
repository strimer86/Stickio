# Релиз v1.2.0 на GitHub — готовый текст

Файл для вставки в веб-интерфейс GitHub. Тег ставится локально (отправка по
SSH), релиз создаётся на сайте — через ssh его создать нельзя.

## 1. Тег

Ставим на коммит выпуска `9c6b82b` — из его дерева собран установщик.

```bash
git tag -a v1.2.0 9c6b82b -m "Версия 1.2.0"
git push origin v1.2.0
```

Проверка: `git ls-remote --tags origin` должен показать `v1.2.0`.

## 2. Что прикладывать к релизу

Файл: `dist\Stickio_Setup_1.2.0.exe`, 35 066 129 байт (33,4 МБ).

```
SHA-256  a2d8c47fae7a4a5a449c467696f01eebe4f2c994438b17e1ae5c9a026191a032
```

Сумма совпадает с записанной в `CHANGELOG.md`.

## 3. Заголовок релиза

```
Stickio 1.2.0
```

## 4. Текст по-русски

````markdown
Stickio — стикеры на рабочем столе Windows: заметки поверх всех окон,
без облака, без телеметрии и без единого сетевого запроса.

**Скачать:** `Stickio_Setup_1.2.0.exe` — 33,4 МБ

```
SHA-256  a2d8c47fae7a4a5a449c467696f01eebe4f2c994438b17e1ae5c9a026191a032
```

### Что нового

- **Закрепление заметки поверх всех окон.** Кнопка-булавка в панели
  оформления — она открывается по «···» в правом верхнем углу заметки.
  Закреплённая заметка не перекрывается другими окнами и при этом не
  отбирает фокус у активной программы: клик по самой заметке временно
  отдаёт ей фокус, чтобы можно было печатать, а при уходе фокуса он
  возвращается прежнему окну.
- Закрепление запоминается для каждой заметки отдельно и переносится
  вместе с ней при экспорте и импорте.

### Установка

Скачать `Stickio_Setup_1.2.0.exe` и запустить. Windows 10 и 11, 64-бит,
около 120 МБ на диске. Интернет не нужен, права администратора не обязательны.
Обновление ставится поверх предыдущей версии, заметки сохраняются.

Заметки хранятся локально, в `%LOCALAPPDATA%\Stickio\notes.db`, рядом с ними
лежат автокопии.

### Ссылки

- Сайт: https://stickio.tumioai.ru
- Исходники: https://github.com/strimer86/Stickio
- История изменений: [CHANGELOG.md](https://github.com/strimer86/Stickio/blob/main/CHANGELOG.md)
````

## 5. Текст по-английски

````markdown
Stickio — sticky notes for the Windows desktop: notes stay on top of every
window, no cloud, no telemetry, not a single network request.

**Download:** `Stickio_Setup_1.2.0.exe` — 33.4 MB

```
SHA-256  a2d8c47fae7a4a5a449c467696f01eebe4f2c994438b17e1ae5c9a026191a032
```

### What's new

- **Pin a note on top of all windows.** The pin button lives in the
  formatting panel, which opens from «···» in the note's top-right corner.
  A pinned note is never covered by other windows, yet it does not steal
  focus from the app you are working in: clicking the note itself gives it
  focus only while you type, and focus returns to the previous window as
  soon as you click away.
- Pinning is remembered per note and travels with it through export and
  import.

### Install

Download `Stickio_Setup_1.2.0.exe` and run it. Windows 10 and 11, 64-bit,
about 120 MB on disk. No internet connection required, administrator rights
optional. Installing over a previous version keeps your notes.

Notes are stored locally in `%LOCALAPPDATA%\Stickio\notes.db`, with automatic
backups kept alongside.

### Links

- Website: https://stickio.tumioai.ru
- Source: https://github.com/strimer86/Stickio
- Changelog: [CHANGELOG.md](https://github.com/strimer86/Stickio/blob/main/CHANGELOG.md)
````

## 6. После релиза

- Проверить, что установщик во вложении скачивается и сумма совпадает.
- Обновить адрес и размер установщика в `README.md` (две строки — русская
  и английская): сейчас там ссылка на 1.1.0.
- Обновить размер и sha256 в `site/README.txt` и выложить установщик в
  `downloads/` на сервере.
- Обновить версию и sha256 в промо-материалах (`promo/`).
- Отправить адреса через IndexNow: страницы менялись.
