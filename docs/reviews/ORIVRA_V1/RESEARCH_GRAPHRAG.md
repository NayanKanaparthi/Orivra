# Research record: GraphRAG family, contextual retrieval, reranking (2026-09-10)

Primary sources only. Fetched and quoted by a research agent; nothing below is embellished.
Design implications are at the foot and are what `docs/ORIVRA_V1_PLAN.md` §0 relies on.

## 1. Microsoft LazyGraphRAG

Source: https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/
(Nov 2024). No arXiv paper exists; no GraphRAG docs page; maintainer statement 2024-12-09 that library
release is "the next top priority" (https://github.com/microsoft/graphrag/discussions/1490), nothing since.

Indexing vs query time. **LazyGraphRAG is not index-free.** Index = "NLP noun phrase extraction to
extract concepts and their co-occurrences" plus "graph statistics to optimize the concept graph and
extract hierarchical community structure" — a lightweight co-occurrence graph and a community
hierarchy are precomputed. What is deferred is the **LLM** work: "None – the 'lazy' approach defers
all LLM use until query time", meaning subquery expansion, sentence-level relevance assessment,
claim extraction and summarisation happen per query. Read as "no index" this source is misquoted;
read as "no LLM at index time" it is accurate.

Seeding: "Uses text chunk embeddings and chunk-community relationships to first rank text chunks by
similarity to the query, then rank communities by the rank of their top-k text chunks (best first)."
Then "an LLM-based sentence-level relevance assessor to rate the relevance of the top-k untested text
chunks from communities in rank order (breadth first)."

Bounding: "Recurses into relevant sub-communities after z successive communities yield zero relevant
text chunks (iterative deepening)." "Terminates when no relevant communities remain or relevance test
budget / q is reached." "single main parameter – the relevance test budget – that controls the
cost-quality trade-off." Budgets tested: 100, 500, 1,500.

Cost claims: "LazyGraphRAG data indexing costs are identical to vector RAG and 0.1% of the costs of full
GraphRAG." "For comparable query costs to vector RAG, LazyGraphRAG outperforms all competing methods on
local queries." No latency figures.

Benchmark conditions: "5,590 AP news articles"; "100 synthetic queries (50 local and 50 global)";
metrics comprehensiveness/diversity/empowerment by LLM pairwise judge. BenchmarkQED
(https://www.microsoft.com/en-us/research/blog/benchmarkqed-automated-benchmarking-of-rag-systems/):
data-local queries "benefit most from Vector RAG's ranking of directly relevant chunks".

## 2. Microsoft GraphRAG

Sources: https://arxiv.org/abs/2404.16130; https://microsoft.github.io/graphrag/index/default_dataflow/;
https://microsoft.github.io/graphrag/index/outputs/; https://microsoft.github.io/graphrag/query/overview/;
extraction prompts in the repo.

Pipeline: 600-token chunks (paper); LLM extracts entities and relationships for pairs "clearly related"
with "relationship_strength: a numeric score"; gleaning passes with logit-biased Y/N; hierarchical
Leiden; community reports. Entity matching is "exact string matching".

Index cost: "281 minutes for the Podcast dataset" (~1M tokens) on a 16 GB VM. Map contexts: "the
smallest context window size tested (8k) was universally better for all comparisons on
comprehensiveness (average win rate of 58.1%)".

Acknowledged limitations, verbatim: "Our evaluation to date has focused on sensemaking questions
specific to two corpora each containing approximately 1 million tokens. More work is needed to
understand how performance generalizes ... Comparison of fabrication rates ... would also strengthen
the current analysis." "vector RAG produces the most direct responses across all comparisons."

**On incremental update, state the narrow claim.** GraphRAG's output tables do carry fields used for
incremental update merges, so "no incremental-update story" overstates it and this record previously
did. The evidenced limitation is narrower: the published material does not establish the freshness
and permission behaviour Orivra requires — no per-item version verification, no handling of access
revocation, and no account of invalidating derived community summaries or extracted relations when a
source changes. That is a gap in what is documented for our purpose, not proof that no mechanism
exists.

Dynamic community selection (AP News): "average cost reduction of 77% over the existing static global
search at community level 1", "no statistical significance" in quality.

Independent: GraphRAG-Bench (https://arxiv.org/abs/2506.05690): "Basic RAG is comparable to or
outperforms GraphRAG in simple fact retrieval"; RAG+rerank 60.92% vs MS-GraphRAG 49.29% (novels);
MS-GraphRAG global ~4x10^4 tokens per query.

## 3. Observed vs inferred; claims tied to spans

GraphRAG claims (covariates) require Subject, Object, Claim Type, "Claim Status: TRUE, FALSE, or
SUSPECTED", dates, description, and "Claim Source Text: List of **all** quotes from the original text
that are relevant to the claim"; the table stores `source_text` and `text_unit_id`. Claims are "turned
off by default" because "claim prompts really need user tuning".

Absent: any GraphRAG-family primary source formally distinguishing observed from inferred relations
or calibrating `relationship_strength`; "clearly related" is undefined. LazyGraphRAG's noun-phrase
co-occurrence is the closest deterministic analogue to an observed edge. Provenance is text-unit
granularity, not span.

## 4. Anthropic

Contextual retrieval (https://www.anthropic.com/news/contextual-retrieval): 50–100-token context
prepended before embedding and BM25; rank fusion; optional rerank. Failure rate (1 − recall@20):
5.7% → 3.7% (contextual embeddings), → 2.9% (+ contextual BM25), → 1.9% (+ rerank top-150 → top-20).
Corpora: codebases, fiction, arXiv, science papers. Below ~200k tokens "just include the entire
knowledge base in the prompt". Performance varies by domain.

Context engineering (https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents):
"context rot"; "the smallest possible set of high-signal tokens"; just-in-time retrieval via
"lightweight identifiers"; "progressive disclosure"; sub-agents return "1,000–2,000 tokens".

## 5. Reranking

Nogueira & Cho (https://arxiv.org/abs/1901.04085): cross-encoder over BM25 top-1,000; 27% relative
MRR@10 improvement on MS MARCO. ColBERT (https://arxiv.org/abs/2004.12832): late interaction "two
orders-of-magnitude faster" than BERT rerankers. Cohere Rerank docs
(https://docs.cohere.com/docs/rerank-overview): scores 0–1, not linear; thresholds set on "30–50
representative queries".

## Implications used by the plan

Adopt: single relevance-test budget with LazyGraphRAG's termination; seed from hybrid retrieval;
covariate-style provenance (spans mandatory, string-match validated); claims only from
relevance-passed chunks; small extraction windows; distilled sub-agent output.

Adapt: metadata-native observed edges (reply, thread, revision, mention, link, share) replace noun-phrase
co-occurrence; observed/inferred namespaces replace TRUE/FALSE/SUSPECTED; thread/channel/folder as the
hierarchy with dynamic selection; one gleaning pass at query time; per-domain reranker thresholds.

Reject: persistent full GraphRAG index; LLM `strength` as confidence; entity-description summarisation
(breaks span provenance); static map-reduce over all communities.

Needs measurement here: everything. **Every number in this record is scoped to its dataset** — AP
news articles, podcast transcripts, Gutenberg novels, medical guidelines — with synthetic queries
and LLM judges scoring comprehensiveness, diversity and empowerment rather than accuracy. None of
it transfers to Orivra's short, multi-party, metadata-rich mail, chat and documents without being
measured here. Open specifically: latency of sequential relevance tests; whether contextual-retrieval
gains transfer; whether the graph helps cross-source questions (the Gmail-only result is not the
test); fabrication rate of query-time claims.
