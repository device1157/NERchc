"""Command line interface for the Ming Shilu NER MVP."""

from __future__ import annotations

import argparse
from pathlib import Path

from .export import build_entities_payload, write_outputs
from .metrics import evaluate_annotation_files
from .modeling import train_token_classifier
from .server import serve_review_app


def cmd_build(args: argparse.Namespace) -> int:
    root = Path(__file__).resolve().parents[2]
    ui_src = root / "ui" / "index.html"
    payload = build_entities_payload(
        input_dir=Path(args.input_dir),
        output_dir=Path(args.output_dir),
        sample_chars=args.sample_chars,
        offline=args.offline,
        link_limit=args.link_limit,
    )
    write_outputs(payload, Path(args.output_dir), ui_src=ui_src if ui_src.exists() else None)
    print(f"Wrote {len(payload['entities'])} entities to {Path(args.output_dir) / 'entities.json'}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    root = Path(__file__).resolve().parents[2]
    serve_review_app(
        workspace=root,
        input_dir=Path(args.input_dir),
        output_dir=Path(args.output_dir),
        port=args.port,
    )
    return 0


def cmd_train(args: argparse.Namespace) -> int:
    train_token_classifier(
        annotations=Path(args.annotations),
        output_dir=Path(args.output_dir),
        model_name=args.model,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        max_length=args.max_length,
    )
    print(f"Saved trained model to {args.output_dir}")
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    metrics = evaluate_annotation_files(
        gold_path=Path(args.annotations),
        pred_path=Path(args.predictions),
        output_dir=Path(args.output_dir),
        target_f1=args.target_f1,
        min_reviewed_segments=args.min_reviewed_segments,
    )
    print(f"Evaluation status: {metrics['status']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ming-ner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Extract entities and write UI-ready outputs.")
    build.add_argument("--input-dir", default="data", help="Folder containing Ming Shilu .txt files.")
    build.add_argument("--output-dir", default="outputs/demo", help="Output folder.")
    build.add_argument(
        "--sample-chars",
        type=int,
        default=8000,
        help="Characters to read per file. Use 0 for full files.",
    )
    build.add_argument("--online", dest="offline", action="store_false", help="Enable CBDB HTTP lookups.")
    build.add_argument("--offline", dest="offline", action="store_true", help="Disable CBDB HTTP lookups.")
    build.set_defaults(offline=True)
    build.add_argument("--link-limit", type=int, default=25, help="Maximum CBDB person lookup attempts.")
    build.set_defaults(func=cmd_build)

    serve = subparsers.add_parser("serve", help="Serve the review WebUI and API locally.")
    serve.add_argument("--input-dir", default="data", help="Folder containing Ming Shilu .txt files.")
    serve.add_argument("--output-dir", default="outputs/demo", help="Output folder to serve.")
    serve.add_argument("--port", type=int, default=8765)
    serve.set_defaults(func=cmd_serve)

    train = subparsers.add_parser("train", help="Train a token-classification NER model from reviewed annotations.")
    train.add_argument("--annotations", default="outputs/review/annotations/reviewed.jsonl")
    train.add_argument("--output-dir", default="models/ming-ner-bert")
    train.add_argument("--model", default="bert-base-chinese")
    train.add_argument("--epochs", type=int, default=8)
    train.add_argument("--batch-size", type=int, default=8)
    train.add_argument("--lr", type=float, default=3e-5)
    train.add_argument("--max-length", type=int, default=256)
    train.set_defaults(func=cmd_train)

    evaluate = subparsers.add_parser("evaluate", help="Evaluate predicted annotations against reviewed gold JSONL.")
    evaluate.add_argument("--annotations", default="outputs/review/annotations/reviewed.jsonl")
    evaluate.add_argument("--predictions", required=True)
    evaluate.add_argument("--output-dir", default="outputs/eval")
    evaluate.add_argument("--target-f1", type=float, default=0.8)
    evaluate.add_argument("--min-reviewed-segments", type=int, default=300)
    evaluate.set_defaults(func=cmd_evaluate)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "sample_chars", None) == 0:
        args.sample_chars = None
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
