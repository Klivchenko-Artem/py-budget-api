.PHONY: up down logs test lint fmt migrate revision shell

# Всё гоняется в контейнере: так же, как в CI, и не зависит от того,
# что установлено на машине
RUN = docker compose run --rm --entrypoint sh api -c

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f api

test:
	$(RUN) "pytest"

lint:
	$(RUN) "ruff check ."

fmt:
	$(RUN) "ruff check --fix ."

migrate:
	$(RUN) "alembic upgrade head"

# make revision m="добавил кошельки"
revision:
	$(RUN) "alembic revision --autogenerate -m '$(m)'"

shell:
	docker compose exec api sh
