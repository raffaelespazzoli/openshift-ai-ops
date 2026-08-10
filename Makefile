REGISTRY ?= quay.io/raffaelespazzoli/openshift-ai-ops
VERSION ?= 0.1.0
CONTAINER_ENGINE ?= podman

BACKEND_IMAGE = $(REGISTRY)-backend:$(VERSION)
SKILLS_IMAGE = $(REGISTRY)-skills:$(VERSION)

.PHONY: all build unit-test integration-test image-build image-push clean help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

all: build unit-test image-build image-push ## Run full pipeline: build, test, image-build, image-push

# ─── Python Build ──────────────────────────────────────────────────────────────

build: ## Install backend dependencies
	cd backend && pip install -e ".[dev]"

# ─── Tests ─────────────────────────────────────────────────────────────────────

unit-test: ## Run unit tests
	cd backend && pytest -m unit -v

integration-test: ## Run integration tests (requires Docker/Podman for testcontainers)
	cd backend && pytest -m "db or api or pipeline" -v

# ─── Container Images ──────────────────────────────────────────────────────────

image-build: image-build-backend image-build-skills ## Build all container images

image-build-backend: ## Build backend container image
	$(CONTAINER_ENGINE) build -t $(BACKEND_IMAGE) -f backend/Containerfile backend/

image-build-skills: ## Build agentic-skills container image
	$(CONTAINER_ENGINE) build -t $(SKILLS_IMAGE) -f skills/Containerfile skills/

image-push: image-push-backend image-push-skills ## Push all container images

image-push-backend: ## Push backend container image
	$(CONTAINER_ENGINE) push $(BACKEND_IMAGE)

image-push-skills: ## Push agentic-skills container image
	$(CONTAINER_ENGINE) push $(SKILLS_IMAGE)

# ─── Development Helpers ───────────────────────────────────────────────────────

dev-setup: ## Configure local environment for integration tests (Podman + Testcontainers)
	@echo "Configuring Podman socket for Testcontainers..."
	systemctl --user start podman.socket
	@echo "Setting environment variables..."
	@echo ""
	@echo "Add the following to your shell profile (~/.bashrc or ~/.zshrc):"
	@echo "  export DOCKER_HOST=unix://$(shell podman info --format '{{.Host.RemoteSocket.Path}}')"
	@echo "  export TESTCONTAINERS_RYUK_DISABLED=true"
	@echo ""
	@echo "Or run integration tests directly with:"
	@echo "  make integration-test-env"

integration-test-env: ## Run integration tests with Podman env configured
	DOCKER_HOST=unix://$(shell podman info --format '{{.Host.RemoteSocket.Path}}') \
	TESTCONTAINERS_RYUK_DISABLED=true \
	$(MAKE) integration-test

lint: ## Run linting
	cd backend && ruff check src/ tests/

format: ## Run code formatting
	cd backend && ruff format src/ tests/

clean: ## Remove build artifacts
	rm -rf backend/dist backend/*.egg-info
	$(CONTAINER_ENGINE) rmi $(BACKEND_IMAGE) $(SKILLS_IMAGE) 2>/dev/null || true
