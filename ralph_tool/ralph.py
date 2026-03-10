#!/usr/bin/env python3
"""CLI entrypoint for Ralph harness."""

from __future__ import annotations

from ralph_harness import RalphError, err, main


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RalphError as exc:
        err(str(exc))
        raise SystemExit(1)
