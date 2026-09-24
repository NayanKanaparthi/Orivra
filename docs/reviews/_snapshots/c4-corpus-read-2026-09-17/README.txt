C4 corpus read, 2026-09-17. Evidence scripts, stored as .py.txt so no lint or test gate collects them.
Isolated run: copy server/ harness/ orivra/ tests/ tools/ docs/ pyproject.toml uv.lock to a scratch dir,
`uv sync --frozen --no-dev`, export PYTHONPATH=server/src:harness/src:orivra/src:tests/fixtures:.
then `python tools/gate/freeze_corpus.py --check <repo>/benchmarks/gate/corpus-freeze-round2.json`
and `python tools/gate/export_review.py --seed 4311 --profile sample --out review/sample-4311`.
Gate manifest: python -c "from mailweave_harness.seed.corpus import generate; open('work/gate-5309.json','w').write(generate(master_seed=5309,size_profile='gate').model_dump_json())"
(sha256 of that JSON must be e2e3b885...d109d, the freeze record's manifest_sha256).
Scripts take the manifest path as argv[1] where applicable; run from the scratch root with work/ holding them renamed to .py.
The inline probes quoted in the report (cross-seed layout identity, cross-seed position lookup, F13/F16/F17 bypass,
F7 same-entity decisions, F8 markers, undecided-after-evidence, nearest-length) are reproduced verbatim in the report's appendix.
