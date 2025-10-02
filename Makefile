DOCKERHUB_USER ?= caiobassetti
IMAGE_NAME ?= elephants-food-bot
IMAGE_TAG ?= dev-0.1

.PHONY: up down logs shell migrate superuser token simulation test lint docker-build-prod docker-push-prod

up:
	docker compose up --build -d

down:
	docker compose down -v

logs:
	docker compose logs -f --tail=200

shell:
	docker compose exec web bash

migrate:
	docker compose exec web python app/manage.py migrate

superuser:
	docker compose exec web python app/manage.py createsuperuser

token:
	@if [ -z "$(U)" ]; then echo "Usage: make token U=<username>"; exit 1; fi; \
	docker compose exec web python app/manage.py drf_create_token $(U)

simulation:
	docker compose exec web python app/manage.py simulate_foods --runs 5

test:
	docker compose exec web pytest -q

lint:
	docker compose exec web ruff check .

smoke:
	docker compose exec web python app/manage.py migrate --noinput
	docker compose exec web python app/manage.py simulate_foods --runs=3

docker-build-prod:
	docker build -f docker/web.azure.Dockerfile -t $(DOCKERHUB_USER)/$(IMAGE_NAME):$(IMAGE_TAG) .

docker-push-prod:
	docker push $(DOCKERHUB_USER)/$(IMAGE_NAME):$(IMAGE_TAG)
