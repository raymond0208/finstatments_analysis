# Repository Review: finstatments_analysis

**Date:** 2026-02-19
**Scope:** Architecture, code quality, dependencies, security, and best practices

---

## Executive Summary

This is a small CLI tool (~290 lines of Python) that fetches balance sheet data from Yahoo Finance and 10-K report sections from the SEC, then uses an LLM (DeepSeek via AutoGen) to produce a plain-language financial analysis. The project is functional for its narrow scope, but has significant issues across dependency management, code correctness, security, project hygiene, and architectural design that should be addressed before any production or team use.

---

## 1. Critical Issues

### 1.1 AutoGen Package Identity Crisis

**Files:** `requirements.txt:4`, `requirements.txt:27`, `analyze_BS_w_param.py:11`

Both `autogen==0.7.3` and `pyautogen==0.7.3` are listed in `requirements.txt`. These are now aliases for the **AG2 community fork**, not Microsoft's AutoGen project. Microsoft's official AutoGen has moved to the `autogen-agentchat` package name and is itself entering maintenance mode as Microsoft merges it into the new "Microsoft Agent Framework."

**Problems:**
- Listing both packages is redundant — they install the same code.
- The code imports `from autogen import ConversableAgent`, which will resolve to the AG2 fork, not Microsoft's version.
- Microsoft AutoGen v0.4+ has a fundamentally different event-driven architecture; the `ConversableAgent` API used here is from the legacy v0.2 design.

**Recommendation:** Decide which project you depend on. If Microsoft's, migrate to `autogen-agentchat` and `autogen-ext[openai]`. Remove the redundant package entry either way.

### 1.2 Bug: `lstrip()` Misuse for URL Parsing

**File:** `analyze_BS_w_param.py:90`

```python
report_address = report_address.lstrip("Link: ").split()[0]
```

`str.lstrip()` strips individual **characters**, not a substring. `lstrip("Link: ")` strips any character in the set `{'L', 'i', 'n', 'k', ':', ' '}` from the left of the string. If the URL begins with any of those characters (e.g., `https://` — the `k` wouldn't match but the logic is fragile), this could silently corrupt the URL.

**Fix:** Use `removeprefix("Link: ")` (Python 3.9+) or slice the string:
```python
report_address = report_address.removeprefix("Link: ").split()[0]
```

### 1.3 Silent Failure on Report Fetch

**File:** `analyze_BS_w_param.py:92`

```python
else:
    return report_address  # debug info
```

If `get_sec_report()` returns an error string (e.g., `"Failed to retrieve data: 404"`), `get_10k_section()` silently returns that error string as if it were valid section text. This error string then gets embedded into the LLM prompt, producing a nonsensical analysis without any warning to the user.

**Fix:** Raise an exception or return a clearly distinguishable error type instead of passing error strings through the data pipeline.

### 1.4 `get_sec_report()` Returns Error Strings Instead of Raising Exceptions

**File:** `get_10k_base.py:26`

```python
if response.status_code != 200:
    return f"Failed to retrieve data: {response.status_code}"
```

Returning error messages as regular strings is an anti-pattern. The caller has no reliable way to distinguish between a valid result and an error. The same issue exists on line 42 when no report is found.

**Fix:** Raise proper exceptions (`requests.exceptions.HTTPError`, or a custom exception) so callers can handle errors explicitly.

---

## 2. Outdated Dependencies

| Package | Pinned | Latest (Feb 2026) | Gap | Risk |
|---|---|---|---|---|
| `autogen`/`pyautogen` | 0.7.3 | 0.11.1 (AG2) / 0.7.5 (MS) | Naming crisis | **HIGH** |
| `openai` | 1.61.1 | **2.21.0** | Major version | **HIGH** |
| `yfinance` | 0.2.52 | **1.2.0** | Major version | **HIGH** |
| `pandas` | 2.2.3 | **3.0.1** | Major version | **HIGH** |
| `numpy` | 2.2.2 | **2.4.2** | Minor versions | MEDIUM |
| `pydantic` | 2.10.6 | **2.12.5** | Minor versions | LOW |
| `requests` | 2.32.3 | **2.32.5** | Security patch | **SECURITY** |
| `httpx` | 0.28.1 | 0.28.1 | Current | OK |
| `sec-api` | 1.0.27 | 1.0.32 | Patch versions | LOW |
| `beautifulsoup4` | 4.13.3 | 4.14.3 | Minor version | LOW |

**Key concerns:**
- **`requests` 2.32.3** has a known CVE (CVE-2024-47081) — upgrade to 2.32.5 immediately.
- **`openai`** crossed a major version boundary (1.x → 2.x) with API changes.
- **`yfinance`** crossed a major version boundary (0.2.x → 1.x).
- **`pandas`** crossed a major version boundary (2.x → 3.x) with breaking changes to string handling.

### Unused Dependencies

The following are in `requirements.txt` but not used anywhere in the codebase:
- `peewee==3.17.9` — ORM with no database in the project
- `docker==7.1.0` — Docker SDK with no Docker usage
- `diskcache==5.6.3` — caching library (the project uses manual file caching instead)
- `asyncer==0.0.8` — async utility not imported anywhere
- `termcolor==2.5.0` — not imported
- `tqdm==4.67.1` — not imported
- `tiktoken==0.8.0` — not imported directly

These inflate the dependency surface and installation time for no benefit.

---

## 3. Security Concerns

### 3.1 API Key in URL Query String

**File:** `get_10k_base.py:22`

```python
url = f"https://financialmodelingprep.com/api/v3/sec_filings/{ticker_symbol}?type=10-k&page=0&apikey={self.fmp_api_key}"
```

The API key is embedded directly in the URL query string. This means it will appear in:
- Server access logs
- Browser history (if ever used in a browser context)
- Any HTTP proxy or debugging tool logs
- Stack traces if the request fails

**Recommendation:** Pass the key via a request header or parameter dict where the library can handle it more safely.

### 3.2 No Input Sanitization on Ticker Symbol in API Requests

**Files:** `get_10k_base.py:22`, `analyze_BS_w_param.py:52-56`

The `ticker_symbol` parameter is used directly in URL construction and API calls without validation beyond `isalpha()` in the CLI input loop. The CLI validation is only in the `__main__` block — the functions themselves accept any string. If these functions are ever called programmatically with unsanitized input, there's a risk of URL injection.

### 3.3 `__pycache__` Committed to Repository

The `__pycache__/` directory (containing compiled `.pyc` files) is tracked in git. The `.gitignore` does not exclude it. These files are machine-specific build artifacts and should never be in version control.

### 3.4 No `.env` Protection Beyond `.gitignore`

There is no `.env` in `.gitignore` — wait, it is listed. However, the pattern `.env.*` with `!.env.example` could still allow accidental commits of files like `.env.production`. The gitignore is also missing `__pycache__/` and `*.pyc`.

---

## 4. Code Quality Issues

### 4.1 Module-Level Side Effects

**File:** `analyze_BS_w_param.py:14-22`

```python
load_dotenv()
sec_api_key = os.environ.get("SEC_API_KEY")
if not sec_api_key:
    raise ValueError("SEC_API_KEY is not set in the environment variables")
extractor_api = ExtractorApi(sec_api_key)
```

Environment loading, validation, and API client instantiation happen at **import time**. This means:
- The module cannot be imported for testing without a valid `.env` file.
- The `SEC_API_KEY` check runs even if you only want to use `get_balance_sheet()` (which doesn't need it).
- No way to inject different configurations or mock the API client.

**Fix:** Move initialization into functions or a configuration class. Use dependency injection.

### 4.2 Overly High LLM Temperature

**File:** `analyze_BS_w_param.py:141`

```python
"temperature": 1.3,
```

A temperature of 1.3 is very high for financial analysis. This produces highly creative, non-deterministic output — the opposite of what you want for factual financial reporting. Financial analysis should prioritize accuracy and consistency.

**Recommendation:** Use a temperature of 0.1–0.3 for factual analysis tasks.

### 4.3 Mixed Error Handling Patterns

The codebase uses three different patterns for error reporting:
1. Returning error strings as regular values (`get_10k_base.py:26`)
2. Raising `ValueError` exceptions (`analyze_BS_w_param.py:19`)
3. Catching all exceptions with bare `except Exception` (`analyze_BS_w_param.py:147-154`)

This inconsistency makes the code fragile and hard to debug.

### 4.4 Broad Exception Catching

**File:** `analyze_BS_w_param.py:147`, `analyze_BS_w_param.py:246`

```python
except Exception as e:
    return f"Error during analysis: {str(e)}"
```

Catching `Exception` broadly hides the root cause of failures. `KeyboardInterrupt`, `SystemExit`, and unexpected programming errors all get swallowed into a generic message.

### 4.5 No Type Hints on Return Values for Key Functions

`combine_prompt()` and `save_to_file()` lack return type annotations. `get_10k_section()` can return either section text or an error message string — the same type — making it impossible to distinguish success from failure via the type system.

### 4.6 Typo in Comment

**File:** `analyze_BS_w_param.py:245`

```python
# Execute analysis with validated parametebrs
```

Should be "parameters".

---

## 5. Project Structure & Hygiene Issues

### 5.1 Files That Should Not Be in the Repository

| File | Issue |
|---|---|
| `__pycache__/` | Build artifacts; add to `.gitignore` and remove |
| `TSLA_2025_balance_sheet_analysis.txt` | 67KB generated output file; should be gitignored |
| `www.datamy.co` | Empty 0-byte file with no purpose |
| `get_10k_raw.cpython-311.pyc` | Compiled bytecode from a deleted source file (`get_10k_raw.py`) |

### 5.2 No Test Suite

There are no tests of any kind — no unit tests, integration tests, or even a test runner configuration. For a tool that fetches financial data and produces analysis reports, even basic tests for:
- `combine_prompt()` output format
- Section validation in `get_10k_section()`
- Error handling paths
- CLI input validation logic

...would catch regressions and build confidence in changes.

### 5.3 No CI/CD Pipeline

No GitHub Actions, no linting, no automated testing. This means:
- No protection against breaking changes on merge
- No dependency vulnerability scanning
- No code style enforcement

### 5.4 No `pyproject.toml` or `setup.py`

The project has no Python packaging configuration. Using `pyproject.toml` with a build system (e.g., `hatchling`, `setuptools`) would:
- Define the Python version requirement formally
- Allow `pip install -e .` for development
- Enable proper entry points instead of `python3.11 analyze_BS_w_param.py`

### 5.5 Flat File Structure

All source code is in the root directory. Even for a small project, a `src/` layout improves:
- Import clarity (explicit package vs. implicit current-directory imports)
- Testing (avoids test files accidentally importing from the wrong location)
- Packaging (clear separation of source from project metadata)

Suggested structure:
```
finstatments_analysis/
├── src/
│   └── finstatments_analysis/
│       ├── __init__.py
│       ├── analyzer.py
│       └── sec_fetcher.py
├── tests/
│   ├── test_analyzer.py
│   └── test_sec_fetcher.py
├── pyproject.toml
├── requirements.txt (or managed via pyproject.toml)
├── .env.example
├── .gitignore
└── README.md
```

### 5.6 Repository Name Typo

The repository is named `finstatments_analysis` (missing the 'e' in "statements"). This appears in the clone URL in the README and throughout. Renaming a repo is trivial on GitHub but affects all existing clones.

---

## 6. Architectural Design Concerns

### 6.1 Hardcoded LLM Provider

**File:** `analyze_BS_w_param.py:134-139`

The DeepSeek model, API URL, and configuration are hardcoded. Switching to a different LLM provider (OpenAI, Anthropic, a local model) requires code changes. The `openai` package is a dependency but isn't used directly — it's pulled in transitively by AutoGen.

**Recommendation:** Make the model, base URL, and API key configurable via environment variables or a config file.

### 6.2 No Separation of Concerns

`analyze_BS_w_param.py` handles:
- CLI input/output
- Data fetching from Yahoo Finance
- Data fetching from SEC/FMP
- Prompt construction
- LLM agent interaction
- File I/O

All 250 lines are in one file. Separating into modules (CLI, data sources, analysis, output) would improve testability and maintainability.

### 6.3 Manual File-Based Caching

**File:** `analyze_BS_w_param.py:94-105`

The caching mechanism manually reads/writes files to `.cache/sec_utils/`. This is fragile:
- No cache expiration or invalidation
- No cache size limits
- No concurrent access protection
- The `diskcache` library is already in `requirements.txt` but unused

**Recommendation:** Either use `diskcache` (already a dependency) or Python's `functools.lru_cache`/`shelve` for a more robust solution.

### 6.4 Synchronous Data Fetching Within Async Function

**File:** `analyze_BS_w_param.py:168-187`

`analyze_balance_sheet()` is `async` but calls synchronous functions (`get_balance_sheet()`, `get_10k_section()`) that make blocking HTTP requests. This blocks the event loop. The async/await is only used for the final LLM call, making the async design largely pointless.

**Fix:** Either make the data fetching functions async (using `httpx` or `aiohttp`), or drop async entirely and use synchronous calls throughout.

### 6.5 AutoGen Overhead for Single-Agent Use

The project uses AutoGen's `ConversableAgent` to make a single LLM call with no tool use, no multi-agent interaction, and no conversation history. This is equivalent to a direct API call via the `openai` client but with significantly more framework overhead, dependencies, and complexity.

**Recommendation:** Replace the AutoGen agent with a direct `openai.ChatCompletion` call (or the DeepSeek client), which would:
- Remove ~10 transitive dependencies
- Simplify the code
- Make the LLM behavior more transparent and debuggable

---

## 7. Summary of Recommended Actions

### Immediate (bugs and security)
1. Fix `lstrip("Link: ")` → `removeprefix("Link: ")`
2. Upgrade `requests` to 2.32.5 (CVE fix)
3. Add `__pycache__/`, `*.pyc`, and `*.txt` output files to `.gitignore`
4. Remove `__pycache__/`, `www.datamy.co`, and `TSLA_2025_balance_sheet_analysis.txt` from the repository
5. Lower LLM temperature from 1.3 to 0.1–0.3

### Short-term (code quality)
6. Resolve autogen/pyautogen package confusion — pick one, remove the other
7. Remove unused dependencies (peewee, docker, diskcache, asyncer, termcolor, tqdm, tiktoken)
8. Replace error-string returns with proper exceptions
9. Move module-level side effects into functions
10. Add basic unit tests

### Medium-term (architecture)
11. Make LLM provider/model configurable via environment
12. Separate concerns into multiple modules
13. Either commit to async fully or drop it
14. Evaluate whether AutoGen is needed at all for single-agent use
15. Add `pyproject.toml` and proper project packaging
16. Set up CI with linting and testing
