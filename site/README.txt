Stickio — сайт stickio.tumioai.ru
=================================

Что в этой папке
----------------

  index.html                     главная страница, русская
  privacy.html                   политика конфиденциальности
  en/index.html                  главная страница, английская
  en/privacy.html                политика конфиденциальности, английская
  404.html                       страница «не найдено»
  robots.txt                     указания поисковым роботам
  sitemap.xml                    список страниц для индексации
  favicon.ico                    значок сайта в корне (браузеры просят именно его)
  b3c2382811680ec6fe3687077f92b2f8.txt   ключ IndexNow — имя файла и есть ключ
  stickio.tumioai.ru.conf        конфигурация nginx
  assets/stickio.ico             значок приложения
  assets/og-stickio.png          картинка предпросмотра ссылки, 1200x630
  assets/screenshot-note.png     снимки настоящих окон программы, 880x620
  assets/screenshot-settings.png
  assets/screenshot-search.png
  assets/*.webp                  те же снимки в WebP — их отдают браузеру
                                 вместо PNG, они в 2-7 раз легче
                                 (снимок рабочего стола: 78 КБ -> 12 КБ).
                                 PNG остаются запасным вариантом, поэтому
                                 удалять их нельзя.

Две языковые версии лежат рядом: русская в корне, английская в en/. Каталог
называется en, а не ru и en, потому что адрес русской версии менять нельзя —
она уже проиндексирована. Перекрёстные ссылки прописаны с обеих сторон:
<link rel="alternate" hreflang="ru|en|x-default"> в <head> обеих главных и
переключатель «EN» / «RU» в шапке. Картинки в en/ подключены от корня
(/assets/...), а не относительно — иначе из /en/ они бы не нашлись.

Каталог downloads/ на сервере должен существовать отдельно — в него
кладётся установщик, в эту папку он не входит (33 МБ).


Состояние на 17 сентября 2026
-----------------------------

На сервере и проверено запросами снаружи:

  установщик     35 068 947 байт, sha256 c4067e9bedd5a8e733cfda8b195e0e74
                 ce2ab221f493a1a5ef2a7919cf773203
                 downloads/Stickio_Setup_1.1.0.exe — скачан снаружи
                 и совпал с dist/Stickio_Setup_1.1.0.exe побайтово;
  страницы       index.html, 404.html, privacy.html, sitemap.xml, en/index.html,
                 en/privacy.html — совпадают с локальными по sha256;
  assets/        все пять картинок и значок отдаются (200);
  битая ссылка   отдаёт 404 и фирменную страницу, а не заглушку nginx;
  сжатие         Content-Encoding: gzip на HTML;
  заголовки      nosniff, Referrer-Policy и X-Frame-Options есть на HTML,
                 на картинках и на установщике;
  редирект       http:// -> https:// отвечает 301;
  IndexNow       адреса отправлены 17.09.2026 повторно, ответ 200.

Установщик 1.0.1 с сервера удалён (кем — не я, время 14:49). Это ничего
не сломало: ни одна живая страница на него не ссылалась, а ссылка в релизе
v1.0.1 на GitHub ведёт на вложение самого релиза, а не на этот сайт.
Восстанавливать не нужно, но и 1.1.0 удалять не стоит по той же причине.

Исправленный конфиг nginx применён 17.09: на сервере лежала ПЕРВАЯ версия
файла — та, где add_header в location отменял наследование, и на HTML,
картинках и установщике заголовков безопасности не было вовсе. Проверено
после reload: заголовки появились везде. Копия прежнего файла на сервере —
stickio.tumioai.ru.conf.bak-20260917.

Осталось (делается руками в браузере, снаружи не проверяется):

  Яндекс.Вебмастер и Google Search Console — подтвердить права на сайт
  и отправить sitemap.xml. Коды подтверждения ждут в index.html: в <head>
  лежат закомментированные строки <meta name="yandex-verification"> и
  <meta name="google-site-verification">. Вставить код, снять комментарий
  и выложить index.html заново. Подтверждать можно и DNS-записью TXT —
  тогда правка страницы не нужна, но нужен доступ к DNS домена.

Про HTTP/2 ничего утверждать нельзя: у curl на машине сборки нет поддержки
h2, он в принципе не может договориться о втором протоколе. Конфиг ниже
HTTP/2 включает, но проверить это отсюда нечем.


Как пересобрать картинки
------------------------

Снимки окон и картинка предпросмотра — не рисунки, а рендер настоящих
окон программы. Если поменяется интерфейс, их надо пересобрать, иначе
на сайте останется старое окно:

  <python 3.11> tools\make_site_screenshots.py   # три снимка, PNG и WebP
  <python 3.11> tools\make_og_image.py           # картинка предпросмотра

Первый скрипт сам обновляет и .webp рядом с .png — отдельной команды
для этого не нужно.


Как выложить
------------

Одной командой из корня проекта (подставьте свой адрес сервера):

  rsync -av --delete \
    --exclude downloads \
    ./site/ \
    root@5.44.40.47:/var/www/stickio.tumioai.ru/

Без rsync — обычным scp:

  scp -r site/* root@5.44.40.47:/var/www/stickio.tumioai.ru/

Потом на сервере права на чтение:

  sudo chown -R www-data:www-data /var/www/stickio.tumioai.ru
  sudo find /var/www/stickio.tumioai.ru -type d -exec chmod 755 {} \;
  sudo find /var/www/stickio.tumioai.ru -type f -exec chmod 644 {} \;

Свежий установщик положить в downloads (файлы не перезаписывают друг
друга, в имени есть версия):

  scp dist/Stickio_Setup_1.1.0.exe \
      root@5.44.40.47:/var/www/stickio.tumioai.ru/downloads/


Конфигурация nginx
------------------

Уже применена 17.09.2026, повторять не нужно. Если будете менять файл заново:

  sudo cp /etc/nginx/sites-available/stickio.tumioai.ru{,.bak}
  sudo cp stickio.tumioai.ru.conf /etc/nginx/sites-available/stickio.tumioai.ru
  sudo nginx -t && sudo systemctl reload nginx

Если nginx -t ругается на ssl_certificate — значит сертификат лежит не там,
где указано в файле. Посмотрите свой прежний конфиг (он сохранён в .bak)
и подставьте те же пути.

Что даёт новый конфиг: сжатие gzip, кэш статики на 30 дней, HTTP/2,
своя страница 404, запрет встраивания сайта в чужой iframe.

Ловушка, на которой я один раз ошибся: в nginx add_header НЕ наследуется
в location, если у того есть свой add_header. В первой версии файла три
заголовка безопасности стояли только на уровне server, а у `location =
/index.html` был свой Cache-Control — он и отменил наследование. Снаружи
это выглядело так: на главной заголовков нет, а на установщике есть nosniff
(он там объявлен отдельно). Поэтому три строки продублированы в каждом
location, где что-то добавляется. Если будете править файл и добавите новый
add_header в какой-нибудь location — продублируйте их и там.

Проверить после reload:

  curl -sI https://stickio.tumioai.ru/ | grep -i "x-content-type\|referrer\|x-frame"


Яндекс.Вебмастер
----------------

1. Открыть https://webmaster.yandex.ru и добавить сайт stickio.tumioai.ru.
2. Подтвердить право: проще всего файлом — Вебмастер даст имя вида
   yandex_1a2b3c4d5e6f.html, положить его в корень сайта. Либо взять код
   из «Метатега» и вставить в index.html вместо строки
   <meta name="yandex-verification" ...> — она там уже есть, закомментирована.
3. «Индексирование» → «Файлы Sitemap» → добавить
   https://stickio.tumioai.ru/sitemap.xml
4. «Индексирование» → «Переобход страниц» → отправить главную.
5. Проверить, что robots.txt и sitemap.xml открываются в браузере.

Метрика (по желанию, но для Яндекса полезна):
6. https://metrika.yandex.ru → добавить счётчик → вставить код перед </head>
   в index.html. После этого в privacy.html ничего менять не нужно: там уже
   сказано, что статистика может использоваться.


Google Search Console
---------------------

1. Открыть https://search.google.com/search-console → «Добавить ресурс» →
   «Префикс URL» → https://stickio.tumioai.ru/
2. Подтвердить: HTML-файлом (положить в корень) или метатегом — строка
   <meta name="google-site-verification" ...> в index.html ждёт код.
3. «Файлы Sitemap» → добавить sitemap.xml
4. «Проверка URL» → вставить адрес главной → «Запросить индексирование».

Скорость: страница проверяется в https://pagespeed.web.dev — там же видно,
что мешает на телефонах.


Ускорить индексацию (IndexNow)
------------------------------

Ключ уже лежит в корне (b3c2382811680ec6fe3687077f92b2f8.txt). Адреса
главной и privacy.html **уже отправлены 17.09.2026, ответ 200** — повторять
сейчас не нужно. Команда ниже нужна при следующем обновлении сайта: Яндекс
и Bing узнают о правках сразу, не дожидаясь обхода.

  curl -X POST https://api.indexnow.org/indexnow \
    -H "Content-Type: application/json; charset=utf-8" \
    -d '{"host":"stickio.tumioai.ru",
         "key":"b3c2382811680ec6fe3687077f92b2f8",
         "keyLocation":"https://stickio.tumioai.ru/b3c2382811680ec6fe3687077f92b2f8.txt",
         "urlList":["https://stickio.tumioai.ru/",
                    "https://stickio.tumioai.ru/privacy.html"]}'

Ответ 200 или 202 — принято, тело ответа пустое, это нормально. Повторять
при каждом обновлении сайта. Google IndexNow не поддерживает — ему нужен
Search Console.


Проверка после выкладки
-----------------------

  curl -sI https://stickio.tumioai.ru/robots.txt        # 200
  curl -sI https://stickio.tumioai.ru/sitemap.xml       # 200
  curl -sI https://stickio.tumioai.ru/favicon.ico       # 200
  curl -sI https://stickio.tumioai.ru/privacy.html      # 200
  curl -sI https://stickio.tumioai.ru/en/               # 200
  curl -sI https://stickio.tumioai.ru/en/privacy.html   # 200
  curl -sI https://stickio.tumioai.ru/нет-такой         # 404 + страница сайта
  curl -sI https://stickio.tumioai.ru/assets/og-stickio.png  # 200
  curl -s  https://stickio.tumioai.ru/ | grep -c canonical   # 1
  curl -sI http://stickio.tumioai.ru/ | head -1         # 301 на https
  curl -s https://stickio.tumioai.ru/ | grep -o 'application/ld+json' # есть разметка

Заголовки безопасности (nosniff, Referrer-Policy, X-Frame-Options) должны
быть на всех четырёх типах ответа — иначе снова вернулась ошибка с
наследованием add_header:

  for u in / /index.html /privacy.html /en/ /assets/og-stickio.png \
           /downloads/Stickio_Setup_1.1.0.exe; do
    echo "--- $u"
    curl -sI "https://stickio.tumioai.ru$u" | grep -i "nosniff\|referrer\|x-frame"
  done

Установщик скачать снаружи и сверить сумму — иначе неизвестно, целый ли
файл доехал:

  curl -o setup.exe https://stickio.tumioai.ru/downloads/Stickio_Setup_1.1.0.exe
  sha256sum setup.exe   # c4067e9b…773203

Проверка разметки для поисковиков:
  https://validator.schema.org/#url=https%3A%2F%2Fstickio.tumioai.ru%2F
  https://webmaster.yandex.ru/tools/microtest/
  https://search.google.com/test/rich-results

Картинка предпросмотра ссылки: https://vk.com/dev/pages_preview или
отправить ссылку себе в Telegram — превью должно быть с картинкой 1200x630.


Что важно понимать про «топ-1»
------------------------------

Технически сайт после этой выкладки готов к индексации: роботы получат
robots.txt и sitemap, страница отдаётся по одному адресу, быстро грузится
и содержит разметку о программе. Но место в выдаче техника не покупает.

Что реально влияет дальше:
  * Возраст сайта и постоянство: новый домен Яндекс и Google держат
    «на карантине» несколько недель, пока не убедятся, что сайт живой.
  * Ссылки. Одна ссылка с крупного каталога (Softportal, Softpedia,
    «Софт для Windows», профиль на GitHub, пост на Habr) даёт больше,
    чем любые правки в метатегах.
  * Поведение: люди приходят, остаются, скачивают. Для Яндекса это
    считается в том числе по Метрике.
  * Свежесть: обновления программы с новыми версиями на странице.

Конкуренты по запросу «заметки на рабочем столе» — старые сайты с
десятками ссылок. Обогнать их за неделю нельзя, но по длинным запросам
(«заметки на рабочем столе windows 11 бесплатно», «программа стикеры
поверх окон», «чем заменить записки windows») шансы хорошие уже скоро.
