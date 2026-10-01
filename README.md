# Document Search Service

Сервис для поиска русскоязычных документов по тексту с использованием Elasticsearch. Полные данные документов хранятся в PostgreSQL.

## Стек

- Python 3.13
- FastAPI
- Pydantic v2
- PostgreSQL 17
- SQLAlchemy + asyncpg
- Elasticsearch 9
- Alembic
- Docker Compose
- pytest
- Ruff

## Запуск

Создайте `.env` из примера:

```sh
cp .env.example .env
```

Запустите сервис и загрузите тестовые данные:

```sh
make bootstrap
```

Swagger будет доступен по адресу:

```text
http://localhost:8000/docs
```

В PostgreSQL и Elasticsearch будет импортировано 1500 документов из `data/posts.csv`.

## API

### Поиск документов

```http
GET /api/v1/documents/search?q=новость
```

Сервис ищет документы по тексту и возвращает до 20 результатов со всеми полями из PostgreSQL, отсортированных по дате создания.

Пример:

```sh
curl 'http://localhost:8000/api/v1/documents/search?q=новость'
```

### Удаление документа

```http
DELETE /api/v1/documents/{id}
```

Документ удаляется из PostgreSQL и Elasticsearch.

Пример:

```sh
curl -X DELETE http://localhost:8000/api/v1/documents/42
```

## Health-check

```http
GET /health/live
```

Проверяет, что приложение запущено.

```http
GET /health/ready
```

Проверяет подключение к PostgreSQL и Elasticsearch.

## Тесты и проверка кода

```sh
make test
make lint
make docs-check
```

## Архитектура

PostgreSQL используется как основное хранилище данных.

Elasticsearch используется для полнотекстового поиска. Для русского текста применяется встроенный анализатор Elasticsearch.

Все обращения к PostgreSQL и Elasticsearch выполняются асинхронно.

## Структура данных

Документ содержит:

- `id` — уникальный идентификатор;
- `rubrics` — список рубрик;
- `text` — текст документа;
- `created_date` — дата создания.

В Elasticsearch хранятся данные, необходимые для поиска и сортировки результатов.

## Структура проекта

```text
app/          приложение FastAPI
alembic/      миграции PostgreSQL
tests/        тесты
data/         тестовый CSV-файл
compose.yaml  конфигурация Docker Compose
```

