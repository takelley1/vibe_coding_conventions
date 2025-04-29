# Vibe Coding Conventions

You must follow all these rules:

- General:
    - This project is critical -- please focus!
    - Don't be obsequious or sycophantic.
    - Don't say things like "Certainly!" or "Absolutely!" or "Of course!"
    - Begin each response with a thinking emoji to indicate you've read and understood this guide.
    - Conserve output tokens in your responses wherever possible.
    - If I say '\\\fix', I want you to do the following:
        - Review this file, then perform any necessary changes to bring the code in adherence to this structure.
        - Improve the code according to the guidelines in this file.

- Planning:
    - Never alter the core tech stack without my explicit approval.
    - Think step-by-step before making a change.
    - For large changes, provide an implementation plan.
    - Refactor code before making a large change.

- Tests:
    - Include comprehensive tests for major features; suggest edge case tests (e.g. invalid inputs).
    - Include unit and integration tests.

- Coding principles:
    - Prefer configuration using environment variables unless stated otherwise.
    - Always prioritize the simplest solution over complexity.
    - Code must be easy to read and understand.
    - Use meaningful names for variables, functions, etc. Names should reveal intent. Don't use short names for variables.
    - Keep code as simple as possible. Avoid unnecessary complexity.
    - Follow DRY and YAGNI coding principles.
    - Follow SOLID principles (e.g., single responsibility, dependency inversion) where applicable.
    - DO NOT over-engineer code!

- Documentation:
    - Log completed work in `./progress.md` and next steps in `./TODO.md`.
    - After each component, summarize what’s done.
    - After major components, write a brief summary in `./docs/[component].md` (e.g., `./docs/login.md`)

- Functions:
    - Functions should be small and do one thing. They should not exceed about 20 lines.
    - Function names should describe what they do.
    - Prefer fewer arguments in functions. Aim for less than about 5.

- Comments:
    - When comments are used, they should add useful information that is not apparent from the code itself.

- Error handling:
    - Handle errors and exceptions to ensure the software's robustness.
    - Use exceptions rather than error codes for handling errors.

- Security:
    - Implement security best-practices to protect against vulnerabilities.
    - Follow input sanitization, parameterized queries, and avoiding hardcoded secrets.

- For bash/zsh/fish code only
    - Follow shellcheck conventions and rules
    - Handle errors gracefully
    - Use `/usr/bin/env` in the shebang line
    - Use `set -euo pipefail`
    - Use `[[ ]]` instead of `[ ]`
    - Use `"$()"` instead of `` ``
    - Use `"${VAR}"` instead of `"$VAR"`

- For Python code only
    - Above all, follow PEP8, Pylint, Flake8, and Pydocstyle, rules. This is your priority.
    - When opening files, specify an encoding, like this: `with open(file, "w", encoding="utf-u") as f:`
    - Keep lines under 100 characters in length.
    - Use lazy % formatting for logging functions instead of f-strings, like this: `logger.info("Merging file: %s", file_path)`
    - Follow Google's docstring format.
    - For docstrings, include all arguments, returns, and exceptions.
    - For docstrings, the first line should be in the imperative mood.
    - Use full type hints wherever possible for functions and variables, like this: `func(arg1: str, arg2: str) -> str:`
    - Include a docstring for the module as a whole.
    - Don't use inline comments. Instead, put the comment on the line before the relevant code.
    - All comments should have a period at the end and be proper sentences, like this: `# This is a comment.`
    - Don't catch overly-broad exceptions. Instead, catch specific exceptions.

    - Here is an example of a correct docstring. It starts at ``` and ends at the following ```:
    ```
    """Convert between repo name and GitLab API code reference.

    Args:
        repo_id_or_name (str): The repository ID or name to convert.

    Returns:
        tuple: A tuple containing (repo_id, repo_name).

    Raises:
        ValueError: If the input is not a valid repository ID or name.
    """
    ```

    - Here's another example of a correct docstring:
    ```
    """Download the manifest CSV file for a given merge request.

    Args:
        mr (dict): The merge request object.
        cr_number (str): The CR number associated with the MR.

    Returns:
        str or None: The local file path if successful, otherwise None.
    """
    ```
