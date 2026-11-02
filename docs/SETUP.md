# Окружение и запуск

## Установка

Бюджет задания предполагает уже установленный работающий Docker и основы Python/SQL. Ниже приведены инструкции для тех, кто готовит компьютер заранее. Само знакомство с Redis входит во время задания.

Установите [Git](https://git-scm.com/downloads) и редактор, в котором удобно менять Python и Markdown, например [VS Code](https://code.visualstudio.com/). Нужен аккаунт GitHub для собственной копии и сдачи. Устанавливать Python, Redis, PostgreSQL или pytest на компьютер отдельно не требуется.

Windows: установите [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) с Linux containers и WSL2, откройте PowerShell в каталоге проекта. macOS: установите [Docker Desktop](https://docs.docker.com/desktop/setup/install/mac-install/) либо используйте уже настроенную Colima с Docker и Compose. Linux: установите [Docker Engine](https://docs.docker.com/engine/install/) и [плагин Compose](https://docs.docker.com/compose/install/linux/) для своего дистрибутива, запустите daemon и настройте доступ своего пользователя к нему.

## Получение своей копии

1. Откройте [репозиторий задания](https://github.com/mperestoronin/concurrent-booking-lab), войдите в GitHub и нажмите Fork, затем Create fork. Владелец новой копии должен совпадать с вашим аккаунтом. Оставьте имя concurrent-booking-lab.
2. Откройте терминал в папке для учебных проектов. В следующем адресе замените YOUR_GITHUB_LOGIN своим логином. Если назвали Fork иначе, возьмите его HTTPS-адрес через кнопку Code на его странице.

```sh
git clone https://github.com/YOUR_GITHUB_LOGIN/concurrent-booking-lab.git
cd concurrent-booking-lab
git switch -c solution/booking
git remote -v
git rev-parse HEAD
```

3. В выводе remote адрес origin должен указывать на ваш Fork. Последняя команда выводит commit исходной заготовки; сохраните его в REPORT.md. Ветку solution/booking создайте один раз, затем продолжайте работу в ней.
4. Откройте эту папку в редакторе. Все команды Docker и тестов выполняйте в ней, где находится compose.yaml. Вводить их в консоли Python или внутри интерактивной SQL-консоли не нужно.

## Сборка и первый запуск

Выполните git --version, docker version и docker compose version. Docker должен показать сведения и о Client, и о Server. Старый docker-compose v1 не поддерживается. Если установлен новый Compose как отдельный исполняемый файл docker-compose, команды с ним эквивалентны, но в документации используется стандартный плагин docker compose.

```sh
docker compose up --build -d
docker compose ps
docker compose logs --tail=50 app
```

Флаг --build собирает образ из сохранённых файлов, -d оставляет контейнеры работать в фоне. В ps дождитесь healthy у app, postgres и redis. Затем откройте [документацию API](http://127.0.0.1:8080/docs). Для ручного запроса выберите маршрут, нажмите Try it out, заполните JSON и нажмите Execute. В ответе будут HTTP-код и тело. Для первого последовательного примера можно выполнить docker compose exec app python -m scripts.demo --resource 1.

Первая сборка скачивает образы и Python-зависимости из интернета. Сам сервис не обращается к внешним API; GitHub нужен для получения и сдачи кода. Закреплены Python 3.12.13, PostgreSQL 16.13, Redis 7.4.8 и версии Python-пакетов. Docker-теги фиксируют выпуск, но могут получать пересборки базового образа; строгая побайтовая воспроизводимость потребовала бы digest и зеркала пакетов.

## Запросы на Windows

В PowerShell удобно работать с объектами, чтобы не экранировать JSON вручную:

```powershell
$base = 'http://127.0.0.1:8080'
Invoke-RestMethod "$base/resources"
$body = @{resourceId=1; clientId='alice'; ttlSeconds=60} | ConvertTo-Json
$hold = Invoke-RestMethod "$base/holds" -Method Post -ContentType 'application/json' -Body $body
$body = @{resourceId=1; clientId='alice'; holdId=$hold.holdId} | ConvertTo-Json
Invoke-RestMethod "$base/bookings" -Method Post -ContentType 'application/json' -Body $body
```

На всех системах доступен пример без ручной подстановки UUID: docker compose exec app python -m scripts.demo. Он использует ресурс 1, который должен быть свободен.

## Изменения и данные

Исходники копируются в образ; привязки рабочего каталога и autoreload нет. После правки кода или миграции выполните docker compose up --build -d. Для тестового образа в командах уже есть run --build. Обычный restart app перезапускает прежний образ и проверяет сохранность SQL-данных.

docker compose down останавливает стенд и сохраняет PostgreSQL в named volume. Redis хранит временные ключи без persistence, после пересоздания его контейнера они исчезнут. Брони остаются в PostgreSQL.

Для повторного примера:

```sh
docker compose exec app python -m scripts.reset_demo --confirm-local-reset
```

Команда удаляет все демонстрационные брони этого стенда и ключи booking-lab:hold:* в его Redis. Она не снимает ограничения и не удаляет миграции. Не направляйте переменные окружения на рабочую БД. Глобальные FLUSHALL/FLUSHDB не нужны. Полный сброс схемы вместе с данными: docker compose down -v, затем обычный запуск. Этот вариант удаляет учебный volume без восстановления; используйте его только если данные больше не нужны.

Если миграция UNIQUE не даёт приложению запуститься из-за уже накопленных дубликатов, exec в перезапускающийся контейнер ненадёжен. После изучения дубликатов, если учебные брони можно удалить, выполните сброс отдельным процессом без запуска API:

```sh
docker compose up -d postgres redis
docker compose run --rm --no-deps app python -m scripts.reset_demo --confirm-local-reset
docker compose up --build -d
```

Перед сбросом дождитесь healthy у PostgreSQL и Redis. Исходники и миграции остаются на месте, удаляются демонстрационные брони и удержания.

## Диагностика

| Симптом | Действие |
|---|---|
| Cannot connect to Docker daemon | Запустите Docker Desktop или свою Colima; проверьте docker context ls |
| docker: unknown command: compose | Установите плагин Compose; для существующей установки нового standalone используйте docker-compose |
| Порт 8080 занят | Скопируйте .env.example в .env, задайте API_PORT=18080, повторите запуск; URL изменится |
| app ещё не healthy | Подождите до 90 секунд, посмотрите docker compose logs app postgres redis |
| Пароль PostgreSQL не подходит после правки .env | Старый volume хранит прежнего пользователя; верните настройки либо сознательно сбросьте volume |
| SQL-миграция не добавляет UNIQUE | Посмотрите дубликаты в bookings; сбросьте только учебные брони, повторите запуск |
| После исправления тест ведёт себя по-старому | Нужны пересборка приложения и run --build для tests |
| base падает в исходной версии | Это ожидаемо для B02/B03/B04/B06/B07/B08; сначала проверьте smoke |
| Permission denied при записи reports | Проверьте доступ Docker к рабочему каталогу и отсутствие режима read-only у диска |

Основной API работает под UID 10001. Одноразовый контейнер tests запускается с UID 0, чтобы записать отчёт в bind-mounted reports и на Linux. На Linux созданные отчёты могут принадлежать root; при необходимости задайте run --user UID:GID со своими числовыми значениями.

Для SQL-консоли: docker compose exec postgres psql -U booking -d booking. При переопределении .env используйте свои значения. Для Redis: docker compose exec redis redis-cli, затем GET booking-lab:hold:1 или PTTL booking-lab:hold:1. Значение PTTL измеряется в миллисекундах.
