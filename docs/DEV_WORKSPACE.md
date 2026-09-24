# The test workspace, and why it is not the development VM

*2026-09-18. Written after a `git show` redirect truncated `server/.../assemble.py` to zero
bytes because the disk filled mid-write.*

## The constraint, measured

The desktop Cowork VM mounts the repo at `~/mnt/MailWeave` on a **9.8 GB volume shared with
other sessions**:

| | |
|---|---|
| Volume | 9.8 GB total, ~0.5 GB reserved |
| Visible to this session | 4.4 GB — the 1.7 GB repo mount, ~2.3 GB of prior sessions' paired-measurement working trees, 186 MB venv, 98 MB `.local` |
| Not visible, not ours | ~4.9 GB in other `/sessions/*` directories |
| Free | **~545 MB** |

No deleted-but-open files hold anything; `du` and `df` differ only by what other sessions own.

Two consequences, both observed rather than predicted:

* **pytest temp directories cannot be unlinked inside the mount**, so they accumulate at
  ~500 MB per full cycle and have to be cleared by hand between runs. On a 545 MB headroom
  that is one run's worth of slack.
* **A write that runs out of space truncates the target.** `git show HEAD:path > path` opened
  the file (truncating it), then failed to write. The file was recovered from the checkpoint
  commit and the change re-applied, but the lesson stands: never redirect into a tracked file
  on this VM.

Freeing real headroom would mean deleting the prior sessions' trees. Those are other work's
records and are **not** ours to remove.

## The workspace

Tests run in the **cloud container**, which is isolated, disposable, and has 27 GB free on a
252 GB volume. The repo is the source of truth on the Mac; the container holds a copy that is
thrown away.

```
# on the Mac, in the repo
python tools/dev/export_tree.py --out _to_delete/export --label <sha>
# stage the archive and the manifest to the container, then:
tar xzf .../tree-<sha>.tar.gz -C tree
python tree/tools/dev/export_tree.py --verify tree --manifest tree-<sha>.manifest.json
uv venv --python /usr/bin/python3.12 venv
uv pip install --python ./venv/bin/python pytest hypothesis jsonschema pytest-timeout \
    "mcp==2.1.1" "pydantic>=2.9,<3" "httpx>=0.27,<0.29" "selectolax>=0.3.21" "lxml>=5.2"
PYTHONPATH=server/src:harness/src:orivra/src:tests/fixtures:. ./venv/bin/python -m pytest tests/
```

### Why not `git archive`

The first version of this used `git archive HEAD`, and **that silently exports the wrong
thing**. It carries tracked files at the last commit, so an uncommitted edit, a staged-but-not
-committed change, and - worst - a brand new test file that has not been `git add`-ed are all
absent, with nothing saying so. The runner then passes, and what it passed on is not what is
being claimed.

`tools/dev/export_tree.py` exports the **working tree** (`git ls-files -co
--exclude-standard`, so untracked-and-not-ignored files are included), writes a manifest with
a sha256 per file, and `--verify` refuses unless the extracted copy matches path for path and
byte for byte, in both directions: a missing file is an incomplete export and an extra one is
an export carrying something the manifest does not describe.

It is **scoped**, because the unscoped working tree is 181MB - nearly all of it
`marketing/`, review snapshots and benchmark output. The scope is recorded in the manifest,
which is the difference between narrowing an export and narrowing one silently.

Recording it was not enough. The first scope was `server/ harness/ orivra/ tests/ tools/` plus
the build config, and three tests failed in the runner because they read
`docs/ARCHITECTURE_DECISION.md` as a contract oracle - a failure that had nothing to do with
the code, which is worse than a gap because it is a false signal that costs an investigation.

So the exporter now **refuses a scope the tests would outgrow**: it extracts every repository
path literal the test tree mentions, and exits rather than writing an archive that omits one.
The check is derived from the tests rather than declared beside them, because a declared list
is one more thing to keep in step with what it describes. `--whole-tree` exports everything.

The credential check is by name in the exporter as well as by `.gitignore`, because being
gitignored is a fact about a config file and this needs to be a property of the artefact.

Three properties worth stating, because they are what make this safe rather than merely
convenient:

* **One-way.** The container copy is never edited and never committed from. Edits and commits
  happen on the Mac. There is nothing to drift.
* **Tracked files only.** `git archive` carries what git carries, so neither OAuth credential
  can ride along — verified on each export by grepping the archive listing. It is 3.9 MB
  against the working tree's 1.6 GB, which is `.git` history and benchmark output.
* **Verified, not assumed.** At `f2fbb5e` the container verified the export against its
  manifest (617 files, every digest matching) and then ran the Orivra, graph and M2 suites,
  reproducing the Mac's results exactly. Python 3.12 on both; the repo
  requires `>=3.12` and the container's default `python3` is 3.11, so the venv pins it.

## What still cannot run anywhere

`tests/test_new_operator_round19.py` (2 tests) copies the **whole repository** into a tmpdir.
That needs ~1.6 GB and fails on the VM with `No space left on device`. It would run in the
container against a full clone, which the `git archive` export is deliberately not. Recorded
rather than worked around.

## If you want the VM fixed instead

The exact requirement: **the desktop workspace volume needs ~10 GB of free space for this
repository**, or those prior-session trees under `~/` on the VM need an owner's decision to
remove. Neither is something a session should decide on its own.
