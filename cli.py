#!/usr/bin/env python3
"""
Command-line interface for Word Bomb Tool — suggestions and definitions via Datamuse
without the GUI or hotkeys.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Dict, List, Optional

from config import MAX_SUGGESTIONS_DISPLAY, SEARCH_MODES, SORT_MODES
from api_client import DatamuseClient
from suggestion_manager import SuggestionManager

SEARCH_ALIASES: Dict[str, str] = {
    "starts-with": "Starts With",
    "starts": "Starts With",
    "sw": "Starts With",
    "ends-with": "Ends With",
    "ends": "Ends With",
    "ew": "Ends With",
    "contains": "Contains",
    "c": "Contains",
    "rhymes": "Rhymes",
    "r": "Rhymes",
    "related": "Related Words",
    "related-words": "Related Words",
    "rel": "Related Words",
}

SORT_ALIASES: Dict[str, str] = {
    "shortest": "Shortest",
    "s": "Shortest",
    "longest": "Longest",
    "l": "Longest",
    "random": "Random",
    "rand": "Random",
    "frequency": "Frequency",
    "freq": "Frequency",
    "f": "Frequency",
}


def _resolve_mode(alias: str, mapping: Dict[str, str], canonical: List[str], label: str) -> str:
    key = alias.strip().lower().replace("_", "-")
    if key in mapping:
        return mapping[key]
    # Allow exact canonical match (case-insensitive)
    for m in canonical:
        if m.lower() == key or m.lower().replace(" ", "-") == key:
            return m
    choices = ", ".join(sorted(set(mapping.keys())))
    raise argparse.ArgumentTypeError(f"unknown {label} {alias!r}; try one of: {choices}")


def cmd_suggest(args: argparse.Namespace) -> int:
    search_mode = _resolve_mode(args.mode, SEARCH_ALIASES, SEARCH_MODES, "search mode")
    sort_mode = _resolve_mode(args.sort, SORT_ALIASES, SORT_MODES, "sort mode")
    limit = max(1, min(args.limit, MAX_SUGGESTIONS_DISPLAY))

    letters = args.letters.strip()
    if not letters:
        print("error: letters must not be empty", file=sys.stderr)
        return 2

    client = DatamuseClient()
    try:
        raw = client.get_suggestions(letters, search_mode)
        sorted_words = SuggestionManager.sort_suggestions(raw, sort_mode)
        words = sorted_words[:limit]
    finally:
        client.close()

    if args.json:
        print(
            json.dumps(
                {
                    "letters": letters,
                    "search_mode": search_mode,
                    "sort_mode": sort_mode,
                    "api_status": client.status,
                    "words": words,
                },
                indent=2 if args.pretty_json else None,
            )
        )
        return 0

    print(f"search: {search_mode}  sort: {sort_mode}  api: {client.status}")
    if not words:
        print("(no words)")
        return 0
    for i, w in enumerate(words, 1):
        print(f"{i:4d}  {w}")
    return 0


def cmd_define(args: argparse.Namespace) -> int:
    word = args.word.strip()
    if not word:
        print("error: word must not be empty", file=sys.stderr)
        return 2

    client = DatamuseClient()
    try:
        defs = client.get_definitions(word)
    finally:
        client.close()

    if isinstance(defs, str):
        defs_list: List[str] = [defs] if defs else []
    else:
        defs_list = list(defs) if defs else []

    if args.json:
        print(
            json.dumps(
                {
                    "word": word,
                    "api_status": client.status,
                    "definitions": defs_list,
                },
                indent=2 if args.pretty_json else None,
            )
        )
        return 0

    print(f"word: {word}  api: {client.status}")
    if not defs_list:
        print("(no definitions)")
        return 0
    for i, d in enumerate(defs_list, 1):
        print(f"{i}. {d}")
    return 0


def cmd_list_modes(_: argparse.Namespace) -> int:
    print("Search modes (use with suggest --mode):")
    for m in SEARCH_MODES:
        print(f"  - {m}")
    print("\nSort modes (use with suggest --sort):")
    for m in SORT_MODES:
        print(f"  - {m}")
    print("\nAliases examples: starts-with, ends-with, contains, rhymes, related")
    print("                  shortest, longest, random, frequency")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wbt",
        description="Word Bomb Tool CLI — word suggestions and definitions (Datamuse).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="enable debug logging on stderr",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p_suggest = sub.add_parser("suggest", help="fetch word suggestions for letters/pattern")
    p_suggest.add_argument("letters", help="letters or pattern (per search mode)")
    p_suggest.add_argument(
        "--mode",
        "-m",
        default="starts-with",
        help="search mode (default: starts-with). See 'modes' subcommand.",
    )
    p_suggest.add_argument(
        "--sort",
        "-s",
        default="shortest",
        help="sort mode (default: shortest)",
    )
    p_suggest.add_argument(
        "--limit",
        "-n",
        type=int,
        default=MAX_SUGGESTIONS_DISPLAY,
        metavar="N",
        help=f"max words to print (1–{MAX_SUGGESTIONS_DISPLAY}, default: {MAX_SUGGESTIONS_DISPLAY})",
    )
    p_suggest.add_argument("--json", action="store_true", help="print JSON to stdout")
    p_suggest.add_argument(
        "--pretty-json",
        action="store_true",
        help="pretty-print JSON (only with --json)",
    )
    p_suggest.set_defaults(func=cmd_suggest)

    p_define = sub.add_parser("define", help="fetch definitions for a word")
    p_define.add_argument("word", help="word to look up")
    p_define.add_argument("--json", action="store_true", help="print JSON to stdout")
    p_define.add_argument(
        "--pretty-json",
        action="store_true",
        help="pretty-print JSON (only with --json)",
    )
    p_define.set_defaults(func=cmd_define)

    p_modes = sub.add_parser("modes", help="list search and sort mode names")
    p_modes.set_defaults(func=cmd_list_modes)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING)

    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
