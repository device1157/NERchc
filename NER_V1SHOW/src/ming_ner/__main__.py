"""Allow `python -m ming_ner ...` invocation."""

from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
