#!/usr/bin/env python3
"""
main.py — Entry point for the RARS1 Genomic-RAG query engine.

Usage
-----
  # Step 1: Ingest / re-ingest PubMed data into the vector store
  python main.py ingest

  # Step 2: Ask a single question
  python main.py query "What are the reported RARS1 variants?"

  # Step 3: Interactive REPL (multi-turn)
  python main.py chat

  # Run the evaluation suite
  python main.py evaluate

  # All-in-one (ingest then interactive chat)
  python main.py --fresh chat
"""

import argparse
import logging
import sys
import json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger("main")

BANNER = r"""
╔══════════════════════════════════════════════════════════════╗
║      RARS1 Genomic-RAG — Clinical & Molecular Intelligence   ║
║   Gene: RARS1  |  Disease: Hypomyelinating Leukodystrophy 9  ║
╚══════════════════════════════════════════════════════════════╝
"""

EXAMPLE_QUERIES = [
    "What are the main phenotypes associated with RARS1 mutations?",
    "What specific RARS1 variants have been reported in the literature?",
    "What MRI findings are seen in HLD9 patients?",
    "How does RARS1 cause hypomyelination at the molecular level?",
    "What is the age of onset for RARS1-related leukodystrophy?",
]


# ─────────────────────────────────────────────────────────────────────────────
#  Command handlers
# ─────────────────────────────────────────────────────────────────────────────

def cmd_ingest(force: bool = False) -> None:
    """Fetch PubMed + preprint data and build/update the vector store."""
    from ingest import load_or_ingest
    print("Ingesting RARS1 literature from PubMed and preprint databases...")
    collection = load_or_ingest(force=force)
    print(f"Ingestion complete -- {collection.count()} chunks indexed.\n")


def cmd_query(question: str, json_output: bool = False) -> None:
    """Run a single query and print the result."""
    from rag_pipeline import RAGPipeline
    pipeline = RAGPipeline()
    resp = pipeline.query(question)

    if json_output:
        output = {
            "query":       resp.query,
            "in_scope":    resp.in_scope,
            "answer":      resp.answer,
            "citations":   resp.citations,
            "guardrail":   resp.guardrail.to_dict() if resp.guardrail else None,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(resp.pretty_print())


def cmd_chat() -> None:
    """Interactive REPL for multi-turn querying."""
    from rag_pipeline import RAGPipeline

    print(BANNER)
    print("Type your question and press Enter.  Commands: /quit /examples /help\n")

    pipeline = RAGPipeline()

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("/quit", "/exit", "quit", "exit"):
            print("Goodbye!")
            break

        if user_input.lower() == "/examples":
            print("\nExample queries:")
            for i, q in enumerate(EXAMPLE_QUERIES, 1):
                print(f"  {i}. {q}")
            print()
            continue

        if user_input.lower() == "/help":
            print(
                "\nCommands:\n"
                "  /examples — show example queries\n"
                "  /quit     — exit\n"
                "  /help     — this message\n"
            )
            continue

        print("\nRetrieving and synthesising...\n")
        try:
            resp = pipeline.query(user_input)
            print(resp.pretty_print())
        except Exception as exc:
            log.error(f"Query failed: {exc}")
            print(f"Error: {exc}\n")


def cmd_evaluate() -> None:
    """Run the full evaluation suite."""
    from rag_pipeline import RAGPipeline
    from evaluate import run_evaluation

    print("Running evaluation suite...\n")
    pipeline = RAGPipeline()
    run_evaluation(pipeline)


# ─────────────────────────────────────────────────────────────────────────────
#  CLI parser
# ─────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    """Construct and return the top-level CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="RARS1 Genomic-RAG — clinical & molecular query engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Force re-ingestion before running the command",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # ingest
    ingest_p = subparsers.add_parser("ingest", help="Fetch and index PubMed data")
    ingest_p.add_argument(
        "--force",
        action="store_true",
        help="Re-ingest even if collection already exists",
    )

    # query
    query_p = subparsers.add_parser("query", help="Run a single query")
    query_p.add_argument("question", nargs="+", help="The question to ask")
    query_p.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output result as JSON",
    )

    # chat
    subparsers.add_parser("chat", help="Interactive multi-turn REPL")

    # evaluate
    subparsers.add_parser("evaluate", help="Run the evaluation suite")

    return parser


# ─────────────────────────────────────────────────────────────────────────────
#  Entrypoint
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    """Parse CLI arguments and dispatch to the appropriate command handler."""
    parser = build_parser()
    args   = parser.parse_args()

    # Apply log level
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    # Fresh ingestion requested globally
    if args.fresh:
        cmd_ingest(force=True)

    if args.command == "ingest":
        force = getattr(args, "force", False) or args.fresh
        if not args.fresh:   # avoid double-ingestion
            cmd_ingest(force=force)

    elif args.command == "query":
        question = " ".join(args.question)
        cmd_query(question, json_output=args.json_output)

    elif args.command == "chat":
        cmd_chat()

    elif args.command == "evaluate":
        cmd_evaluate()

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
