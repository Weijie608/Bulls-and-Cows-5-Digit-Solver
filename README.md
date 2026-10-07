# A Seven-Guess Strategy for Five-Digit Bulls and Cows

A deterministic strategy for all **30,240 five-digit strings with distinct
digits**, including strings beginning with zero. Every secret is guessed
correctly within **7 guesses**. Under a uniform distribution of secrets, the
mean is **171689 / 30240 = 5.6775462963 guesses**.

This repository publishes the strategy, per-secret results, complete strategy
tree, and independent verification tools. It is a hobby project. The result is
a constructive upper bound; it does not prove that seven is the theoretical
minimum, that the average is globally optimal, or that every subtree is optimal.

## Try the games in your browser

Game interfaces are maintained in separate repositories. No installation is
needed to play either five-digit game.

| Mode | Link | What it demonstrates |
| --- | --- | --- |
| You guess | [Play Guess Five](https://weijie608.github.io/guess5-web/) · [source](https://github.com/Weijie608/guess5-web) | Five distinct digits; you guess the computer's secret. |
| Computer guesses | [Let the computer guess](https://weijie608.github.io/guess5-computer-web/) · [source](https://github.com/Weijie608/guess5-computer-web) | Keep a five-digit secret in mind and score the computer's guesses. The computer follows the strategy published here. |

The computer-guessing page ends and reveals the secret as soon as only one
candidate remains. Its result distinguishes the identification count from the
success count that includes a final exact guess when needed.

## Rules and what the counts mean

- A secret and every guess contain exactly five distinct digits from `0` to `9`.
  Leading zeroes are allowed: `01234` is valid.
- There are `10 × 9 × 8 × 7 × 6 = 30,240` possible secrets.
- A guess may be **any** of these strings, even one excluded as a possible secret.
- Feedback is `r` correct positions and `s` shared digits in total, **including**
  the digits counted by `r`. Conventional bulls/cows `(b, w)` therefore maps to
  `(r, s) = (b, b + w)`.
- **Success count:** guesses through the actual winning answer `5r5s`.
- **Identification count:** guesses until only one possible secret remains.
  If that guess did not win, guessing the known secret costs one more turn.

For this strategy, the maximum success count is **7** and the maximum
identification count is **6**. These are measured maxima for this particular
strategy, not lower bounds on all possible strategies. See
[Concepts and conventions](CONCEPTS.md) for precise definitions.

## Published result

The frozen snapshot is [`optimized_20260925_052028/`](optimized_20260925_052028/).
All 30,240 secrets are included; averages assume equal probability for every secret.

| Successful guesses | Number of secrets |
| ---: | ---: |
| 1 | 1 |
| 2 | 5 |
| 3 | 110 |
| 4 | 1,753 |
| 5 | 9,508 |
| 6 | 15,245 |
| 7 | 3,618 |
| **Total secrets** | **30,240** |

Total successful guesses: **171,689**. The exact mean is **171689/30240**.

| File | Purpose |
| --- | --- |
| [SQLite strategy](optimized_20260925_052028/guess5_optimized.sqlite3) | Candidate-set-to-guess decisions; 8,600 non-singleton records and all 30,240 singleton decisions. |
| [Base85 strategy export](optimized_20260925_052028/guess5_optimized.strategy.b85) | Compressed representation of the same 8,600 non-singleton decisions. Singleton decisions follow the rule “guess the sole candidate.” |
| [Per-secret results](optimized_20260925_052028/guess5_optimized_steps.txt) | One line per secret with its success count, in lexicographic order. |
| [Complete success tree](optimized_20260925_052028/strategy_tree.json) | Machine-readable tree with explicit final winning guesses and exactly 30,240 success leaves. |
| [Summary](optimized_20260925_052028/summary.json) | Exact totals, both count distributions, tree statistics and original artifact hashes. |
| [SHA256SUMS](optimized_20260925_052028/SHA256SUMS) | Byte-level hashes of the five data files above. |

The `.strategy.b85` file is encoded strategy data. It is not the source code of
the historical optimization search. The stored decisions define the reachable
strategy from the full universe, not a full strategy for arbitrary subsets.

## Verify everything

Requirements: **Python 3.10 or later**, standard library only. No package
installation, network connection, database server, or original development
repository is needed. From this repository's root, run:

```sh
python -B publication.py verify
```

Use `python3` or `py -3` instead of `python` if that is your Python command.
Verification is read-only. A successful run exits with code `0` and reports:

```json
{
  "status": "PASS",
  "operation": "verify",
  "secrets_verified": 30240,
  "maximum_success_count": 7,
  "total_success_count": 171689,
  "mean_success_count": 5.677546296296296,
  "maximum_identification_count": 6,
  "tree_nodes": 61102
}
```

The command first runs the original independent SQLite verifier. It then decodes
the Base85 export, compares every non-singleton decision with SQLite, and replays
all secrets using a separate feedback implementation. It regenerates the results,
tree, summary and checksums and compares them with the published files. Any
missing or inconsistent artifact causes a nonzero exit.

To verify just the original database:

```sh
python -B verify_strategy_db.py optimized_20260925_052028/guess5_optimized.sqlite3
```

To run the additional tree-replay and corruption-detection checks:

```sh
python -B -m unittest discover -s tests -v
```

The included [GitHub Actions workflow](.github/workflows/verify.yml) runs these
checks on pushes and pull requests. Its first remote run occurs after upload.

## Rebuild the derived data

```sh
python -B publication.py export --output rebuilt
```

This verifies the original artifacts and writes `strategy_tree.json`,
`summary.json` and `SHA256SUMS` into a separate directory. Output files must not
already exist. Repeated exports have identical bytes. The original strategy and
results are never rewritten. The command rebuilds the published representations;
it does not rerun the historical strategy search.

## Read further

- [Concepts and counting conventions](CONCEPTS.md)
- [File formats and tree traversal](FORMATS.md)
- [Provenance and prior work](PROVENANCE.md)
- [Changes in this publication](CHANGELOG.md)
- [Original development repository](https://github.com/Weijie608/Bulls-and-Cows)

No license has been selected for this publication yet.
