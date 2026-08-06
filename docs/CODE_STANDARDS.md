# Zecpath AI — Code Standards & Documentation Format

## Style
- Follow **PEP 8**. Format with `black` and lint with `flake8` before committing.
- Use type hints on all function signatures.
- Max line length: 100 characters (black default is close enough — don't fight the formatter).

## Naming
- `snake_case` for functions, variables, and file names.
- `PascalCase` for classes (e.g. `ATSService`, `BaseAIService`).
- Module-level constants in `UPPER_SNAKE_CASE`.

## Structure
- Every AI service subclasses `utils.base_service.BaseAIService` and implements `process()`.
- Every service returns a response dict via `self._base_response()` plus its own fields, so every service's output is consistent (`service`, `model_version`, `status`, ...).
- No service imports another service's module directly — communication between services happens through the API Gateway (REST/Queue/Webhook), matching the Day 2 architecture. Within `tests/`, direct imports are fine.

## Logging
- Never use `print()` for anything except quick local debugging in an `if __name__ == "__main__":` block.
- Always log through `utils.logger.get_logger(__name__)`.
- Log levels:
  - `DEBUG` — internal details useful only while developing
  - `INFO` — normal operational events (call started, score computed)
  - `WARNING` — recoverable issues (retry triggered, missing optional field)
  - `ERROR` — a request failed and could not be recovered

## Docstrings
Every module starts with a triple-quoted docstring stating:
1. What Day 2 process number/service it implements
2. Its input contract
3. Its output contract

Every public function/class gets a one-line summary docstring minimum.

## Tests
- One test file per module under `tests/`, named `test_<module>.py`.
- Use `pytest`. Test both a normal case and an edge case per function where practical.
- Run the full suite with:
  ```
  pytest --cov=. --cov-report=term-missing
  ```

## Commits
- Small, focused commits. One logical change per commit.
- Commit message format: `<area>: <short description>` e.g. `ats_engine: add keyword matching logic`
