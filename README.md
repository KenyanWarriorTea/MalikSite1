# Code Wave - Judge0 Образовательная Платформа

Веб-приложение для дистанционного обучения программированию с автоматической проверкой кода через Judge0 API.

## 🎯 Возможности

### Для учителей
- ✅ Публикация заданий на программирование (поддержка Python, Java, C++)
- ✅ Указание ожидаемого результата для автоматической проверки
- ✅ Просмотр всех решений студентов
- ✅ Автоматическая оценка кода через Judge0
- ✅ Мониторинг активности студентов (смена вкладок, потеря фокуса)
- ✅ Просмотр подозрительной активности для борьбы с списыванием

### Для студентов
- ✅ Просмотр доступных заданий
- ✅ Отправка решений на автоматическую проверку
- ✅ Мгновенный результат проверки (Accepted/Wrong Answer/Runtime Error)
- ✅ Безопасное подключение через код доступа (без регистрации)
- ✅ Работа в локальной сети школы

## 🏗️ Архитектура

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────┐
│  Студенты       │────▶│  FastAPI Web     │────▶│  PostgreSQL │
│  (браузер)      │     │  приложение      │     │  База данных│
└─────────────────┘     └──────────────────┘     └─────────────┘
                               │
                               │
                        ┌──────▼──────┐
                        │   Judge0    │
                        │ Оценка кода │
                        └─────────────┘
```

## 📋 Требования

- Docker Desktop (https://www.docker.com/products/docker-desktop)
- Браузер с поддержкой JavaScript
- Локальная сеть для подключения студентов

## 🚀 Быстрый старт

### 1. Клонируйте репозиторий
```bash
git clone https://github.com/KenyanWarriorTea/MalikSite1.git
cd MalikSite1
```

### 2. Запустите приложение
```bash
docker-compose up --build
```

Приложение будет доступно по адресу: **http://localhost:8000**

### 3. Тестовые коды доступа
- **Учитель**: `teacher123`
- **Ученик**: `student123`

### 4. Подключение студентов из локальной сети

Замените `localhost` на IP адрес учительского компьютера:
```
http://192.168.1.100:8000
```

Подробнее см. [NETWORK_SETUP.md](./NETWORK_SETUP.md)

## 🔐 Безопасность

- Коды доступа хранятся в переменных окружения
- Сессии защищены токеном
- Мониторинг активности студентов для предотвращения списывания
- Все данные хранятся в защищенной базе данных

**Важно**: Измените коды доступа перед использованием в production!

## 📊 Стек технологий

| Компонент | Технология |
|-----------|-----------|
| Backend | FastAPI (Python 3.12) |
| Database | PostgreSQL |
| Code Evaluation | Judge0 |
| Frontend | HTML/CSS/JavaScript |
| Containerization | Docker & Docker Compose |
| ORM | SQLAlchemy |

## 📁 Структура проекта

```
MalikSite1/
├── backend/
│   ├── app.py              # Основное приложение
│   ├── models.py           # Database models (SQLAlchemy)
│   ├── database.py         # Database configuration
│   ├── judge0_client.py    # Judge0 API integration
│   ├── requirements.txt    # Python зависимости
│   ├── Dockerfile          # Container configuration
│   └── tests/
│       └── test_app.py     # Модульные тесты
├── docker-compose.yml      # Multi-container setup
├── .env.example           # Environment variables template
├── README.md              # This file
├── NETWORK_SETUP.md       # Local network configuration
└── LICENSE
```

## 🧪 Тестирование

```bash
cd backend
pip install -r requirements.txt
python -m pytest tests/test_app.py -v
```

Все 8 тестов должны пройти успешно.

## 📱 Использование

### Учитель

1. Откройте http://localhost:8000
2. Введите имя и код учителя (`teacher123`)
3. Добавьте задание:
   - Название
   - Описание
   - Ожидаемый результат
   - Язык программирования
4. Смотрите решения студентов с указанием статуса проверки

### Ученик

1. Откройте http://[IP_учителя]:8000
2. Введите имя и код ученика (`student123`)
3. Выберите задание и напишите код
4. Нажмите "Отправить решение"
5. Получите результат проверки за несекунды

## 🎓 Мониторинг активности студентов

Система отслеживает:
- ❌ Смену вкладок браузера
- ❌ Потерю фокуса окна
- 📊 Время фокусировки на задании

Учитель может видеть подозрительную активность в панели управления.

## 🐛 Отладка

### Просмотр логов

```bash
# Все сервисы
docker-compose logs -f

# Только веб-приложение
docker-compose logs -f web

# Только Judge0
docker-compose logs -f judge0
```

### Проверка статуса контейнеров

```bash
docker-compose ps
```

### Остановка приложения

```bash
docker-compose down
```

## 🔌 API endpoints

| Method | Endpoint | Описание |
|--------|----------|---------|
| GET | `/` | Login page |
| POST | `/login` | User authentication |
| GET | `/teacher` | Teacher dashboard |
| GET | `/student` | Student dashboard |
| POST | `/teacher/assignments` | Create assignment |
| POST | `/student/submissions` | Submit solution |
| POST | `/api/activity` | Log student activity |

## 📝 Переменные окружения

Скопируйте `.env.example` в `.env` и настройте:

```bash
cp .env.example .env
```

Подробнее см. [.env.example](./.env.example)

## 🤝 Вклад

Проект создан в рамках дипломной работы. Для вопросов и предложений открывайте Issues.

## 📄 Лицензия

MIT License - см. [LICENSE](./LICENSE)

## 📚 Дополнительные ресурсы

- [Docker документация](https://docs.docker.com/)
- [FastAPI официальный сайт](https://fastapi.tiangles.io/)
- [Judge0 документация](https://judge0.com/)
- [SQLAlchemy docs](https://docs.sqlalchemy.org/)
- [Local Network Setup Guide](./NETWORK_SETUP.md)

---

**Статус проекта**: ✅ Функциональный

**Версия**: 1.0.0 (Diploma Edition)
