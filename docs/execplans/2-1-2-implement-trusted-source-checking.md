# Implement trusted source checking with Classless Inter-Domain Routing (CIDR) subnet support

This ExecPlan is a living document. The sections `Progress`,
`Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must
be kept up to date as work proceeds.

## Purpose / Big Picture

After this change, the middleware will validate incoming correlation IDs
against a configurable set of trusted sources. If `req.remote_addr` matches an
IP address or falls within a CIDR subnet in the trusted sources list, incoming
correlation ID headers will be accepted. Otherwise, or if the header is
missing, a new ID will be generated. This implements design-doc section 3.2.2.

Success is observable when:

1. Unit tests verify `_is_trusted_source()` method works for exact IPs, CIDR
   subnets, and edge cases
2. Behaviour-Driven Development (BDD) tests demonstrate end-to-end trust-based
   ID acceptance/rejection
3. Invalid IP/CIDR formats in `trusted_sources` raise `ValueError` at
   configuration time
4. Documentation describes the new behaviour
5. `docs/roadmap.md` shows task 2.1.2 as complete

## Progress

- [x] Capture requirements from the roadmap and design document
- [x] Add unit tests for `_is_trusted_source()` method
- [x] Add unit tests for IP/CIDR validation at config time
- [x] Add unit tests for trusted source integration in `process_request`
- [x] Add BDD scenarios for trusted source behaviour
- [x] Implement parsed network storage in `CorrelationIDConfig`
- [x] Implement `_is_trusted_source()` method in middleware
- [x] Integrate trust checking into `process_request()`
- [x] Update documentation and roadmap
- [x] Run formatting, linting, type checking, and tests

## Surprises & Discoveries

1. **Existing tests assumed no trusted sources**: The existing header retrieval
   tests and Behaviour-Driven Development (BDD) scenarios were written before
   trusted source checking existed. They sent correlation ID headers without
   configuring any trusted sources, which now means the IDs get rejected. Fixed
   by configuring `trusted_sources=["127.0.0.1"]` since Falcon's TestClient
   uses 127.0.0.1 as the default `remote_addr`.

2. **ID generation deferred to task 2.2**: The design spec says to "generate new
   ID" when source is untrusted, but the default `uuid7_generator` raises
   `NotImplementedError`. Rather than add a temporary fallback, the generation
   logic is deferred to task 2.2 (UUIDv7 generation). For now, untrusted
   sources simply don't get a `correlation_id` set on `req.context`.

3. **BDD step definition collision**: Adding a new step for "a custom ID
   generator that returns X" conflicted with an existing step that creates a
   fixture. Resolved by removing the duplicate step since generation is no
   longer needed in the new BDD scenarios.

## Decision Log

1. **Parse networks at config time (not request time)**: Using
   `ipaddress.ip_network(source, strict=True)` at instantiation validates early
   and stores pre-parsed `IPv4Network`/`IPv6Network` objects for O(1) request
   time lookups.

2. **Use `strict=True` for CIDR validation**: This ensures users provide network
   addresses (for example, `10.0.0.0/24`) rather than host addresses with
   subnet notation (for example, `10.0.0.5/24`). Prevents subtle configuration
   mistakes.

3. **Defer ID generation to task 2.2**: Rather than implement a temporary
   fallback generator, the `process_request` method only sets `correlation_id`
   when an incoming ID is accepted from a trusted source. This keeps the
   implementation clean and aligned with the roadmap.

4. **Trust existing test fixtures by default**: Updated the BDD step
   "a Falcon application with CorrelationIDMiddleware" to configure
   `trusted_sources=["127.0.0.1"]` so that header capture tests work correctly
   with the new trust checking logic.

## Outcomes & Retrospective

**What went well:**

- TDD approach caught edge cases early (None remote_addr, malformed IPs)
- Using stdlib `ipaddress` module avoided external dependencies
- Pre-parsing networks provides efficient O(1) request-time lookups
- Defensive `_is_trusted_source()` never accidentally grants trust

**What could be improved:**

- The behaviour change (rejecting IDs from untrusted sources) broke existing
  tests. Future middleware changes should consider backward compatibility more
  carefully.

**Test coverage summary:**

- 17 new unit tests for `_is_trusted_source()` and config validation
- 6 new integration tests for `process_request` trust checking
- 4 new BDD scenarios for trusted source behaviour
- All 94 tests pass (11 skipped - workflow tests requiring external tools)

## Context and Orientation

### Key Files

| File                                                | Purpose                                                                  |
| --------------------------------------------------- | ------------------------------------------------------------------------ |
| `src/falcon_correlate/middleware.py`                | Core middleware with `CorrelationIDConfig` and `CorrelationIDMiddleware` |
| `src/falcon_correlate/unittests/test_middleware.py` | Colocated unit tests                                                     |
| `tests/bdd/middleware.feature`                      | BDD feature specifications                                               |
| `tests/bdd/test_middleware_steps.py`                | BDD step definitions                                                     |
| `tests/conftest.py`                                 | Shared test fixtures                                                     |
| `docs/users-guide.md`                               | User documentation                                                       |
| `docs/falcon-correlation-id-middleware-design.md`   | Design document                                                          |
| `docs/roadmap.md`                                   | Task checklist                                                           |

### Current State

The middleware already has:

- `CorrelationIDConfig` dataclass with `trusted_sources: frozenset[str]` field
- Validation that `trusted_sources` does not contain empty strings
- `CorrelationIDMiddleware` class with property access to `trusted_sources`
- `_get_incoming_header_value(req)` method that reads the header
- `process_request(req, resp)` currently stores incoming header on
  `req.context.correlation_id` without trust checking

What needs to be added:

- IP/CIDR format validation at config time
- Parsed network objects stored for O(1) lookup
- `_is_trusted_source(remote_addr)` method
- Integration of trust checking into `process_request()`

### Design Specification (from section 3.2.2)

> The identification of trusted sources will typically be based on the IP
> address of the direct peer connection, available via `req.remote_addr`. The
> middleware will be configurable with a list of trusted IP addresses or
> subnets. If `req.remote_addr` matches an entry in this list, an incoming
> `X-Correlation-ID` header value can be accepted. Otherwise, or if the header
> is missing, a new ID must be generated.

## Plan of Work

### Phase 1: Write Tests (Test-Driven Development)

Following AGENTS.md guidance, tests are written before implementation.

#### 1.1 Unit Tests for `_is_trusted_source()` Method

Add a new test class `TestTrustedSourceChecking` in
`src/falcon_correlate/unittests/test_middleware.py` covering:

- Exact IP matching (IPv4 and IPv6)
- CIDR subnet matching (IPv4 and IPv6)
- Edge cases: `None` remote_addr, empty trusted sources, malformed addresses
- Multiple sources with any-match semantics

#### 1.2 Unit Tests for IP/CIDR Validation at Config Time

Add tests to `TestCorrelationIDConfigValidation` class for:

- Invalid IP addresses raise `ValueError`
- Invalid CIDR notation raises `ValueError`
- CIDR with host bits set raises `ValueError` (using `strict=True`)

#### 1.3 Unit Tests for Trust Integration in `process_request`

Create `TestTrustedSourceIntegration` class covering:

- Trusted source accepts incoming ID
- Untrusted source generates new ID
- Empty trusted sources always generates
- CIDR matching accepts incoming ID
- Missing header generates ID even from trusted source

#### 1.4 BDD Scenarios

Add scenarios to `tests/bdd/middleware.feature`:

- Incoming ID accepted from trusted source
- Incoming ID rejected from untrusted source
- CIDR subnet matching accepts incoming ID
- Missing header generates ID even from trusted source

### Phase 2: Implement Parsed Network Storage

Modify `CorrelationIDConfig` dataclass:

1. Import `ipaddress` module at top of file
2. Add a private field `_parsed_networks` to store parsed
   `IPv4Network`/`IPv6Network` objects
3. Modify `_validate_trusted_sources()` to parse and validate IP/CIDR formats
   using `ipaddress.ip_network(source, strict=True)`

**Design decision**: Parse networks at configuration time for O(1) request-time
lookup. Using `strict=True` ensures users explicitly provide network addresses,
not host addresses with CIDR notation (for example, `10.0.0.5/24` is rejected,
must use `10.0.0.0/24`).

### Phase 3: Implement `_is_trusted_source()` Method

Add to `CorrelationIDMiddleware` class a method that:

1. Returns `False` if `remote_addr` is `None` or empty
2. Returns `False` if no trusted sources configured
3. Parses `remote_addr` with `ipaddress.ip_address()`
4. Returns `False` for malformed addresses (catches `ValueError`)
5. Returns `True` if address is in any configured network

### Phase 4: Integrate Trust Checking into `process_request()`

Modify `process_request` to:

1. Get incoming header value
2. Check if source is trusted AND header is present
3. If trusted: accept incoming ID
4. Otherwise: generate new ID using `self.generator()`
5. Always set `req.context.correlation_id`

**Behaviour change**: `req.context.correlation_id` is now always set (either to
incoming or generated ID), aligning with the design spec that a correlation ID
should always be available.

### Phase 5: Update Documentation

Update these files:

- `docs/users-guide.md`: Add CIDR examples, validation behaviour, security notes
- `docs/falcon-correlation-id-middleware-design.md`: Add section 4.6.6 with
  implementation notes about IP/CIDR matching
- `docs/roadmap.md`: Mark task 2.1.2 items complete

## Concrete Steps

1. Create tests before changing code.

   - Add `TestTrustedSourceChecking` class to unit tests with parametrised tests
     for exact IP matching, CIDR matching, IPv6 support, and edge cases.
   - Add config validation tests for invalid IP/CIDR formats.
   - Add `TestTrustedSourceIntegration` class for `process_request` integration.
   - Add BDD scenarios and step definitions for trusted source behaviour.

2. Run targeted tests to confirm they fail before the implementation change.

   Example command (run from `/root/repo`):

   ```bash
   set -o pipefail
   make build && uv run pytest -k "trusted" -v 2>&1 \
       | tee /tmp/falcon-correlate-trusted-tests.log
   ```

   Expected result: new tests fail because `_is_trusted_source()` does not
   exist and `process_request()` does not check trust.

3. Implement IP/CIDR parsing in `CorrelationIDConfig`.

   - Add `import ipaddress` at top of `middleware.py`.
   - Add `_parsed_networks` field to dataclass.
   - Modify `_validate_trusted_sources()` to parse and validate using
     `ipaddress.ip_network(source, strict=True)`.
   - Use `object.__setattr__()` to set frozen field.

4. Implement `_is_trusted_source()` method.

   - Add method to `CorrelationIDMiddleware` class.
   - Handle edge cases: `None`, malformed, empty trusted sources.
   - Use `any(addr in network for network in self._config._parsed_networks)`.

5. Integrate trust checking into `process_request()`.

   - Modify method to check trust before accepting incoming ID.
   - Generate new ID when source not trusted or header missing.
   - Always set `req.context.correlation_id`.

6. Update documentation and roadmap.

   - `docs/users-guide.md`: document CIDR support, validation, security notes.
   - `docs/falcon-correlation-id-middleware-design.md`: add implementation
     notes.
   - `docs/roadmap.md`: check off task 2.1.2 items.

7. Run formatting, linting, type checking, and the full test suite.

   ```bash
   set -o pipefail
   make fmt 2>&1 | tee /tmp/falcon-correlate-fmt.log
   set -o pipefail
   make check-fmt 2>&1 | tee /tmp/falcon-correlate-check-fmt.log
   set -o pipefail
   make lint 2>&1 | tee /tmp/falcon-correlate-lint.log
   set -o pipefail
   make typecheck 2>&1 | tee /tmp/falcon-correlate-typecheck.log
   set -o pipefail
   make test 2>&1 | tee /tmp/falcon-correlate-test.log
   set -o pipefail
   make markdownlint 2>&1 | tee /tmp/falcon-correlate-markdownlint.log
   set -o pipefail
   make nixie 2>&1 | tee /tmp/falcon-correlate-nixie.log
   ```

   Expected result: all commands exit 0.

## Validation and Acceptance

- **Unit tests**: New tests in `test_middleware.py` verify:
  - Exact IP matching returns correct boolean
  - CIDR subnet matching works for IPv4 and IPv6
  - Edge cases handled correctly (`None`, malformed, empty)
  - Config validation rejects invalid IP/CIDR formats
  - `process_request` integrates trust checking correctly

- **Behavioural tests**: BDD scenarios verify end-to-end:
  - Trusted source accepts incoming ID
  - Untrusted source generates new ID
  - CIDR matching works
  - Missing header generates ID even from trusted source

- **Documentation**: Users guide updated with CIDR examples and security notes

- **Quality gates**: All pass (`make check-fmt`, `make lint`, `make typecheck`,
  `make test`, `make markdownlint`, `make nixie`)

## Idempotence and Recovery

All steps are safe to re-run:

- Tests can be run repeatedly
- Documentation changes are idempotent
- Quality gate checks are read-only

If implementation fails validation:

1. Fix failing tests
2. Re-run `make test` to verify
3. Re-run full quality gate suite

## Artifacts and Notes

- Log files created in `/tmp/` by `tee` commands
- Test coverage should remain at or above 90%
- No new external dependencies required (uses stdlib `ipaddress`)

## Interfaces and Dependencies

### New/Modified Interfaces

```python
# In CorrelationIDConfig (private field)
_parsed_networks: tuple[IPv4Network | IPv6Network, ...]

# In CorrelationIDMiddleware
def _is_trusted_source(self, remote_addr: str | None) -> bool:
    """Check if remote_addr is from a trusted source."""
```

### Modified Behaviour

```python
# process_request now always sets correlation_id
def process_request(self, req: falcon.Request, resp: falcon.Response) -> None:
    """Accepts incoming ID only from trusted sources, generates otherwise."""
```

### Dependencies

- Python standard library `ipaddress` module (no new dependencies)
- Existing Falcon testing infrastructure
