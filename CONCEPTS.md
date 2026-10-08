# Guess5 Concepts and Conventions

[Back to the project README](README.md)

This document defines the mathematical objects and counting conventions used in
Guess5. It distinguishes the research objective from the guarantees provided by
the currently retained strategies and scripts.

## 1. Codes, the universe, and guesses

A **code** is a length-five string of distinct digits from `0` through `9`.
Leading zeroes are allowed. The **universe**, or initial candidate set, is

$$
U = \{x \in \{0,\ldots,9\}^{5} : x_i \ne x_j\text{ whenever }i\ne j\},
\qquad |U| = 10\cdot9\cdot8\cdot7\cdot6 = 30{,}240.
$$

A candidate set is any subset $S\subseteq U$. A secret is one element of the
current non-empty candidate set. A **guess** is any $g\in U$: it need not belong
to $S$. A guess excluded as a possible secret may still distinguish the remaining
candidates efficiently.

## 2. Feedback, filtering, and partitions

For secret $x$ and guess $g$, let $F(x,g)=(r,s)$, where

- $r$ is the number of positions in which $x$ and $g$ agree;
- $s$ is the number of digits shared by the two codes, including correct-position
  matches.

For example, secret `01234` and guess `01567` produce `2r2s`. The second number
is the total shared-digit count, not the count of misplaced digits. The answer
`5r5s` occurs exactly when $x=g$.

There are 21 formal answer pairs:

$$
A = \{(r,s): r,s\in\mathbb{Z},\ 0\le r\le s\le5\}.
$$

The pair `4r5s` is impossible: if the codes contain the same five digits and four
positions agree, the fifth position must agree as well. Thus only 20 answer types
can actually occur, and a particular state and guess may allow fewer.

Given a set $S$, a guess $g$, and an answer $a$, **filtering** produces

$$
S_{g,a}=\{x\in S:F(x,g)=a\}.
$$

This is the **legal candidate set** after the answer; $S\setminus S_{g,a}$ is
excluded by that observation. A filter can leave the entire set unchanged or
produce the empty set. In a valid game with a fixed secret and truthful feedback,
the actual answer always selects a non-empty set containing that secret.

For a fixed guess, the 21 answer-indexed buckets satisfy

$$
S=\bigcup_{a\in A}S_{g,a},
\qquad S_{g,a}\cap S_{g,b}=\varnothing\quad(a\ne b).
$$

We call this the **partition induced by the guess**, allowing empty buckets in
the answer-indexed representation. In the strict set-theoretic definition of a
partition, empty buckets are omitted. Different guesses need not induce distinct
partitions; equivalent partitions are possible.

## 3. Strategy functions and full strategy functions

A deterministic **full strategy function** chooses one guess for every candidate
set:

$$
f:\mathcal{P}(U)\longrightarrow U.
$$

There are $2^{30{,}240}$ possible subsets in its domain. Its output is a single
code, not another candidate set. The value at the empty set is irrelevant to a
valid game and can be left as an arbitrary formal convention. For strict success,
the natural singleton rule is $f(\{x\})=x$.

Starting from $U$, fixing $f$ and the secret fixes the entire sequence of guesses
and feedback. Usually, only a small fraction of the full function's domain is
visited across the 30,240 possible secrets.

A **strategy function**, in this project's narrower terminology, is the
restriction to the candidate sets actually needed by those runs. It specifies a
complete strategy for games starting from $U$ without specifying what to do at
every arbitrary subset. Correspondingly, a local strategy stores the decisions
reachable from a specified starting set $S$.

The published database is a stored strategy function in this sense. It contains
reachable non-singleton decisions and also all singleton decisions. Its missing
entries do not define a fallback policy for arbitrary subsets. A complete
strategy from $U$ is sufficient to establish the claimed bound on games starting
from $U$; decisions on every arbitrary subset are unnecessary for that claim.

An arbitrary function is not automatically a terminating strategy. For example,
repeating a guess whose answer leaves $S$ unchanged gives no progress. The finite
trees discussed below assume a terminating policy. The included database verifier
requires every non-singleton decision to split its set into strictly smaller
non-empty children.

## 4. Strategy trees and local strategy trees

For a fixed strategy, its **identification tree** has:

- root $U$ at depth 0;
- an internal node for each reached set with more than one candidate;
- the guess selected by the strategy at each internal node;
- outgoing edges labeled by feedback, leading to the corresponding filtered sets;
- a leaf when the candidate set is a singleton.

An edge can equivalently be labeled by both the node's guess and its answer.
Empty buckets may be drawn as impossible leaves or omitted entirely. They never
represent an actual secret.

A complete, terminating tree starting at $U$ has exactly **30,240 non-empty
singleton leaves**, one per secret. If empty buckets are also drawn, the total
number of leaves is larger; the number 30,240 counts only the non-empty leaves.

A **local strategy tree** starts from some non-empty $S\subseteq U$. If $S$ is
reached in the global tree, this is its continuation subtree. A full strategy can
also define a local tree for a set never reached from $U$. A stored partial
strategy may not contain the decisions needed for such a set.

The identification tree stops once the secret is known. A tree that explicitly
records strict success additionally includes a final guess at any singleton
reached through a non-winning answer.

## 5. Identification counts and success counts

For secret $x$, distinguish:

- **Identification count** $D_f(x)$: the depth of its non-empty leaf in the
  identification tree. This corresponds to the project's term "guess count"
  when discussing tree height.
- **Success count** $T_f(x)$: the number of guesses, starting with the first,
  through the guess that receives `5r5s`.

For a strategy that immediately guesses the sole candidate when necessary,

$$
T_f(x)=
\begin{cases}
D_f(x), & \text{if the answer reaching the singleton was }5r5s,\\
D_f(x)+1, & \text{otherwise}.
\end{cases}
$$

For a local game that starts with a singleton, these counts are 0 and 1,
respectively. An already completed game after `5r5s` requires no further guess.

For example, let $S=\{12345,12346,12347\}$ and guess `12346`. The answer `5r5s`
identifies `12346` and succeeds immediately. The answer `4r4s` instead leaves
$\{12345,12347\}$. If the next guess is `12345` and again receives `4r4s`, the
secret is now known to be `12347`: identification has taken two guesses, while
strict success requires a third guess, `12347`.

The global **maximum identification count** is the height of the identification
tree, counting only non-empty leaves. The **maximum success count** is
$\max_{x\in U}T_f(x)$. These maxima can differ by one.

The per-secret `_steps.txt` file reports **success counts**, including any
required final singleton guess. The summary labels the two counts separately.
For a uniform secret,

$$
\text{total} = \sum_{x\in U}T_f(x),
\qquad
\text{mean} = \frac{1}{30{,}240}\sum_{x\in U}T_f(x).
$$

The published success tree explicitly includes the final singleton guess when
required. Its success leaves are reached only through `5r5s`. The accompanying
summary records identification and success statistics separately.

## 6. The optimality objective

For a non-empty set $S$, let $H_f(S)$ be the maximum number of **additional**
guesses needed for strict success when starting from $S$ under strategy $f$.
Local counts start at that state; they do not include guesses already made on
the path from the global root.

The optimal worst-case value is

$$
H^*(S)=\min_f H_f(S).
$$

An **optimal strategy** from $U$ first attains $H^*(S)$ at the root and at
**every reached non-empty continuation state**. Among all strategies satisfying
all of these worst-case minima, it minimizes the uniform mean success count
from $U$. An **optimal local strategy** applies the same two requirements to a
specified starting set and all its reached continuations. Average counts use
equal weight for each possible secret in the starting set.

An **optimal full strategy** applies this local rule to every non-empty
candidate set, including sets not reached from $U$. More than one strategy may
attain both objectives. Choosing the lexicographically smallest guess among
remaining ties makes an implementation deterministic; uniqueness is not part
of the definition.

Merely minimizing the root maximum and then the root mean is a weaker
requirement: a continuation with a worse local maximum may still fit within
the root's depth limit. Under the definition above, an improvement in the mean
cannot justify increasing any reached state's maximum above its own $H^*(S)$.
Likewise, minimizing the mean before the maximum is a different objective.

### A recurrence for the worst-case value

A singleton needs one guess, so $H^*(\{x\})=1$. For non-empty $S$, define the
remaining cost after observing an answer as

$$
R(S,g,a)=
\begin{cases}
0, & a=(5,5),\\
H^*(S_{g,a}), & a\ne(5,5),\ S_{g,a}\ne\varnothing.
\end{cases}
$$

Then

$$
H^*(S)=1+\min_{g\in G(S)}\max_{a\in A:\,S_{g,a}\ne\varnothing}R(S,g,a),
$$

where $G(S)\subseteq U$ contains the guesses for which every non-empty,
non-winning bucket is a proper subset of $S$. A guess with an unchanged
non-winning state costs a guess without reducing uncertainty and can be excluded
from an optimal terminating strategy. The restriction does **not** require the
guess to be in $S$.

The initial `1` counts the current guess. A winning answer contributes no future
cost; a non-winning singleton contributes one more guess. Empty answer buckets
are omitted from the maximum. One may define $H^*(\varnothing)=0$ for bookkeeping,
but an empty set is not a playable state.

This recurrence concerns eventual strict-success depth. Minimizing the largest
bucket or the variance of bucket sizes is a heuristic for choosing a partition,
not an equivalent definition of $H^*$.

### Minimum mean subject to every state's optimal worst case

Retain only guesses attaining the worst-case minimum:

$$
G_H(S)=\left\{g\in G(S):
1+\max_{a\in A:\,S_{g,a}\ne\varnothing}R(S,g,a)=H^*(S)\right\}.
$$

Let $C^*(S)$ be the minimum total additional success count among strategies
that attain $H^*$ at $S$ and at every reached continuation. Then

$$
C^*(S)=|S|+\min_{g\in G_H(S)}
\sum_{\substack{a\in A,\ a\ne(5,5)\\S_{g,a}\ne\varnothing}}C^*(S_{g,a}),
\qquad C^*(\{x\})=1.
$$

The corresponding minimum uniform mean is $C^*(S)/|S|$. The term $|S|$ charges
the current guess once to every possible secret. A winning bucket has no
continuation cost; a non-winning singleton still contributes one more guess.
One may set $C^*(\varnothing)=0$ for bookkeeping.

Every child uses the same two-stage rule recursively. If a reached child had
a smaller total within this class, replacing its continuation would preserve
all worst-case minima and reduce the parent's total. Thus the secondary
optimum also holds at each reached state. This is stronger than optimizing the
mean subject only to a depth limit at the root.

## 7. How this publication relates to the objective

The published strategy achieves maximum success count 7 and maximum
identification count 6. It provides the constructive bound $H^*(U)\le7$.
Its measured results alone do not establish $H^*(U)=7$, global mean optimality,
or optimality of every continuation. Its total success count is 171,689, giving
the uniform mean $171689/30240$.

`verify_strategy_db.py` establishes that the stored database is internally
consistent, covers all secrets, and reproduces its declared success results.
`publication.py verify` also compares the Base85 representation with the
database, independently reconstructs its success tree and both count
distributions, and checks the published artifacts. These tools do not compare
the strategy against every possible alternative.

## 8. Stored strategy representation

The canonical codebook is the lexicographic sequence generated by
`itertools.permutations("0123456789", 5)`. Codes are indexed from 0 to 30,239.
The same ordering is used by the databases and result files.

A candidate set is represented by a 30,240-bit bitset, or 3,780 bytes. Code ID
`i` occupies bit `i % 8` of byte `i // 8`, with the least significant bit first.
Each compact database has a `strategy` table with these columns:

| Column | Meaning |
| --- | --- |
| `state_hash` | SHA-256 of the uncompressed candidate bitset, stored as 32 bytes. |
| `candidate_bits_z` | The bitset compressed with zlib. |
| `candidate_count` | Number of set bits, equal to the candidate-set size. |
| `guess_id` | The selected guess's index in the canonical codebook. |

The separate `metadata` table contains exactly these keys:

- `codebook_sha256`: hash of the canonical ASCII code list, one code per line.
- `step_distribution`: counts of secrets by strict-success step.
- `results_sha256`: hash of the canonical per-secret results.
- `record_count`: number of strategy records.
- `created_utc`: creation timestamp.

The canonical results used for hashing contain one ASCII line per codebook
entry, in order, with exactly one space and an LF newline:

```text
<secret> <success_count>\n
```

Here `\n` denotes a newline byte, not two literal characters. Directory and file
names label the snapshot; the compact metadata does not contain a policy-name
field. See [File formats](FORMATS.md) for the Base85 payload, the explicit
success-tree representation, the summary and the checksum manifest.
