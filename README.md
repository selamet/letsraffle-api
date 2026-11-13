# Santa's Draw - Secret Santa API

FastAPI-based RESTful API project for Secret Santa draw management.

## Features

- 🔐 User authentication and authorization
- 🎲 Draw creation and management
- 👥 Participant addition and removal
- 🎁 Automatic matching algorithm
- 📧 Email notifications
- 🔄 Versioned API (v1)

## Technologies

- **FastAPI** 0.120.0 - Modern web framework
- **Pydantic** 2.12.3 - Data validation
- **Python** 3.13
- **Uvicorn** - ASGI server
- **SQLAlchemy** 2.0.36 - ORM
- **PostgreSQL** - Database
- **Alembic** 1.14.0 - Database migrations

## Quick Start

```bash
# Clone the repository
git clone <repository-url>
cd santas_draw

# Copy environment file
cp .env.example .env

# Start all services
docker-compose up -d

# That's it! Application is running at http://localhost:8000
# API Docs: http://localhost:8000/docs
```

## Prerequisites

- Docker & Docker Compose

No Python, PostgreSQL, or other dependencies needed!

## Available Commands

```bash
# Start all services
docker-compose up -d

# Stop all services
docker-compose down

# View logs
docker-compose logs -f

# View application logs only
docker-compose logs -f app

# View database logs only
docker-compose logs -f postgres

# Rebuild and start
docker-compose up -d --build

# Stop and remove volumes
docker-compose down -v
```

## Configuration

The application uses environment variables loaded from `.env` file. Key settings:

- `APP_NAME` - Application name
- `APP_VERSION` - Application version
- `DEBUG` - Debug mode (True/False)
- `API_VERSION` - API version
- `HOST` - Server host
- `PORT` - Server port
- `CORS_ORIGINS` - CORS allowed origins
- `DATABASE_URL` - PostgreSQL connection string
- `DATABASE_ECHO` - Log SQL queries (True/False)
- `DATABASE_POOL_SIZE` - Connection pool size
- `DATABASE_MAX_OVERFLOW` - Max overflow connections

## E-mails

| When | Who | Template |
|---|---|---|
| Names are drawn | every participant | `email-template-{tr,en}.html` |
| Someone joins a draw | that participant | `join-confirmation.html` |
| An invite draw is created | the organizer | `draw-created.html` |
| 24 hours before a scheduled draw | the organizer | `draw-reminder.html` |
| Password reset requested | the user | `reset-password-template-{tr,en}.html` |

All of them are sent from Celery tasks, so a mail problem never fails the request that caused it.

## Announcement e-mails

Campaign e-mails (for example the 2027 launch announcement) are sent with a script, never automatically:

```bash
python -m scripts.send_announcement                      # dry run: recipient counts only
python -m scripts.send_announcement --to me@example.com  # one test e-mail
python -m scripts.send_announcement --apply              # send to every registered user
```

Every e-mail carries a personal unsubscribe link (`/api/v1/email/unsubscribe`) and one-click
`List-Unsubscribe` headers. Unsubscribed addresses are skipped, and sent addresses are recorded so the
script can be re-run safely. `API_URL` must be the public URL of the API in production.

## API Documentation

After running the application:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Project Structure

```
app/
├── main.py          # Main application
├── models/          # Database models
├── schemas/         # Pydantic schemas
├── api/
│   ├── deps.py      # Dependency injection
│   └── v1/          # API endpoints
├── config/          # Configuration
└── tasks/           # Background tasks
```

## License

AGPL v3 - See LICENSE file for details.
