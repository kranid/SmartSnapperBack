test:
	wsl docker compose --profile test run --rm --build test

test-e2e:
	wsl docker compose --profile e2e up --build --abort-on-container-exit --exit-code-from e2e e2e

test-all: test test-e2e
