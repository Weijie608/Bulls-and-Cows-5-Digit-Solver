#!/usr/bin/env python3
"""Independently verify a compact Guess5 SQLite strategy database.

The canonical result content is one ASCII line per codebook entry:
``CODE SPACE successful_steps NEWLINE``.  Its SHA-256 must equal the
``results_sha256`` value stored in the database metadata.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import itertools
import json
import sqlite3
import sys
import time
import zlib
from pathlib import Path
from typing import Sequence


DIGITS = "0123456789"
LENGTH = 5
N_CODES = 30_240
BITSET_BYTES = N_CODES // 8
WIN = (LENGTH, LENGTH)
EXPECTED_METADATA_KEYS = frozenset(
    {
        "codebook_sha256",
        "step_distribution",
        "results_sha256",
        "record_count",
        "created_utc",
    }
)
EXPECTED_STRATEGY_COLUMNS = (
    "state_hash",
    "candidate_bits_z",
    "candidate_count",
    "guess_id",
)


class VerificationError(RuntimeError):
    """The database is malformed, incomplete, or internally inconsistent."""


def build_all_codes() -> tuple[list[str], list[tuple[int, ...]], list[int]]:
    codes = ["".join(item) for item in itertools.permutations(DIGITS, LENGTH)]
    digit_tuples = [tuple(map(int, code)) for code in codes]
    masks = [
        sum(1 << digit for digit in code_digits)
        for code_digits in digit_tuples
    ]
    if len(codes) != N_CODES:
        raise VerificationError(
            f"Expected {N_CODES} codebook entries, got {len(codes)}"
        )
    return codes, digit_tuples, masks


def codebook_sha256(codes: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for code in codes:
        digest.update(code.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def candidate_bitset(candidates: Sequence[int]) -> bytes:
    encoded = bytearray(BITSET_BYTES)
    for code_id in candidates:
        byte_index, bit_index = divmod(code_id, 8)
        encoded[byte_index] |= 1 << bit_index
    return bytes(encoded)


def parse_step_distribution(raw: str) -> dict[int, int]:
    try:
        parsed = json.loads(raw)
        distribution = {
            int(step): int(count) for step, count in parsed.items()
        }
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise VerificationError(f"Invalid step_distribution: {error}") from error
    if (
        not distribution
        or any(step < 1 or count < 0 for step, count in distribution.items())
        or sum(distribution.values()) != N_CODES
    ):
        raise VerificationError(
            f"Invalid step_distribution values: {distribution!r}"
        )
    return dict(sorted(distribution.items()))


def verify_database(path: Path) -> dict[str, object]:
    path = path.expanduser().resolve()
    if path.suffix != ".sqlite3":
        raise VerificationError(f"Expected a .sqlite3 file: {path}")
    if not path.is_file():
        raise VerificationError(f"Database does not exist: {path}")

    started = time.perf_counter()
    codes, digit_tuples, masks = build_all_codes()
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity != ("ok",):
            raise VerificationError(f"SQLite integrity_check failed: {integrity}")

        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if tables != {"metadata", "strategy"}:
            raise VerificationError(f"Unexpected tables: {sorted(tables)!r}")

        metadata_columns = tuple(
            row[1]
            for row in connection.execute("PRAGMA table_info(metadata)")
        )
        if metadata_columns != ("key", "value"):
            raise VerificationError(
                f"Unexpected metadata columns: {metadata_columns!r}"
            )
        strategy_columns = tuple(
            row[1]
            for row in connection.execute("PRAGMA table_info(strategy)")
        )
        if strategy_columns != EXPECTED_STRATEGY_COLUMNS:
            raise VerificationError(
                f"Unexpected strategy columns: {strategy_columns!r}"
            )

        metadata_rows = list(
            connection.execute("SELECT key, value FROM metadata")
        )
        metadata = dict(metadata_rows)
        if len(metadata) != len(metadata_rows):
            raise VerificationError("Duplicate metadata key")
        if set(metadata) != EXPECTED_METADATA_KEYS:
            raise VerificationError(
                "Unexpected metadata keys: "
                f"expected {sorted(EXPECTED_METADATA_KEYS)!r}, "
                f"got {sorted(metadata)!r}"
            )
        if not metadata["created_utc"]:
            raise VerificationError("created_utc is empty")

        calculated_codebook_hash = codebook_sha256(codes)
        if metadata["codebook_sha256"] != calculated_codebook_hash:
            raise VerificationError(
                "codebook_sha256 mismatch: "
                f"stored={metadata['codebook_sha256']}, "
                f"calculated={calculated_codebook_hash}"
            )
        stored_distribution = parse_step_distribution(
            metadata["step_distribution"]
        )
        stored_results_hash = metadata["results_sha256"]
        if len(stored_results_hash) != 64 or any(
            character not in "0123456789abcdef"
            for character in stored_results_hash
        ):
            raise VerificationError(
                f"Invalid results_sha256: {stored_results_hash!r}"
            )

        try:
            stored_record_count = int(metadata["record_count"])
        except ValueError as error:
            raise VerificationError(
                f"Invalid record_count: {metadata['record_count']!r}"
            ) from error
        actual_record_count = connection.execute(
            "SELECT COUNT(*) FROM strategy"
        ).fetchone()[0]
        if stored_record_count != actual_record_count:
            raise VerificationError(
                "record_count mismatch: "
                f"stored={stored_record_count}, actual={actual_record_count}"
            )

        invalid_rows = connection.execute(
            "SELECT COUNT(*) FROM strategy "
            "WHERE length(state_hash) != 32 "
            "OR candidate_count < 1 OR candidate_count > ? "
            "OR guess_id < 0 OR guess_id >= ?",
            (N_CODES, N_CODES),
        ).fetchone()[0]
        if invalid_rows:
            raise VerificationError(
                f"Found {invalid_rows} rows with invalid ranges or hash length"
            )

        steps = [0] * N_CODES
        visited_non_singletons: set[bytes] = set()

        def lookup(candidates: tuple[int, ...]) -> int:
            raw = candidate_bitset(candidates)
            state_hash = hashlib.sha256(raw).digest()
            row = connection.execute(
                """
                SELECT candidate_bits_z, candidate_count, guess_id
                FROM strategy WHERE state_hash = ?
                """,
                (state_hash,),
            ).fetchone()
            if row is None:
                raise VerificationError(
                    "Missing reachable state: "
                    f"size={len(candidates)}, sha256={state_hash.hex()}"
                )
            compressed, stored_count, guess_id = row
            try:
                stored_raw = zlib.decompress(compressed)
            except zlib.error as error:
                raise VerificationError(
                    f"Invalid compressed bitset: {state_hash.hex()}"
                ) from error
            if len(stored_raw) != BITSET_BYTES or stored_raw != raw:
                raise VerificationError(
                    f"Bitset mismatch: {state_hash.hex()}"
                )
            if stored_count != len(candidates):
                raise VerificationError(
                    f"candidate_count mismatch: {state_hash.hex()}"
                )
            if sum(byte.bit_count() for byte in stored_raw) != stored_count:
                raise VerificationError(
                    f"Bitset population mismatch: {state_hash.hex()}"
                )
            return guess_id

        def partition(
            candidates: tuple[int, ...], guess_id: int
        ) -> dict[tuple[int, int], tuple[int, ...]]:
            buckets: dict[tuple[int, int], list[int]] = collections.defaultdict(list)
            guess_digits = digit_tuples[guess_id]
            guess_mask = masks[guess_id]
            for secret_id in candidates:
                secret_digits = digit_tuples[secret_id]
                r = sum(
                    left == right
                    for left, right in zip(secret_digits, guess_digits)
                )
                s = (masks[secret_id] & guess_mask).bit_count()
                buckets[(r, s)].append(secret_id)
            return {
                answer: tuple(bucket) for answer, bucket in buckets.items()
            }

        def visit(candidates: tuple[int, ...], depth: int) -> None:
            if len(candidates) == 1:
                secret_id = candidates[0]
                if steps[secret_id]:
                    raise VerificationError(
                        f"Secret {codes[secret_id]} was assigned twice"
                    )
                steps[secret_id] = depth + 1
                return

            raw = candidate_bitset(candidates)
            if raw in visited_non_singletons:
                raise VerificationError("A reachable non-singleton state repeated")
            visited_non_singletons.add(raw)
            guess_id = lookup(candidates)
            buckets = partition(candidates, guess_id)
            if max(map(len, buckets.values())) >= len(candidates):
                raise VerificationError(
                    f"Non-shrinking decision at state size {len(candidates)}"
                )
            for answer, child in buckets.items():
                if answer == WIN:
                    if child != (guess_id,) or steps[guess_id]:
                        raise VerificationError("Invalid or duplicate winning bucket")
                    steps[guess_id] = depth + 1
                else:
                    visit(child, depth + 1)

        visit(tuple(range(N_CODES)), 0)
        if any(step == 0 for step in steps):
            raise VerificationError("Replay did not cover all 30240 secrets")

        non_singleton_count = connection.execute(
            "SELECT COUNT(*) FROM strategy WHERE candidate_count > 1"
        ).fetchone()[0]
        if non_singleton_count != len(visited_non_singletons):
            raise VerificationError(
                "Non-singleton reachability mismatch: "
                f"database={non_singleton_count}, "
                f"replay={len(visited_non_singletons)}"
            )

        singleton_rows = list(
            connection.execute(
                """
                SELECT state_hash, candidate_bits_z, candidate_count, guess_id
                FROM strategy WHERE candidate_count = 1
                """
            )
        )
        if len(singleton_rows) != N_CODES:
            raise VerificationError(
                f"Expected {N_CODES} singleton rows, got {len(singleton_rows)}"
            )
        singleton_ids: set[int] = set()
        for state_hash, compressed, stored_count, guess_id in singleton_rows:
            try:
                raw = zlib.decompress(compressed)
            except zlib.error as error:
                raise VerificationError("Invalid singleton compression") from error
            if len(raw) != BITSET_BYTES or stored_count != 1:
                raise VerificationError("Malformed singleton bitset")
            if hashlib.sha256(raw).digest() != state_hash:
                raise VerificationError("Singleton state_hash mismatch")
            if sum(byte.bit_count() for byte in raw) != 1:
                raise VerificationError("Singleton bitset population is not one")
            byte_index = next(i for i, byte in enumerate(raw) if byte)
            byte_value = raw[byte_index]
            if byte_value & (byte_value - 1):
                raise VerificationError("Singleton byte contains multiple bits")
            code_id = byte_index * 8 + byte_value.bit_length() - 1
            if code_id != guess_id or code_id in singleton_ids:
                raise VerificationError("Singleton guess_id mismatch or duplicate")
            singleton_ids.add(code_id)
        if len(singleton_ids) != N_CODES:
            raise VerificationError("Singleton rows do not cover the codebook")

        calculated_distribution = dict(
            sorted(collections.Counter(steps).items())
        )
        if calculated_distribution != stored_distribution:
            raise VerificationError(
                "step_distribution mismatch: "
                f"stored={stored_distribution}, "
                f"calculated={calculated_distribution}"
            )

        canonical_results = b"".join(
            f"{code} {step}\n".encode("ascii")
            for code, step in zip(codes, steps)
        )
        calculated_results_hash = hashlib.sha256(canonical_results).hexdigest()
        if calculated_results_hash != stored_results_hash:
            raise VerificationError(
                "results_sha256 mismatch: "
                f"stored={stored_results_hash}, "
                f"calculated={calculated_results_hash}"
            )

        return {
            "status": "PASS",
            "database": str(path),
            "database_sha256": file_sha256(path),
            "created_utc": metadata["created_utc"],
            "record_count": actual_record_count,
            "non_singleton_records": non_singleton_count,
            "singleton_records": len(singleton_rows),
            "total_successful_steps": sum(steps),
            "worst_successful_step": max(steps),
            "step_distribution": calculated_distribution,
            "results_sha256": calculated_results_hash,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Replay all 30240 secrets from a compact Guess5 SQLite strategy "
            "and verify step_distribution and results_sha256."
        )
    )
    parser.add_argument("database", type=Path, help="compact .sqlite3 strategy")
    args = parser.parse_args()
    report = verify_database(args.database)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (VerificationError, sqlite3.Error, OSError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
