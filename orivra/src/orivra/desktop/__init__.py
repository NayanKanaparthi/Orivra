"""The Orivra desktop beta: the same product, installed as a Claude Desktop extension.

**An additional way to install, not a second product.** Everything that reads mail is
MailWeave's and Orivra's code, unchanged: `mailweave.surface.runtime.start` establishes the
credential, the granted scope and the account exactly as `orivra serve` does, and every
Orivra and MailWeave tool is dispatched to `orivra.surface.server.call`. What this package adds
is only what an installer needs and a command line did not:

  * **one setup tool**, `orivra_setup`, that walks a person through the steps the
    self-managed path runs by hand - connect Gmail through the beta's test OAuth application,
    download the locked models with visible progress, verify - by running the product's own
    commands, `mailweave auth login --events` and `mailweave setup-models --events`, as child
    processes;
  * **locations it owns** (`orivra.desktop.paths`), so the extension shares no credential,
    configuration or model directory with a self-managed install on the same machine;
  * **a bring-up that waits for setup** instead of refusing to start, because a desktop
    extension that exits at launch shows its user nothing but "disconnected".

What it deliberately does not do: open a browser (the person opens the link themselves, as
`mailweave auth login` requires), listen on a socket (the one-shot loopback listener belongs to
the `auth login` child, never to this server process), contact the model host (only the
`setup-models` child does), or write anything to disk (the children write the credential and
the models through the modules the source guards already allow to).
"""
