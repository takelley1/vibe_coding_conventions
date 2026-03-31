Append this to the end of Rust-related AGENTS.md files













Always collapse if statements per https://rust-lang.github.io/rust-clippy/master/index.html#collapsible_if
Always inline format! args when possible per https://rust-lang.github.io/rust-clippy/master/index.html#uninlined_format_args
Use method references over closures when possible per https://rust-lang.github.io/rust-clippy/master/index.html#redundant_closure_for_method_calls
Avoid bool or ambiguous Option parameters that force callers to write hard-to-read code such as foo(false) or bar(None). Prefer enums, named methods, newtypes, or other idiomatic Rust API shapes when they keep the callsite self-documenting.
When you cannot make that API change and still need a small positional-literal callsite in Rust, follow the argument_comment_lint convention:

    Use an exact /*param_name*/ comment before opaque literal arguments such as None, booleans, and numeric literals when passing them by position.
    Do not add these comments for string or char literals unless the comment adds real clarity; those literals are intentionally exempt from the lint.
    If you add one of these comments, the parameter name must exactly match the callee signature.

When possible, make match statements exhaustive and avoid wildcard arms.
When writing tests, prefer comparing the equality of entire objects over fields one by one.
When making a change that adds or changes an API, ensure that the documentation in the docs/ folder is up to date if applicable.
