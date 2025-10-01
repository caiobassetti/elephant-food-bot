# Elephants Food Bot — Django + DRF

A Dockerized Django service that simulates 100 “A asks → B answers top-3 foods” chats, stores results in SQL, and exposes an **authenticated** API that lists vegetarian/vegan users with their top-3 foods.

> Stack: <br>
> - Django, <br>
> - DRF, <br>
> - Postgres (local via Docker), <br>
> - structured logs, <br>
> - tests + CI <br>


## Architecture

```mermaid
flowchart LR
    Dev[You / CI] -->|docker compose up| Web[Web (Django+DRF)]
    Web -->|ORM| DB[Dev(Postgres) / Prod (SQLite)]
    Cmd[app/manage.py simulate_foods] --> Web
    Web -->|/api/veg-users/ | Client[curl / browser]
    Auth
      Client -->|Basic| Web
      Client -->|Token| Web
    end
```


## Quickstart

Pre-requirements:
- Docker
- Docker Compose
- OpenAI API key

### 1. Environment
```
cp .env.example .env
```

### 2. Start services
`make up`

### 3. Apply migrations
`make migrate`

### 4. Create a superuser (for admin & quick Auth tests)
`make superuser`

### 5. Load simulation data
`make simulation`

- The command stores:
    - **Conversation A**: the prompt used (base + seed).
    - **Conversation B**: the returned list of 3 foods (as text), and token/cost.

### 6. Hit the API (Basic Auth)
`curl -s -i -u <username>:<password> GET http://localhost:8000/api/veg-users/`

### 7. Optionally, you can hit the API using Token Auth
`make token U=<username>`
`curl -s -i -H "Authorization: Token <TOKEN>" http://localhost:8000/api/veg-users/`

## API

**Authentication**
- **Basic Auth**: username/password you created with `createsuperuser` (or any staff/user).
- **Token Auth**: supply `Authorization: Token <your-token>` header.
    - Obtain a token via `make token U=<username>`.


**Endpoints**
GET `/api/veg-users/`
  - Returns users classified as **vegetarian** or **vegan**, with top-3 foods.
  - **Response (example)**
    ```json
    [
      {
        "user_id":"33beafb1-5d2c-40ff-8062-2073851bc8de",
        "run_id":"728d9378-29bd-46c1-9b1c-5fc9be6caa93",
        "diet":"vegan",
        "top3":["caprese salad","avocado toast","banana"]
      }
    ]
    ```

## Local services

- **App**: http://localhost:8000
- **Admin**: http://localhost:8000/admin/
- **Postgres**: localhost:5432 (inside Docker network at `db:5432`)
    - DB name: efb
    - DB user:efb_user
    - DB password: efb_pass

## Repo layout
.
├─ app/                        # Django app
│  ├─ common/                  # Helpers package common to all domains
│  ├─ config/                  # Django project settings split (base/dev/prod)
│  ├─ foods/
│  │  ├─ management/commands/simulate_foods.py
│  │  ├─ catalog.py
│  │  ├─ openai_client.py
│  │  └─ … models.py, serializers.py, views.py, urls.py
├─ docker/                     # Build for the web service
│  ├─ entrypoint.sh
│  └─ web.Dockerfile
├─ tests/                      # pytest suite for API, simulation, utils
├─ .env.example                # Sample env vars
├─ compose.yaml                # Local runtime (db + web)
├─ Makefile                    # One-liners for common tasks
├─ pyproject.toml              # Ruff config
├─ pytest.ini                  # Pytest config
├─ README.md
├─ requirements-dev.txt        # Dependencies for local dev
└─ requirements.txt            # Dependencies for prod


### Secrets

- Some credentials may be hardcoded in `compose.yaml` to maximize legibility for reviewers (`efb_user/efb_pass`).
    - For production they would be moved to `.env` and reference via `${VAR}` in compose.
- OpenAI keys: keept in `.env` or CI secrets.


### Logging

- Logs are JSON via structlog:
`make logs`


### Tests & CI

- Run tests locally:
`Make test`

- CI: GitHub Actions workflow (.github/workflows/ci.yml) runs ruff + pytest on every push/PR.
- To cap LLM calls in tests/CI, set `EFB_LLM_CALL_BUDGET` (`0` or `1`). Exceeding it will raise an error.


### Teardown

- Stop/remove container (erasing volumes):
`Make down`
