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
# Cap xdist at the available cores; ``auto`` sees host CPUs and starves nested tests.
PYTEST_WORKERS ?= 6
RUFF_VERSION ?= 0.16.4
TY_VERSION ?= 0.0.74
MBAKE_VERSION ?= 1.4.6
RUFF = $(UV_ENV) $(UV) run --with ruff==$(RUFF_VERSION) ruff
TY = $(UV_ENV) $(UV) run --with ty==$(TY_VERSION) ty
TYPOS_CONFIG_BUILDER_VERSION ?= v0.1.1
TYPOS_CONFIG_BUILDER = $(UV_ENV) $(UV) tool run --python 3.14 --from \
	"git+https://github.com/leynos/typos-config-builder.git@$(TYPOS_CONFIG_BUILDER_VERSION)" \
	typos-config-builder
INTERROGATE_TARGETS ?= src/falcon_correlate
# These tests spawn pytest subprocesses and must run outside the xdist worker pool.
SERIAL_PY_TESTS := src/falcon_correlate/unittests/test_optional_celery_dependency.py
SERIAL_PY_TEST_EXCLUDES := $(foreach source,$(SERIAL_PY_TESTS),--ignore=$(source))
PYLINT_TARGETS ?= src tests examples
PYLINT_PYPY_VERSION ?= 8.0.0
PYLINT_PYTHON_VERSION ?= 3.12
PYLINT_PYPY_ARCHIVE = pypy3.12-v$(PYLINT_PYPY_VERSION)-linux64.tar.gz
PYLINT_PYPY_URL = https://downloads.python.org/pypy/$(PYLINT_PYPY_ARCHIVE)
PYLINT_PYPY_SHA256 = a1b4851459c2b3dffccab71cb08989534fab0839deddd34f0e6bf18add256fd7
PYLINT_TOOLCHAIN_DIR ?= .lint-tools
PYLINT_PYPY_ROOT = $(PYLINT_TOOLCHAIN_DIR)/pypy3.12-v$(PYLINT_PYPY_VERSION)-linux64
PYLINT_PYTHON ?= $(PYLINT_PYPY_ROOT)/bin/pypy3.12
PYLINT_VERSION ?= 4.0.8
ASTROID_VERSION ?= 4.0.4
PYLINT_HOME ?= .pylint_cache/pypy-$(PYLINT_PYTHON_VERSION)-$(PYLINT_PYPY_VERSION)-pylint-$(PYLINT_VERSION)-astroid-$(ASTROID_VERSION)
PYLINT_TOOL = $(UV_ENV) $(UV) tool run --isolated --python $(PYLINT_PYTHON) \
	--from 'pylint==$(PYLINT_VERSION)' --with 'astroid==$(ASTROID_VERSION)'
PYLINT_ANALYSIS_MESSAGES = syntax-error,astroid-error,parse-error,config-parse-error,method-check-failed,raw-checker-failed,bad-plugin-value
PYLINT_CLASSIC_MESSAGES = logging-format-interpolation,logging-format-truncated,logging-fstring-interpolation,logging-not-lazy,logging-too-few-args,logging-too-many-args,logging-unsupported-format,bare-name-capture-pattern,invalid-match-args-definition,match-class-bind-self,match-class-positional-attributes,multiple-class-sub-patterns,too-many-positional-sub-patterns,chained-comparison,condition-evals-to-constant,consider-merging-isinstance,consider-swap-variables,consider-using-in,consider-using-max-builtin,consider-using-min-builtin,consider-using-sys-exit,consider-using-ternary,inconsistent-return-statements,no-else-break,no-else-continue,no-else-raise,no-else-return,redefined-argument-from-local,simplifiable-condition,simplifiable-if-expression,simplifiable-if-statement,simplify-boolean-expression,stop-iteration-return,super-with-arguments,trailing-comma-tuple,unnecessary-negation,useless-return,consider-iterating-dictionary,consider-using-dict-comprehension,consider-using-dict-items,consider-using-enumerate,consider-using-f-string,consider-using-generator,consider-using-get,consider-using-join,consider-using-set-comprehension,unnecessary-comprehension,unnecessary-dict-index-lookup,unnecessary-list-index-lookup,use-a-generator,use-dict-literal,use-implicit-booleaness-not-comparison,use-implicit-booleaness-not-comparison-to-string,use-implicit-booleaness-not-len,use-list-literal,use-maxsplit-arg,use-sequence-for-iteration,use-yield-from,bad-open-mode,bad-thread-instantiation,boolean-datetime,consider-using-with,deprecated-argument,deprecated-attribute,deprecated-class,deprecated-decorator,deprecated-method,forgotten-debug-statement,invalid-envvar-default,invalid-envvar-value,method-cache-max-size-none,redundant-unittest-assert,shallow-copy-environ,singledispatch-method,singledispatchmethod-function,subprocess-popen-preexec-fn,subprocess-run-check,unnecessary-dunder-call,unnecessary-ellipsis,unspecified-encoding,missing-final-newline,mixed-line-endings,superfluous-parens,trailing-newlines,trailing-whitespace,unexpected-line-ending-format,modified-iterating-dict,modified-iterating-list,modified-iterating-set,too-many-arguments,too-many-boolean-expressions,too-many-branches,too-many-lines,too-many-locals,too-many-nested-blocks,too-many-positional-arguments,too-many-public-methods,too-many-statements
PYLINT = PYLINTHOME=$(PYLINT_HOME) $(PYLINT_TOOL) pylint --jobs=1 --disable=all \
	--enable=$(PYLINT_CLASSIC_MESSAGES),$(PYLINT_ANALYSIS_MESSAGES)
DF12_PYTHON_LINTS_REF ?= v0.3.0
DF12_PYTHON_LINTS = git+https://github.com/leynos/df12-python-lints.git@$(DF12_PYTHON_LINTS_REF)
DF12_PYTHON ?= 3.14
DF12_PYLINT_VERSION ?= $(PYLINT_VERSION)
DF12_ASTROID_VERSION ?= $(ASTROID_VERSION)
DF12_PYLINT_HOME ?= .pylint_cache/cpython-$(DF12_PYTHON)-df12-$(DF12_PYTHON_LINTS_REF)-pylint-$(DF12_PYLINT_VERSION)-astroid-$(DF12_ASTROID_VERSION)
DF12_PYLINT_MESSAGES = R9101,C9102,R9103,R9104,C9105,C9106,C9107,R9108,R9109,R9110,R9111,C9112
DF12_PYLINT_TOOL = $(UV_ENV) $(UV) tool run --isolated --python $(DF12_PYTHON) \
	--from '$(DF12_PYTHON_LINTS)' --with 'pylint==$(DF12_PYLINT_VERSION)' \
	--with 'astroid==$(DF12_ASTROID_VERSION)'
DF12_PYLINT = PYLINTHOME=$(DF12_PYLINT_HOME) $(DF12_PYLINT_TOOL) pylint --jobs=1 \
	--disable=all --load-plugins=df12_python_lints \
	--enable=$(DF12_PYLINT_MESSAGES),$(PYLINT_ANALYSIS_MESSAGES)
AMBRLEAKS = $(UV_ENV) $(UV) tool run --isolated --python $(DF12_PYTHON) \
	--from '$(DF12_PYTHON_LINTS)' ambrleaks

.PHONY: help all clean build build-release lint classic-pylint df12-pylint \
        prepare-pylint-python verify-classic-pylint verify-df12-pylint \
        verify-pylint-toolchains fmt check-fmt doctest \
        markdownlint nixie spelling test typecheck \
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
	$(MAKE) --no-print-directory classic-pylint
	$(MAKE) --no-print-directory df12-pylint
	$(AMBRLEAKS) tests

prepare-pylint-python: $(PYLINT_PYPY_ROOT)/bin/pypy3.12 ## Install the pinned PyPy lint runtime

$(PYLINT_PYPY_ROOT)/bin/pypy3.12:
	@set -eu; \
	if [ "$$(uname -s)" != Linux ] || [ "$$(uname -m)" != x86_64 ]; then \
		printf '%s\n' 'PyPy 8.0.0 linting requires a Linux x86_64 host.' >&2; \
		exit 1; \
	fi; \
	mkdir -p '$(PYLINT_TOOLCHAIN_DIR)'; \
	archive='$(PYLINT_TOOLCHAIN_DIR)/$(PYLINT_PYPY_ARCHIVE)'; \
	temporary='$(PYLINT_PYPY_ROOT).temporary'; \
	rm -rf "$$temporary" '$(PYLINT_PYPY_ROOT)'; \
	curl --fail --location --retry 3 '$(PYLINT_PYPY_URL)' --output "$$archive"; \
	printf '%s  %s\n' '$(PYLINT_PYPY_SHA256)' "$$archive" | sha256sum --check --status; \
	mkdir "$$temporary"; \
	tar --extract --gzip --file "$$archive" --strip-components=1 --directory "$$temporary"; \
	test -x "$$temporary/bin/pypy3.12"; \
	mv "$$temporary" '$(PYLINT_PYPY_ROOT)'; \
	rm --force "$$archive"

verify-classic-pylint: prepare-pylint-python ## Verify the exact PyPy Pylint runtime
	$(PYLINT_TOOL) python -c 'import astroid, pylint, sys; assert sys.implementation.name == "pypy"; assert sys.version_info[:2] == (3, 12); assert sys.pypy_version_info[:3] == (8, 0, 0); assert pylint.__version__ == "$(PYLINT_VERSION)"; assert astroid.__version__ == "$(ASTROID_VERSION)"; print(f"classic pylint: executable={sys.executable} version={sys.version} pypy={sys.pypy_version_info} pylint={pylint.__version__} astroid={astroid.__version__}")'

verify-df12-pylint: ## Verify the exact CPython DF12 runtime
	$(DF12_PYLINT_TOOL) python -c 'import astroid, df12_python_lints, pylint, sys; assert sys.implementation.name == "cpython"; assert sys.version_info[:2] == (3, 14); assert pylint.__version__ == "$(DF12_PYLINT_VERSION)"; assert astroid.__version__ == "$(DF12_ASTROID_VERSION)"; print(f"df12 pylint: executable={sys.executable} version={sys.version} pylint={pylint.__version__} astroid={astroid.__version__} plugin={df12_python_lints.__file__}")'

verify-pylint-toolchains: verify-classic-pylint verify-df12-pylint ## Verify both isolated Pylint toolchains

classic-pylint: verify-classic-pylint ## Run focused built-in Pylint checks on Python 3.12 source
	$(PYLINT) $(PYLINT_TARGETS)

df12-pylint: verify-df12-pylint ## Run df12 Pylint checks under CPython 3.14
	$(DF12_PYLINT) $(PYLINT_TARGETS)

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

test: build uv $(VENV_TOOLS) doctest ## Run tests
	$(UV_ENV) $(UV) run pytest -v $(SERIAL_PY_TESTS)
	$(UV_ENV) $(UV) run pytest -v -n $(PYTEST_WORKERS) --dist=loadgroup $(SERIAL_PY_TEST_EXCLUDES)

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | \
	awk 'BEGIN {FS=":"; printf "Available targets:\n"} {printf "  %-20s %s\n", $$1, $$2}'
