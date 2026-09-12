"""Disabled compatibility entry point for the pre-migration live bot.

The unsafe monolithic implementation remains available in Git history. The
replacement runtime is ``python -m execution.app`` and starts with live trading
blocked by versioned readiness gates.
"""


def main() -> int:
    raise RuntimeError(
        "Legacy live bot is disabled. Use 'python -m execution.app' and review "
        "docs/PRODUCTION_READINESS.md."
    )


if __name__ == "__main__":
    raise SystemExit(main())
