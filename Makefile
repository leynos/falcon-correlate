MDLINT ?= markdownlint-cli2
# `make fmt` and `make check-fmt` call mdtablefix directly. `--git` selects the
# Markdown files Git tracks and `--include-untracked` adds the untracked files
# Git does not ignore, so a new document is formatted before it is staged.
# Both modes need mdtablefix 0.6.0 or later; CI pins the version at the
# install-mdtablefix step.
MDTABLEFIX ?= mdtablefix
MDTABLEFIX_SELECT = --git --include-untracked
MDTABLEFIX_RULES = --wrap --renumber --breaks --ellipsis --fences
NIXIE ?= nixie
export PATH := $(HOME)/.local/bin:$(HOME)/.bun/bin:$(PATH)
UV ?= $(shell command -v uv 2>/dev/null || printf '%s/.local/bin/uv' "$$HOME")
TOOLS = $(MDLINT) uv
VENV_TOOLS = pytest
UV_ENV = UV_CACHE_DIR=.uv-cache UV_TOOL_DIR=.uv-tools
MUTMUT_VERSION ?= 3.6.0

# The CV-005 CodeScene contracts live in shared-actions and run from a full
# commit, so a fix is a pin bump. `.github/cv005.toml` holds this repository's
# only parameters.
CV005_CONTRACTS_REF ?= 88977798a5c3bae1549afb99642529488c665276
CV005_CONTRACTS = $(UV_ENV) $(UV) tool run --python 3.13 \
	--from 'git+https://github.com/leynos/shared-actions@$(CV005_CONTRACTS_REF)\#subdirectory=packages/cv005-contracts' \
	cv005-contracts

TYPOS_CONFIG_BUILDER_VERSION ?= v0.1.3
# Cap xdist at the available cores; ``auto`` sees host CPUs and starves nested tests.
PYTEST_WORKERS ?= 6
RUFF_VERSION ?= 0.16.4
TY_VERSION ?= 0.0.74
MBAKE_VERSION ?= 1.4.6
RUFF = $(UV_ENV) $(UV) run --with ruff==$(RUFF_VERSION) ruff
TY = $(UV_ENV) $(UV) run --with ty==$(TY_VERSION) ty
TYPOS_CONFIG_BUILDER = $(UV_ENV) $(UV) tool run --python 3.14 --from \
	"git+https://github.com/leynos/typos-config-builder.git@$(TYPOS_CONFIG_BUILDER_VERSION)" \
	typos-config-builder
INTERROGATE_TARGETS ?= src/falcon_correlate
PYLINT_PYTHON ?= pypy@3.12
PYLINT_VERSION ?= 4.0.9
PYLINT_TARGETS ?= src tests examples
PYLINT_HOME ?= .pylint_cache
PYLINT = PYLINTHOME=$(PYLINT_HOME) $(UV_ENV) $(UV) tool run --managed-python --python $(PYLINT_PYTHON) --from 'pylint==$(PYLINT_VERSION)' pylint
OPTIONAL_CELERY_TEST := src/falcon_correlate/unittests/test_optional_celery_dependency.py
PROJECT_PYTEST_EXCLUDES := --ignore=$(OPTIONAL_CELERY_TEST)
SKYLOS_VERSION ?= 4.33.2
# Skylos parses source with its own runtime AST; pin Python 3.14 so newer
# project syntax does not produce phantom findings.
SKYLOS_CLI = $(UV_ENV) $(UV) tool run --python 3.14 \
	--from 'skylos==$(SKYLOS_VERSION)' skylos
SKYLOS_SCAN_OPTIONS = --config-file pyproject.toml
SKYLOS = $(SKYLOS_CLI) $(SKYLOS_SCAN_OPTIONS)
SKYLOS_PRODUCTION_TARGETS ?= src/falcon_correlate
SKYLOS_EXCLUDES ?= unittests
SKYLOS_WHITELIST_LOCK ?= .skylos-whitelist.lock
DF12_PYTHON_LINTS_REF ?= v0.3.0
DF12_PYTHON_LINTS = git+https://github.com/leynos/df12-python-lints.git@$(DF12_PYTHON_LINTS_REF)
DF12_PYTHON ?= 3.14
DF12_PYLINT_MESSAGES = R9101,C9102,R9103,R9104,C9105,C9106,C9107,R9108,R9109,R9110,R9111,C9112
DF12_PYLINT = $(UV_ENV) $(UV) run --python $(DF12_PYTHON) pylint \
	--disable=all --load-plugins=df12_python_lints \
	--enable=$(DF12_PYLINT_MESSAGES)
AMBRLEAKS = $(UV_ENV) $(UV) tool run --python $(DF12_PYTHON) \
	--from '$(DF12_PYTHON_LINTS)' ambrleaks

.PHONY: help all clean build build-release lint fmt check-fmt doctest \
        markdownlint nixie spelling makeutil skylos-allow test \
        test-optional-celery typecheck \
        $(TOOLS) $(VENV_TOOLS) test-workflow-contracts \
        test-mutmut-sandbox

.DEFAULT_GOAL := all

test-workflow-contracts: ## Check the CV-005 CodeScene workflow contracts
	$(CV005_CONTRACTS) check --repository .

all: build check-fmt lint typecheck test spelling test-workflow-contracts

.venv: pyproject.toml
	$(UV_ENV) $(UV) venv --clear

build: uv .venv ## Build virtual-env and install deps
	$(UV_ENV) $(UV) sync --group dev

build-release: ## Build artefacts (sdist & wheel)
	python -m build --sdist --wheel

clean: ## Remove build artefacts
	rm -rf build dist *.egg-info \
	  .mypy_cache .pylint_cache .pytest_cache .coverage coverage.* \
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

fmt: ## Format sources
	$(RUFF) format
	$(RUFF) check --select I --fix
	$(MDTABLEFIX) --in-place $(MDTABLEFIX_SELECT) $(MDTABLEFIX_RULES)
	@unset FORCE_COLOR; $(MDLINT) --fix "**/*.md"

check-fmt: ## Verify formatting
	$(RUFF) format --check
	$(MDTABLEFIX) --check $(MDTABLEFIX_SELECT) $(MDTABLEFIX_RULES)

lint: ## Run linters
	$(RUFF) check
	$(UV_ENV) $(UV) run interrogate --fail-under 100 $(INTERROGATE_TARGETS)
	$(PYLINT) $(PYLINT_TARGETS)
	$(DF12_PYLINT) $(PYLINT_TARGETS)
	$(AMBRLEAKS) tests
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
	flock "$(SKYLOS_WHITELIST_LOCK)" env $(SKYLOS_CLI) whitelist "$${SKYLOS_SYMBOL}" --reason "$${SKYLOS_REASON}"

typecheck: build ## Run typechecking
	$(TY) --version
	$(TY) check

markdownlint: spelling $(MDLINT) ## Lint Markdown files and enforce spelling
	$(MDLINT) '**/*.md' '#.uv-cache' '#.uv-tools'

spelling: ## Enforce en-GB-oxendict spelling
	$(TYPOS_CONFIG_BUILDER) gate --repository .

nixie: ## Validate Mermaid diagrams
	$(call ensure_tool,nixie)
	@git ls-files -z '*.md' | \
		xargs -0 -n 1 $(NIXIE) --no-sandbox --max-concurrency 1

doctest: build uv $(VENV_TOOLS) ## Run docstring examples
	$(UV_ENV) $(UV) run pytest --doctest-modules --import-mode=importlib src/falcon_correlate --ignore=src/falcon_correlate/unittests

makeutil: ## Verify the Makefile parser used by contract tests
	$(call ensure_tool,$@)

# These tests spawn pytest subprocesses and must run outside the xdist worker pool.
SERIAL_PY_TESTS := $(OPTIONAL_CELERY_TEST)
SERIAL_PY_TEST_EXCLUDES := $(PROJECT_PYTEST_EXCLUDES)

test: build uv $(VENV_TOOLS) doctest makeutil ## Run tests
	$(UV_ENV) $(UV) run pytest -v $(SERIAL_PY_TESTS)
	$(UV_ENV) $(UV) run pytest -v -n $(PYTEST_WORKERS) --dist=loadgroup $(SERIAL_PY_TEST_EXCLUDES)

test-mutmut-sandbox: build ## Exercise mutmut's configured sandbox on a small module
	$(UV_ENV) $(UV) run --with mutmut==$(MUTMUT_VERSION) \
		mutmut run falcon_correlate.pure.*

test-optional-celery: build uv $(VENV_TOOLS) ## Validate missing-Celery support
	$(UV_ENV) $(UV) run pytest -v $(OPTIONAL_CELERY_TEST)

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | \
	awk 'BEGIN {FS=":"; printf "Available targets:\n"} {printf "  %-20s %s\n", $$1, $$2}'
