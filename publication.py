#!/usr/bin/env python3
"""Verify the publication, or deterministically regenerate its derived artifacts.

Python 3.10+; standard library only. No game interface or network access.
The SQLite verifier is independent of the Base85 replay implemented here.
"""

from __future__ import annotations

import argparse
import base64
from collections import Counter, defaultdict
import hashlib
import itertools
import json
from pathlib import Path
import sqlite3
import struct
import sys
import zlib

from verify_strategy_db import VerificationError, verify_database


ROOT = Path(__file__).resolve().parent
SNAPSHOT = "optimized_20260925_052028"
STEM = "guess5_optimized"
CODE_COUNT = 30_240
BITSET_BYTES = 3_780
RECORD_BYTES = BITSET_BYTES + 5
MAGIC = b"BCS7SUM1"
SOURCE_NAMES = (f"{STEM}.sqlite3", f"{STEM}.strategy.b85", f"{STEM}_steps.txt")
DERIVED_NAMES = ("strategy_tree.json", "summary.json", "SHA256SUMS")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def bitset(ids: tuple[int, ...]) -> bytes:
    result = bytearray(BITSET_BYTES)
    for code_id in ids:
        result[code_id // 8] |= 1 << (code_id % 8)
    return bytes(result)


def decode_strategy(path: Path) -> dict[bytes, int]:
    """Decode and validate every non-singleton decision in the historical export."""
    encoded = b"".join(path.read_bytes().split())
    compressed = base64.b85decode(encoded)
    inflater = zlib.decompressobj()
    payload = inflater.decompress(compressed) + inflater.flush()
    require(inflater.eof and not inflater.unused_data, "Incomplete or trailing zlib stream")
    require(payload[:8] == MAGIC and len(payload) >= 12, "Invalid Base85 payload header")
    count = struct.unpack_from(">I", payload, 8)[0]
    require(len(payload) == 12 + count * RECORD_BYTES, "Base85 record count/length mismatch")
    decisions: dict[bytes, int] = {}
    for offset in range(12, len(payload), RECORD_BYTES):
        raw = payload[offset:offset + BITSET_BYTES]
        size, guess, tag = struct.unpack_from(">HHB", payload, offset + BITSET_BYTES)
        require(tag == 1, "Unsupported Base85 record tag")
        require(1 < size <= CODE_COUNT and 0 <= guess < CODE_COUNT, "Invalid Base85 record range")
        require(sum(byte.bit_count() for byte in raw) == size, "Base85 candidate count mismatch")
        require(raw not in decisions, "Duplicate Base85 candidate set")
        decisions[raw] = guess
    return decisions


def compare_database(path: Path, decisions: dict[bytes, int]) -> None:
    """Compare the export with every non-singleton SQLite record."""
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        seen: set[bytes] = set()
        for state_hash, compressed, count, guess in connection.execute(
            "SELECT state_hash, candidate_bits_z, candidate_count, guess_id "
            "FROM strategy WHERE candidate_count > 1"
        ):
            raw = zlib.decompress(compressed)
            require(hashlib.sha256(raw).digest() == state_hash, "Database state hash mismatch")
            require(sum(byte.bit_count() for byte in raw) == count, "Database candidate count mismatch")
            require(raw in decisions and decisions[raw] == guess, "SQLite/Base85 decision mismatch")
            require(raw not in seen, "Duplicate database candidate set")
            seen.add(raw)
        require(seen == set(decisions), "SQLite/Base85 state coverage mismatch")
    finally:
        connection.close()


def replay_export(decisions: dict[bytes, int]) -> tuple[dict, list[int], list[int], list[str]]:
    """Build the explicit success tree using digit comparisons and set intersections."""
    codes = ["".join(code) for code in itertools.permutations("0123456789", 5)]
    digit_sets = [frozenset(code) for code in codes]
    nodes: list[dict] = []
    successful_steps = [0] * CODE_COUNT
    identification_steps = [0] * CODE_COUNT
    visited: set[bytes] = set()

    def win(secret: int, depth: int, identified_at: int) -> int:
        require(successful_steps[secret] == 0, "A secret has multiple success leaves")
        successful_steps[secret] = depth
        identification_steps[secret] = identified_at
        node_id = len(nodes)
        nodes.append({"id": node_id, "kind": "success", "depth": depth,
                      "secret": codes[secret], "identification_count": identified_at})
        return node_id

    def visit(candidates: tuple[int, ...], depth: int) -> int:
        raw = bitset(candidates)
        if len(candidates) == 1:
            guess = candidates[0]
        else:
            require(raw in decisions, f"Missing Base85 decision at size {len(candidates)}")
            require(raw not in visited, "A non-singleton state repeats")
            visited.add(raw)
            guess = decisions[raw]
        node_id = len(nodes)
        node = {"id": node_id, "kind": "guess", "depth": depth,
                "candidate_count": len(candidates), "guess": codes[guess],
                "state_sha256": digest(raw), "branches": []}
        nodes.append(node)
        buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
        for secret in candidates:
            r = sum(a == b for a, b in zip(codes[secret], codes[guess]))
            s = len(digit_sets[secret] & digit_sets[guess])
            buckets[(r, s)].append(secret)
        for answer, values in sorted(buckets.items()):
            child = tuple(values)
            if answer == (5, 5):
                require(child == (guess,), "Invalid winning branch")
                identified_at = depth if len(candidates) == 1 else depth + 1
                target = win(guess, depth + 1, identified_at)
            else:
                require(len(child) < len(candidates), "A non-winning branch makes no progress")
                target = visit(child, depth + 1)
            node["branches"].append({"feedback": list(answer), "child": target})
        return node_id

    visit(tuple(range(CODE_COUNT)), 0)
    require(all(successful_steps), "The Base85 tree does not cover every secret")
    require(visited == set(decisions), "The Base85 export has unreachable decisions")
    tree = {"format": "bac5-success-tree-v1", "root": 0,
            "feedback": "r=correct positions; s=all shared digits, including r",
            "nodes": nodes}
    return tree, successful_steps, identification_steps, codes


def tree_bytes(tree: dict) -> bytes:
    """One node per line: stable, reasonably compact, and directly readable."""
    header = {key: value for key, value in tree.items() if key != "nodes"}
    prefix = json.dumps(header, ensure_ascii=True, separators=(",", ":"))[:-1]
    lines = [prefix + ',"nodes":[']
    lines.extend(json.dumps(node, ensure_ascii=True, separators=(",", ":")) +
                 ("," if index + 1 < len(tree["nodes"]) else "")
                 for index, node in enumerate(tree["nodes"]))
    return ("\n".join(lines) + "\n]}\n").encode("ascii")


def statistics(steps: list[int]) -> dict:
    total = sum(steps)
    return {"maximum": max(steps), "total": total,
            "mean_numerator": total, "mean_denominator": len(steps),
            "mean_decimal": total / len(steps),
            "distribution": {str(k): v for k, v in sorted(Counter(steps).items())}}


def generate(root: Path) -> tuple[dict[str, bytes], dict]:
    source = root / SNAPSHOT
    database = source / SOURCE_NAMES[0]
    database_report = verify_database(database)
    decisions = decode_strategy(source / SOURCE_NAMES[1])
    compare_database(database, decisions)
    tree, success, identification, codes = replay_export(decisions)
    results = "".join(f"{code} {step}\n" for code, step in zip(codes, success)).encode("ascii")
    require(results == (source / SOURCE_NAMES[2]).read_bytes(), "Published steps.txt differs from replay")
    require(digest(results) == database_report["results_sha256"], "Independent replays disagree")
    require(sum(success) == database_report["total_successful_steps"], "Replay totals disagree")
    require(max(success) == database_report["worst_successful_step"], "Replay maxima disagree")
    encoded_tree = tree_bytes(tree)
    summary = {
        "format": "bac5-publication-summary-v1", "snapshot": SNAPSHOT,
        "rules": {"digits": "0123456789", "length": 5, "repeated_digits": False,
                  "leading_zero_allowed": True, "code_count": CODE_COUNT,
                  "guesses_from_entire_universe": True, "winning_feedback": [5, 5],
                  "s_includes_r": True, "mean_assumes_uniform_secret": True},
        "success": statistics(success), "identification": statistics(identification),
        "strategy": {"root_guess": tree["nodes"][0]["guess"],
                     "non_singleton_decisions": len(decisions),
                     "singleton_decisions": database_report["singleton_records"],
                     "database_records": database_report["record_count"]},
        "tree": {"nodes": len(tree["nodes"]),
                 "guess_nodes": sum(n["kind"] == "guess" for n in tree["nodes"]),
                 "success_leaves": CODE_COUNT, "maximum_depth": max(success),
                 "sha256": digest(encoded_tree)},
        "source_files": {name: {"bytes": (source / name).stat().st_size,
                                "sha256": digest((source / name).read_bytes())}
                         for name in SOURCE_NAMES},
        "claims": {"worst_case_upper_bound": max(success),
                   "global_worst_case_optimality_proved": False,
                   "global_mean_optimality_proved": False,
                   "full_strategy_on_arbitrary_subsets": False},
    }
    derived = {"strategy_tree.json": encoded_tree,
               "summary.json": (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode("ascii")}
    checksums = {name: digest((source / name).read_bytes()) for name in SOURCE_NAMES}
    checksums.update({name: digest(content) for name, content in derived.items()})
    derived["SHA256SUMS"] = "".join(f"{checksums[name]}  {name}\n" for name in sorted(checksums)).encode("ascii")
    return derived, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify", help="read-only verification of all published artifacts")
    verify.add_argument("--root", type=Path, default=ROOT, help="publication folder; defaults to this script's folder")
    export = commands.add_parser("export", help="regenerate tree, summary and checksums in a separate directory")
    export.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve() if args.command == "verify" else ROOT
    generated, summary = generate(root)
    if args.command == "verify":
        for name, expected in generated.items():
            require((root / SNAPSHOT / name).read_bytes() == expected, f"Derived artifact differs: {name}")
    else:
        output = args.output.resolve()
        require(output != (root / SNAPSHOT).resolve(), "Use a separate output directory to preserve the published snapshot")
        output.mkdir(parents=True, exist_ok=True)
        for name in generated:
            require(not (output / name).exists(), f"Output already exists: {name}")
        for name, content in generated.items():
            (output / name).write_bytes(content)
    print(json.dumps({"status": "PASS", "operation": args.command,
                      "secrets_verified": CODE_COUNT,
                      "maximum_success_count": summary["success"]["maximum"],
                      "total_success_count": summary["success"]["total"],
                      "mean_success_count": summary["success"]["mean_decimal"],
                      "maximum_identification_count": summary["identification"]["maximum"],
                      "tree_nodes": summary["tree"]["nodes"]}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (VerificationError, OSError, ValueError, struct.error, zlib.error, sqlite3.Error) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
