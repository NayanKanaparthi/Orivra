# Licensing scope and third-party notices

The MIT licence in `LICENSE` covers Orivra's and MailWeave's original software
and accompanying software documentation. It does not relicense third-party
components, downloaded models, or separately licensed assets.

The desktop extension includes CPython and third-party Python distributions.
Their licence and copyright notices remain with those components, including
the runtime's licence files and distribution metadata under
`server/python/lib/python3.12/site-packages/`. Each component's own terms apply;
the extension manifest's `MIT` identifier describes Orivra's software, not all
dependencies collectively.

Retrieval-model weights are downloaded separately during setup. `models.lock`
records their upstream sources, pinned revisions, and licences. Retain and
comply with the applicable upstream notices when redistributing those models.

The OAuth client configuration identifies a Google application. The software
licence grants no access to a Google account and no exemption from Google's
API or OAuth requirements. Users must authorize their own accounts.
