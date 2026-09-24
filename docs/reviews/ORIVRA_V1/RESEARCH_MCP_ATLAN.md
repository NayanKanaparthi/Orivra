# Research record: MCP resources vs tools, and Atlan as a lineage reference (2026-09-10)

Primary sources: modelcontextprotocol.io specification pages and repo, Anthropic docs, Atlan docs and SDK.

## MCP

Current revision 2026-07-28 (https://modelcontextprotocol.io/specification/versioning). Changelog
(https://modelcontextprotocol.io/specification/2026-07-28/changelog): "Make MCP stateless: remove the
`initialize`/`notifications/initialized` handshake"; "Add `server/discover`: servers MUST implement this
RPC"; "Replace ... `resources/subscribe`/`resources/unsubscribe` with `subscriptions/listen`"; "Require
`ttlMs` and `cacheScope` fields on results".

Resources (https://modelcontextprotocol.io/specification/2026-07-28/server/resources): `resources/list`,
`resources/read` returning `contents[]` of `{uri, mimeType?, text | blob}`; templates via RFC 6570;
annotations `audience`, `priority`, `lastModified`, `size`. Custom URI schemes "MUST be in accordance
with RFC3986"; `file://` resources "do not need to map to an actual physical filesystem".

Control table (https://modelcontextprotocol.io/specification/2026-07-28/server): Resources are
"Application-controlled: Contextual data attached and managed by the client"; Tools are
"Model-controlled: Functions exposed to the LLM to take actions". "Resources in MCP are designed to be
**application-driven** ... the protocol itself does not mandate any specific user interaction model."

Tool results (https://modelcontextprotocol.io/specification/2026-07-28/server/tools): `resource_link`
("not guaranteed to appear in the results of a `resources/list` request"); embedded `resource`;
`structuredContent` conforming to `outputSchema`, with the serialised JSON "SHOULD" also be in a text
block. Annotations `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint` are hints;
Anthropic's review criteria (https://claude.com/docs/connectors/building/review-criteria.md): "read-only
tools can run without per-call confirmation; destructive tools always prompt"; names ≤ 64 characters.

Client support: Claude.ai/Desktop (https://claude.com/docs/connectors/building): "Supported: Tools,
prompts, and resources"; "Not yet supported: Resource subscriptions · Sampling"; auth specs 2025-03-26,
2025-06-18, 2025-11-25 (no 2026-07-28); max tool result ~150,000 characters; how resources reach the
model is UNDOCUMENTED. Claude Code (https://code.claude.com/docs/en/mcp): v2 runtime on SDK 2.0 adds
2026-07-28; model-callable `ListMcpResourcesTool`/`ReadMcpResourceTool`/`ReadMcpResourceDirTool`
observed; `resources/directory/read` is not in the 2026-07-28 or draft spec (UNCONFIRMED as standard).
Messages API connector (https://platform.claude.com/docs/en/agents-and-tools/mcp-connector): "only tool
calls are currently supported".

`_meta` (https://modelcontextprotocol.io/specification/2026-07-28/basic/index): reverse-DNS prefixes;
requests carry `io.modelcontextprotocol/protocolVersion` and `clientCapabilities`. Stateful tools
guidance: "Handles that encode internal structure invite parsing or guessing; opaque identifiers do
not"; state spanning requests "MUST be referenced by an explicit identifier the client passes on each
request".

## Atlan (design reference only)

Store: "hardened fork of Apache Atlas" (https://atlan.com/atlan-vs-apache-atlas/), graph layer plus
Elasticsearch and Cassandra. Typedefs with attributes, relationships, supertypes
(https://docs.atlan.com/product/capabilities/build-apps/sdks/application-sdk/concepts/typedefs). Lineage
"by combining assets and processes"; a `Process` entity with `inputs`/`outputs` and deterministic
`process_id` (https://docs.atlan.com/product/capabilities/lineage/concepts/what-is-lineage). Sources of
lineage: SQL parsing, API crawling, OpenLineage ingestion, user-declared CSV, pattern-matched
"Lineage Generator" with preview. Provenance attributes rather than a first-class observed/inferred
flag: `connectorName`, `lastSyncWorkflowName`, `lastSyncRunAt`, `isPartial` ("not fully-known",
"dotted border"), `isAIGenerated`. Audit via a dedicated log. UNCONFIRMED: any first-class
observed/declared/inferred label.

## Implications used by the plan

Direct tools are the only surface documented to work on every Claude client; resources are additive and
must be readable through a tool as well; nothing may depend on subscriptions; `query_id` opaque and
passed explicitly; `readOnlyHint: true` on every tool; target 2026-07-28 for Claude Code and keep the
handshake path for Claude.ai/Desktop. From Atlan: a deterministic process/edge identity, an
`isPartial`-style partiality flag on nodes, and provenance carried as explicit attributes, which
Orivra strengthens into a closed observed/inferred namespace split.
