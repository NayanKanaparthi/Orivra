/**
 * PF-4b's Node arm: the reranker's wall clock on this machine, over the rows the Python arm
 * measured.
 *
 * WHAT THIS MEASURES, AND WHAT IT CANNOT
 * --------------------------------------
 * It measures stage B - the cross-encoder - because `models-catalog.json` pins a `node-onnx`
 * artifact set for `stage_b_default` (BAAI/bge-reranker-base) and for no other model.
 * `stage_a_default` (minishlab/potion-retrieval-32M) has no Node artifact set, so there is
 * nothing here to embed with. That is recorded in the result as
 * `stages_measured: ["rerank"]`, and `nodearm.comparison()` then reports R2 as *not
 * evaluable* rather than firing or not firing on half the question: R2 asks whether the Node
 * stack is materially faster at equal quality, and the cost the semantic rung is bounded by
 * at MAX_POOL_MESSAGES is stage A.
 *
 * It does not compare quality. Nothing here scores relevance; that is H1/H2/H3 on F1-F17.
 *
 * THE ROWS CROSS AS DATA
 * ----------------------
 * PF-4b's first registered rule is that both arms embed the same rows. This reads them from
 * the corpus file the Python side exported and reports that file's digest back, so "the same
 * rows" is checkable by `read_node_results` rather than asserted from a shared seed. This
 * script never generates a row.
 *
 * PREREQUISITES (all on the operator's machine, none of them in this repository)
 * ------------------------------------------------------------------------------
 *   * Node >= 20.
 *   * `npm install @huggingface/transformers` in this directory (or anywhere on NODE_PATH).
 *   * the stage_b `node-onnx` artifacts already on disk, from
 *     `mailweave setup-models` - this script sets `env.allowLocalModels = true` and
 *     `env.allowRemoteModels = false`, so it will fail rather than download anything.
 *
 * USAGE
 * -----
 *   python -m mailweave_harness.modelbench --export-node-corpus corpus.json
 *   node harness/node/pf4b-arm.mjs --corpus corpus.json \
 *        --model-dir <models dir>/BAAI/bge-reranker-base --out node-arm.json
 *   python -m mailweave_harness.modelbench --node-results node-arm.json --corpus corpus.json
 */

import { readFileSync, writeFileSync } from "node:fs";
import { argv, hrtime, versions } from "node:process";

function arg(name, fallback = null) {
  const at = argv.indexOf(`--${name}`);
  if (at === -1 || at === argv.length - 1) {
    if (fallback === null) {
      throw new Error(`missing required --${name}`);
    }
    return fallback;
  }
  return argv[at + 1];
}

const corpusPath = arg("corpus");
const modelDir = arg("model-dir");
const outPath = arg("out", "node-arm.json");

const corpus = JSON.parse(readFileSync(corpusPath, "utf-8"));
if (corpus.schema !== 1) {
  throw new Error(`corpus schema ${corpus.schema} is not the schema this arm reads (1)`);
}

// Local only, and stated rather than assumed: a silent download would make this a
// measurement of somebody's network.
const transformers = await import("@huggingface/transformers");
transformers.env.allowLocalModels = true;
transformers.env.allowRemoteModels = false;

const millis = (started) => Number(hrtime.bigint() - started) / 1e6;

// Cold acquire, then a second acquire in the same process. The pair is the reuse question
// PF-4 asks of the Python arm, asked here in the same shape so the two records compare.
let started = hrtime.bigint();
const cold = await transformers.AutoModelForSequenceClassification.from_pretrained(modelDir);
const tokenizer = await transformers.AutoTokenizer.from_pretrained(modelDir);
const coldAcquireMs = Math.round(millis(started));

started = hrtime.bigint();
await transformers.AutoModelForSequenceClassification.from_pretrained(modelDir);
const warmAcquireMs = Math.round(millis(started));

const query = corpus.rerank_query;
const candidates = corpus.rerank_candidates;
const repeats = corpus.repeats;

async function scoreOnce(pairs) {
  const inputs = tokenizer(new Array(pairs.length).fill(query), {
    text_pair: pairs,
    padding: true,
    truncation: true,
  });
  const output = await cold(inputs);
  return output.logits.data.length;
}

const median = (values) => {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : Math.round((sorted[mid - 1] + sorted[mid]) / 2);
};

// One discarded warm-up before every timed size, for the reason PF-4's spec gives: run 1
// timed each size once, ascending, and produced a rerank curve that FELL as the work grew.
const rerankMsByPairs = {};
for (const size of corpus.rerank_sizes) {
  const pairs = candidates.slice(0, size);
  await scoreOnce(pairs);
  const samples = [];
  for (let index = 0; index < repeats; index += 1) {
    const at = hrtime.bigint();
    await scoreOnce(pairs);
    samples.push(millis(at));
  }
  rerankMsByPairs[String(size)] = median(samples.map(Math.round));
}

const results = {
  corpus_digest: corpus.digest,
  stages_measured: ["rerank"],
  runtime_versions: {
    node: versions.node,
    v8: versions.v8,
    "@huggingface/transformers": transformers.env.version ?? "unknown",
  },
  // What the runtime actually loaded onto, not what was asked for.
  device: cold?.config?.device ?? transformers.env.backends?.onnx?.device ?? "cpu",
  cold_acquire_ms: coldAcquireMs,
  warm_acquire_ms: warmAcquireMs,
  rerank_ms_by_pairs: rerankMsByPairs,
  repeats_per_size: repeats,
  embedding_dimension: 0,
};

writeFileSync(outPath, `${JSON.stringify(results, null, 2)}\n`, "utf-8");
console.log(`wrote ${outPath}`);
console.log(
  "stage A was not measured: models-catalog.json pins a node-onnx artifact set for " +
    "stage_b_default only, so R2 is reported as not evaluable rather than decided on the " +
    "reranker alone.",
);
