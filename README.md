# MalikSite — Judge Platform (MVP)

Минимальный скелет платформы для выдачи и автопроверки задач (FastAPI + SQLModel + Celery + Judge0).

Как запустить локально:
1. Клонировать репозиторий
2. docker-compose up --build
3. Backend будет доступен на http://localhost:8000

Endpoints:
- POST /problems/{problem_id}/submissions — отправка решения

Примечание: проверьте конфигурацию Judge0 и список language_id.
