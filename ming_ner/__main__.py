"""Allow `python -m ming_ner ...` from the workspace root."""

from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
