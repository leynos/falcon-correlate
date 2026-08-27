MDLINT ?= markdownlint-cli2
NIXIE ?= nixie
MDFORMAT_ALL ?= mdformat-all
export PATH := $(HOME)/.local/bin:$(HOME)/.bun/bin:$(PATH)
UV ?= $(shell command -v uv 2>/dev/null || printf '%s/.local/bin/uv' "$$HOME")
TOOLS = $(MDFORMAT_ALL) ruff ty $(MDLINT) uv
VENV_TOOLS = pytest
UV_ENV = UV_CACHE_DIR=.uv-cache UV_TOOL_DIR=.uv-tools
PATHSPEC_VERSION ?= 1.1.1
TYPOS_VERSION ?= 1.48.0
TYPOS_CONFIG_BUILDER_COMMIT := d6da92f02240a79a945c835f69bdd08a888da1d0
TYPOS_CONFIG_BUILDER_SOURCE := git+https://github.com/leynos/typos-config-builder.git@$(TYPOS_CONFIG_BUILDER_COMMIT)
TYPOS_CONFIG_BUILDER := $(UV_ENV) $(UV) tool run --python 3.14 \
	--from "$(TYPOS_CONFIG_BUILDER_SOURCE)" typos-config-builder
SPELLING_PY_TESTS := scripts/tests/test_typos_rollout_check.py
OPTIONAL_CELERY_TEST := src/falcon_correlate/unittests/test_optional_celery_dependency.py
PROJECT_PYTEST_EXCLUDES := $(foreach source,$(SPELLING_PY_TESTS) $(OPTIONAL_CELERY_TEST),--ignore=$(source))
SPELLING_COVERAGE_ARGS := --cov=typos_rollout_check --cov-fail-under=90
SPELLING_HELPER_PYTEST = PYTHONPATH=scripts $(UV_ENV) $(UV) run --no-project \
	--python 3.14 --with pathspec==$(PATHSPEC_VERSION) --with pytest==9.0.2 \
	--with pytest-cov==7.0.0 python -m pytest
INTERROGATE_TARGETS ?= src/falcon_correlate scripts
PYLINT_PYTHON ?= pypy
PYLINT_TARGETS ?= src tests examples scripts
PYLINT_PYPY_SHIM_REF ?= 726d09f968b4d729ee4b29c71fc732e744854f3b
PYLINT_PYPY_SHIM = git+https://github.com/leynos/pylint-pypy-shim.git@$(PYLINT_PYPY_SHIM_REF)
PYLINT = $(UV_ENV) $(UV) tool run --python $(PYLINT_PYTHON) --from '$(PYLINT_PYPY_SHIM)' pylint-pypy
SKYLOS_VERSION ?= 4.33.2
# Skylos parses source using its own Python AST, so Python 3.14 prevents
# phantom dead-code findings from syntax older tool runtimes cannot parse.
SKYLOS_CLI = $(UV_ENV) $(UV) tool run --python 3.14 \
	--from 'skylos==$(SKYLOS_VERSION)' skylos
SKYLOS = $(SKYLOS_CLI) --config-file pyproject.toml
SKYLOS_PRODUCTION_TARGETS ?= src/falcon_correlate
SKYLOS_EXCLUDES ?= unittests

.PHONY: help all clean build build-release lint fmt check-fmt doctest \
        markdownlint nixie spelling spelling-config spelling-config-write \
	spelling-phrase-check spelling-helper-test makeutil skylos-allow test \
        test-optional-celery typecheck \
        $(TOOLS) $(VENV_TOOLS)

.DEFAULT_GOAL := all

all: build check-fmt lint typecheck test spelling

.venv: pyproject.toml
	$(UV_ENV) $(UV) venv --clear

build: uv .venv ## Build virtual-env and install deps
	$(UV_ENV) $(UV) sync --group dev

build-release: ## Build artefacts (sdist & wheel)
	python -m build --sdist --wheel

clean: ## Remove build artefacts
	rm -rf build dist *.egg-info \
	  .mypy_cache .pytest_cache .coverage coverage.* \
	  lcov.info htmlcov .venv .uv-cache .uv-tools
	find . -type d -name '__pycache__' -print0 | xargs -0 -r rm -rf

define ensure_tool
	@command -v $(1) >/dev/null 2>&1 || { \
	  printf "Error: '%s' is required, but not installed\n" "$(1)" >&2; \
	  exit 1; \
	}
endef

define ensure_tool_venv
	@$(UV_ENV) $(UV) run which $(1) >/dev/null 2>&1 || { \
	  printf "Error: '%s' is required in the virtualenv, but is not installed\n" "$(1)" >&2; \
	  exit 1; \
	}
endef

ifneq ($(strip $(TOOLS)),)
$(TOOLS): ## Verify required CLI tools
	$(call ensure_tool,$@)
endif


ifneq ($(strip $(VENV_TOOLS)),)
.PHONY: $(VENV_TOOLS)
$(VENV_TOOLS): ## Verify required CLI tools in venv
	$(call ensure_tool_venv,$@)
endif

fmt: ruff $(MDFORMAT_ALL) ## Format sources
	$(UV_ENV) $(UV) run ruff format
	$(UV_ENV) $(UV) run ruff check --select I --fix
	$(MDFORMAT_ALL)

check-fmt: ruff ## Verify formatting
	$(UV_ENV) $(UV) run ruff format --check
	# mdformat-all doesn't currently do checking

lint: ruff ## Run linters
	$(UV_ENV) $(UV) run ruff check
	$(UV_ENV) $(UV) run interrogate --fail-under 100 $(INTERROGATE_TARGETS)
	$(PYLINT) $(PYLINT_TARGETS)
	$(SKYLOS) $(SKYLOS_PRODUCTION_TARGETS) --exclude $(SKYLOS_EXCLUDES) \
		--category dead_code --gate --format concise --no-upload --no-provenance \
		--no-grep-verify

skylos-allow: export SKYLOS_SYMBOL = $(value SYMBOL)
skylos-allow: export SKYLOS_REASON = $(value REASON)
skylos-allow: ## Document one named Skylos exception, not an entry point
	@case "$${SKYLOS_SYMBOL}" in *[![:space:]]*) ;; *) \
		printf "Error: SYMBOL is required for a named whitelist exception\\n" >&2; \
		exit 2;; esac
	@case "$${SKYLOS_REASON}" in *[![:space:]]*) ;; *) \
		printf "Error: REASON is required for a named whitelist exception\\n" >&2; \
		exit 2;; esac
	$(SKYLOS_CLI) whitelist "$${SKYLOS_SYMBOL}" --reason "$${SKYLOS_REASON}"

typecheck: build ## Run typechecking
	$(UV_ENV) $(UV) run ty --version
	$(UV_ENV) $(UV) run ty check

markdownlint: spelling $(MDLINT) ## Lint Markdown files and enforce spelling
	$(MDLINT) '**/*.md' '#.uv-cache' '#.uv-tools'

spelling: spelling-phrase-check ## Enforce en-GB-oxendict policy in tracked text
	@git ls-files -z '*.md' | xargs -0 -r env $(UV_ENV) \
		$(UV) tool run typos@$(TYPOS_VERSION) --config typos.toml --force-exclude

spelling-phrase-check: spelling-config ## Reject prohibited spelling phrases
	@PYTHONPATH=scripts $(UV_ENV) $(UV) run --no-project --python 3.14 scripts/typos_rollout_check.py --repository .

spelling-config: spelling-helper-test ## Verify the generated spelling configuration
	@git ls-files --error-unmatch typos.toml >/dev/null
	@$(TYPOS_CONFIG_BUILDER) --repository . --check

spelling-config-write: spelling-helper-test ## Generate the spelling configuration
	@$(TYPOS_CONFIG_BUILDER) --repository .

spelling-helper-test: ## Validate the shared spelling-policy integration
	@$(SPELLING_HELPER_PYTEST) $(SPELLING_PY_TESTS) -c /dev/null --rootdir=. -p no:cacheprovider $(SPELLING_COVERAGE_ARGS)

nixie: ## Validate Mermaid diagrams
	$(call ensure_tool,nixie)
	$(NIXIE) --no-sandbox

doctest: build uv $(VENV_TOOLS) ## Run docstring examples
	$(UV_ENV) $(UV) run pytest --doctest-modules --import-mode=importlib src/falcon_correlate --ignore=src/falcon_correlate/unittests

makeutil: ## Verify the Makefile parser used by contract tests
	$(call ensure_tool,$@)

test: build uv $(VENV_TOOLS) doctest makeutil ## Run tests
	$(UV_ENV) $(UV) run pytest -v -n auto $(PROJECT_PYTEST_EXCLUDES)

test-optional-celery: build uv $(VENV_TOOLS) ## Validate missing-Celery support
	$(UV_ENV) $(UV) run pytest -v $(OPTIONAL_CELERY_TEST)

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | \
	awk 'BEGIN {FS=":"; printf "Available targets:\n"} {printf "  %-20s %s\n", $$1, $$2}'
