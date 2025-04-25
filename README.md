# Vibe Coding Conventions

You must follow all these rules:

- This project is critical -- please focus!
- Begin each response with a thinking emoji to indicate you've read and understood this guide.

- Planning:
    - Never alter the stack without my explicit approval.
    - Think step-by-step before making a change.
    - For large changes, provide an implementation plan.
    - Pre-emptively refactor code before making a large change.

- Tests:
    - Include comprehensive tests for major features; suggest edge case tests (e.g., invalid inputs).
    - Include both unit tests and integration tests.

- Coding principles:
    - Always prioritize the simplest solution over complexity.
    - Code should be easy to read and understand.
    - Use meaningful names for variables, functions, etc. Names should reveal intent. Do not use short names for variables.
    - Keep the code as simple as possible. Avoid unnecessary complexity.
    - Follow DRY coding principles.
    - Follow SOLID principles (e.g., single responsibility, dependency inversion) where applicable.
    - Don't write duplicate functions or duplicate functionality in general.
    - Avoid repeating code; reuse existing functionality when possible.

- Documentation:
    - Log completed work in `./progress.md` and next steps in `./TODO.txt`.
    - After each component, summarize what’s done.
    - After major components, write a brief summary in `./docs/[component].md` (e.g., `./docs/login.md`)

- Functions:
    - Functions should be small and do one thing well. They should not exceed about 20 lines.
    - Function names should describe the action being performed.
    - Prefer fewer arguments in functions. Ideally, aim for no more than about five.

- Comments:
    - When comments are used, they should add useful information that is not readily apparent from the code itself.

- Error handling:
    - Properly handle errors and exceptions to ensure the software's robustness.
    - Use exceptions rather than error codes for handling errors.

- Security:
    - Consider security implications of the code. Implement security best practices to protect against vulnerabilities and attacks.

- For Python code only
    - When opening files. always specify an encoding.
    - Keep lines under 100 characters in length.
    - Use lazy % formatting for logging functions -- don't use f-strings for logging functions.
    - Follow Google docstring format.
    - For docstrings, include all arguments, returns, and exceptions.
    - For docstrings, the first line should be in imperative mood.
    - Use full type hints wherever possible for functions and variables.
    - Include a docstring for the module as a whole.
    - DO NOT use inline comments.
    - All comments should have a period at the end, like this sentence.
    - Don't catch overly-broad exceptions. Instead, focus on catching specific exceptions.
    - Follow PEP8, Pylint, Flake8, Pydocstyle, and Black rules.
