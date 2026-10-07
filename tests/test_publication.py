"""Consume the serialized tree independently and exercise failure cases."""

import base64
from collections import Counter, defaultdict
import hashlib
import itertools
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import publication  # noqa: E402


class PublishedTreeTests(unittest.TestCase):
    def test_every_secret_against_serialized_tree(self):
        """Walk the actual JSON, checking feedback edges, state contents and counts."""
        folder = ROOT / publication.SNAPSHOT
        tree = json.loads((folder / "strategy_tree.json").read_text(encoding="ascii"))
        summary = json.loads((folder / "summary.json").read_text(encoding="ascii"))
        expected = dict(line.split() for line in
                        (folder / publication.SOURCE_NAMES[2]).read_text(encoding="ascii").splitlines())
        nodes = tree["nodes"]
        codes = ["".join(p) for p in itertools.permutations("0123456789", 5)]
        self.assertEqual(tree["format"], "bac5-success-tree-v1")
        self.assertEqual(len(expected), 30240)
        self.assertEqual(set(expected), set(codes))
        self.assertEqual(tree["root"], 0)
        visits = defaultdict(list)
        leaves = set()
        successes, identifications = [], []
        for code_id, secret in enumerate(codes):
            node_id, depth, identified_at = tree["root"], 0, None
            while True:
                self.assertLessEqual(depth, 7, f"Non-terminating path: {secret}")
                node = nodes[node_id]
                self.assertEqual(node["id"], node_id)
                self.assertEqual(node["depth"], depth)
                if node["kind"] == "success":
                    self.assertEqual(node["secret"], secret)
                    self.assertNotIn(node_id, leaves)
                    leaves.add(node_id)
                    self.assertEqual(depth, int(expected[secret]))
                    self.assertEqual(node["identification_count"], identified_at)
                    successes.append(depth)
                    identifications.append(identified_at)
                    break
                self.assertEqual(node["kind"], "guess")
                visits[node_id].append(code_id)
                if node["candidate_count"] == 1 and identified_at is None:
                    identified_at = depth
                guess = node["guess"]
                self.assertEqual(len(guess), 5)
                self.assertEqual(len(set(guess)), 5)
                self.assertTrue(set(guess) <= set("0123456789"))
                exact = sum(secret[i] == guess[i] for i in range(5))
                shared = sum(digit in guess for digit in secret)
                matching = [branch for branch in node["branches"]
                            if branch["feedback"] == [exact, shared]]
                self.assertEqual(len(matching), 1)
                depth += 1
                if exact == 5:
                    identified_at = depth if identified_at is None else identified_at
                node_id = matching[0]["child"]
                self.assertTrue(0 <= node_id < len(nodes))
                self.assertEqual(nodes[node_id]["kind"] == "success", exact == 5)
        self.assertEqual(len(leaves), 30240)
        self.assertEqual(len(visits) + len(leaves), len(nodes))
        all_visited = set(visits) | leaves
        for node_id, candidates in visits.items():
            node = nodes[node_id]
            self.assertEqual(node["candidate_count"], len(candidates))
            bits = sum(1 << code_id for code_id in candidates).to_bytes(3780, "little")
            self.assertEqual(hashlib.sha256(bits).hexdigest(), node["state_sha256"])
            feedbacks = [tuple(branch["feedback"]) for branch in node["branches"]]
            self.assertEqual(feedbacks, sorted(set(feedbacks)))
            self.assertNotIn((4, 5), feedbacks)
            for branch in node["branches"]:
                self.assertIn(branch["child"], all_visited)
        for key, values in (("success", successes), ("identification", identifications)):
            self.assertEqual(sum(values), summary[key]["total"])
            self.assertEqual(max(values), summary[key]["maximum"])
            self.assertEqual({str(k): v for k, v in Counter(values).items()}, summary[key]["distribution"])
        self.assertEqual((max(successes), sum(successes), max(identifications)), (7, 171689, 6))

    def test_base85_decoder_rejects_invalid_records(self):
        bits = (3).to_bytes(3780, "little")
        record = bits + struct.pack(">HHB", 2, 0, 1)
        fixtures = {
            "truncated": b"BCS7SUM1" + struct.pack(">I", 1) + record[:-1],
            "duplicate": b"BCS7SUM1" + struct.pack(">I", 2) + record + record,
            "count": b"BCS7SUM1" + struct.pack(">I", 1) + bits + struct.pack(">HHB", 3, 0, 1),
            "tag": b"BCS7SUM1" + struct.pack(">I", 1) + bits + struct.pack(">HHB", 2, 0, 0),
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "corrupt.b85"
            for name, payload in fixtures.items():
                with self.subTest(name=name):
                    path.write_bytes(base64.b85encode(zlib.compress(payload)))
                    with self.assertRaises(publication.VerificationError):
                        publication.decode_strategy(path)

    def test_cli_rejects_changed_steps_and_tree(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = ROOT / publication.SNAPSHOT
            target = root / publication.SNAPSHOT
            shutil.copytree(source, target)
            for name, expected_error in (
                (publication.SOURCE_NAMES[2], "Published steps.txt differs"),
                ("strategy_tree.json", "Derived artifact differs"),
            ):
                with self.subTest(name=name):
                    path = target / name
                    original = path.read_bytes()
                    try:
                        path.write_bytes(original + b" ")
                        result = subprocess.run(
                            [sys.executable, "-B", str(ROOT / "publication.py"),
                             "verify", "--root", str(root)],
                            capture_output=True, text=True, timeout=180,
                        )
                        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                        self.assertIn(expected_error, result.stderr)
                    finally:
                        path.write_bytes(original)


if __name__ == "__main__":
    unittest.main()
