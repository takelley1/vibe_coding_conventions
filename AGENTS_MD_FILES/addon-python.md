Append this to the end of Python-related AGENTS.md files













## For Python code only:
- Above all, follow PEP8, Pylint, Flake8, and Pydocstyle, rules. This is your priority.
- Keep lines under 100 characters in length.
- Follow Google's docstring format.
- For docstrings, include all arguments, returns, and exceptions.
- For docstrings, the first line should be in the imperative mood.
- Include a docstring for the module as a whole.
- Don't use inline comments. Instead, put the comment on the line before the relevant code.
- Don't catch overly-broad exceptions. Instead, catch specific exceptions.

# WRONG: Exception as control flow
try:
    value = mapping[key]
    process(value)
except KeyError:
    pass

# CORRECT: Check first
if key in mapping:
    value = mapping[key]
    process(value)

# ACCEPTABLE: Third-party API forces exception handling
def _get_bigquery_sample(sql_client, table_name):
    """
    BigQuery's TABLESAMPLE doesn't work on views.
    There's no reliable way to determine a priori whether
    a table supports TABLESAMPLE.
    """
    try:
        return sql_client.run_query(f"SELECT * FROM {table_name} TABLESAMPLE...")
    except Exception:
        return sql_client.run_query(f"SELECT * FROM {table_name} ORDER BY RAND()...")

2. Never Swallow Exceptions

# WRONG: Silent exception swallowing
try:
    risky_operation()
except:
    pass

# CORRECT: Let exceptions bubble up
risky_operation()

3. Magic Methods Must Be O(1)
Magic methods like__len__, __bool__, and __contains__ are called frequently and implicitly. They must run in constant time.

# WRONG: __len__ doing iteration
def __len__(self) -> int:
    return sum(1 for _ in self._items)

# CORRECT: O(1) __len__
def __len__(self) -> int:
    return self._count

4. Check Existence Before Resolution

# WRONG: resolve() can raise OSError on non-existent paths
wt_path_resolved = wt_path.resolve()
if current_dir.is_relative_to(wt_path_resolved):
    current_worktree = wt_path_resolved

# CORRECT: Check exists() first
if wt_path.exists():
    wt_path_resolved = wt_path.resolve()
    if current_dir.is_relative_to(wt_path_resolved):
        current_worktree = wt_path_resolved

5. Defer Import-Time Computation

# WRONG: Path computed at import time
SESSION_FILE = Path("scratch/current-session-id")

# CORRECT: Defer with @cache
@cache
def _session_file_path() -> Path:
    """Return path to session ID file (cached after first call)."""
    return Path("scratch/current-session-id")

6. Verify Your Casts at Runtime

# WRONG: Blind cast
cast(dict[str, Any], doc)["key"] = value

# CORRECT: Assert before cast
assert isinstance(doc, MutableMapping), f"Expected MutableMapping, got {type(doc)}"
cast(dict[str, Any], doc)["key"] = value

7. Use Literal Types for Fixed Values

# WRONG: Bare strings
issues.append(("orphen-state", "desc"))  # Typo goes unnoticed!

# CORRECT: Literal type
IssueCode = Literal["orphan-state", "orphan-dir", "missing-branch"]

@dataclass(frozen=True)
class Issue:
    code: IssueCode
    message: str

8. Declare Variables Close to Use

# WRONG: Variable declared 20 lines before use
def process_data(ctx, items):
    result_path = compute_result_path(ctx)
    # ... 20 lines of other logic ...
    save_to_path(transformed, result_path)

# CORRECT: Inline at call site
def process_data(ctx, items):
    # ... other logic ...
    save_to_path(transformed, compute_result_path(ctx))

9. Keyword Arguments for Complex Functions

# WRONG: Positional chaos - what do these values mean?
response = fetch_data(api_url, 30.0, 3, {"Accept": "application/json"}, token)

# CORRECT: Keyword-only after first param
def fetch_data(
    url,
    *,
    timeout: float,
    retries: int,
    headers: dict[str, str],
    auth_token: str,
) -> Response:
    ...

# Call site is self-documenting
response = fetch_data(
    api_url,
    timeout=30.0,
    retries=3,
    headers={"Accept": "application/json"},
    auth_token=token,
)

10. Default Values Are Dangerous
Avoid default parameter values unless absolutely necessary. They are a significant source of bugs because callers forget to pass a parameter and get unexpected results.

# DANGEROUS: Caller forgets encoding, gets wrong behavior
def process_file(path: Path, encoding: str = "utf-8") -> str:
    return path.read_text(encoding=encoding)

content = process_file(legacy_latin1_file)  # Bug: should be encoding="latin-1"

# SAFER: Require explicit choice
def process_file(path: Path, encoding: str) -> str:
    return path.read_text(encoding=encoding)

content = process_file(legacy_latin1_file, encoding="latin-1")

## Examples

<Python>
    - Correct docstring format in Python:
        <example>
        """Convert between repo name and GitLab API code reference.

        Args:
            repo_id_or_name (str): The repository ID or name to convert.

        Returns:
            tuple: A tuple containing (repo_id, repo_name).

        Raises:
            ValueError: If the input is not a valid repository ID or name.
        </example>

        <example>
        """Download the manifest CSV file for a given merge request.

        Args:
            mr (dict): The merge request object.
            cr_number (str): The CR number associated with the MR.

        Returns:
            str or None: The local file path if successful, otherwise None.
        """
        </example>

    - Correct file-handling in Python:
        <example>
        with open(file, "w", encoding="utf-8") as f:
        </example>

    - Correct logging format in Python:
        <example>
        logger.info("Merging file: %s", file_path)
        </example>

    - Correct function syntax in Python:
        <example>
        def my_function(arg1: str, arg2: str) -> str:
        </example>

    - Correct comment format in Python:
        <example>
        # This comment has a period at the end and explains useful information.
        </example>

        <example>
        # This comment goes over multiple lines.
        #   You can see how starting from the second line it's indented.
        #   Here's the third line of the comment.
        </example>

</Python>
