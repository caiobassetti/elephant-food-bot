.PHONY: up down logs shell migrate test lint

up:
	docker compose up --build -d

down:
	docker compose down -v

logs:
	docker compose logs -f --tail=200

shell:
	docker compose exec web bash

migrate:
	docker compose exec web python /app/app/manage.py migrate

test:
	docker compose exec web pytest -q

lint:
	docker compose exec web ruff check app
