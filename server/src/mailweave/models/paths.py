"""Where provisioned weights live, shared by the provisioner and the loader.

Its own module so that the server never imports `provision.py`. D.8 says
`mailweave setup-models` is the only code path that contacts the model host and that it is
never invoked from the server process; if the loader had to import the provisioner to learn
a directory name, "never invoked" would rest on nobody calling the function rather than on
the module not being there. The `no-model-host-at-runtime` guard holds the import rule.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

#: Cache-like data, deliberately not under the state directory: `mailweave purge` means
#: "delete my credentials and the watermark", not "delete a multi-gigabyte download".
DEFAULT_MODELS_DIR: Final[Path] = Path("~/.local/share/mailweave/models")


def model_dir(lock_key: str, revision: str, root: Path | str = DEFAULT_MODELS_DIR) -> Path:
    """One directory per **lock key and revision**, so nothing overwrites anything.

    The key is `<model>.<artifact set>`, not the repo id, because one repo yields more than
    one set: `bge-reranker-base` has a safetensors set for the Python arm and an ONNX set
    for PF-4b's, at the same revision. Keying by repo would put them in one directory, where
    the second pin's file list would silently coexist with the first's and neither lock would
    describe what is actually on disk.
    """
    return Path(root).expanduser() / lock_key.replace("/", "__") / revision
