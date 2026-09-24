# Research record: Gmail, Drive v3 and Slack change, revision and permission mechanisms (2026-09-10)

Primary documentation only. UNCONFIRMED marks anything a primary page did not state.

## Gmail

`users.history.list` (https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.history/list,
https://developers.google.com/workspace/gmail/api/guides/sync): historyTypes `messageAdded`,
`messageDeleted`, `labelAdded`, `labelRemoved`. "A `historyId` is typically valid for at least a week,
but in some rare circumstances may be valid for only a few hours. If you receive an `HTTP 404` error
response, your application should perform a full sync." No hard retention guarantee. `maxResults`
max 500. Initial id from `users.getProfile`. Push `watch` renews every 7 days and carries no delta.

Change vs delete vs trash: message `id` is immutable; only label operations mutate an existing message;
`messagesDeleted` is permanent, `labelsAdded: [TRASH]` is trashed and still fetchable. No API alters
body or headers (content immutability implied by the surface; UNCONFIRMED as a verbatim statement).

Quota (https://developers.google.com/workspace/gmail/api/reference/quota): `history.list` 2 units,
`messages.get` 20, `messages.list` 5, `getProfile` 1, `threads.get` 40; 6,000 units/min/user/project.

## Google Drive v3

`changes` (https://developers.google.com/workspace/drive/api/reference/rest/v3/changes/list): record has
`changeType`, `fileId`, `time`, `driveId`, `removed`, `file`, `drive`. `removed`: "Whether the file or
shared drive has been removed from this list of changes, for example by deletion or loss of access."
`startPageToken`/`newStartPageToken`: "The page token doesn't expire." Shared drives: per-`driveId`
tokens or `includeItemsFromAllDrives=true`. `restrictToMyDrive=true` omits shared files not added to My
Drive.

Revisions: `headRevisionId` "only available for files with binary content"; `version` "A monotonically
increasing version number for the file. This reflects every change made to the file on the server";
`revisions.list` "might be incomplete"; binary revisions purge after ~30 days or 100 revisions unless
keepForever; Docs revisions via `exportLinks`.

Permissions: inherited from folders, "cannot be removed or reduced on any item"; `permissionDetails[]`
with `inherited`; `File.permissions` visible "only if the requesting user can share the file"; current
user's access via `files.get?fields=capabilities`. Loss of access: `changes.list` emits `removed: true`
(deletion or loss, undistinguished); `files.get` returns 404 `notFound` in both cases ("This error occurs
when the user doesn't have read access to a file, or the file doesn't exist").

Scopes: `drive.readonly` (restricted) allows content; `drive.metadata.readonly` (restricted) allows
`changes.list`, `files.get` metadata, `permissions.list`, `revisions.list` but not export or download.

## Slack

`conversations.history`/`replies` (https://docs.slack.dev/reference/methods/conversations.history/,
https://docs.slack.dev/reference/methods/conversations.replies/): Tier 3; `limit` max 999 / 1000 (15
for restricted unlisted apps); "The `ts` value is essentially the ID of the message, guaranteed unique
within the context of a channel"; parent `thread_ts == ts`; "A parent message object will retain a
`thread_ts` value, even if all its replies have been deleted." Cursors: "do not persist cursors for
hours or days."

Edited when reading: "it will include an `edited` property, which includes the user ID of the editor
and the timestamp" (https://docs.slack.dev/reference/events/message/). Deleted: "The original message
will no longer return in history calls" (https://docs.slack.dev/reference/events/message/message_deleted/).
Deleting a thread parent leaves "a placeholder informing viewers about the deleted message". The
`tombstone` subtype page 404s (UNCONFIRMED).

Events (https://docs.slack.dev/apis/events-api/): `message_changed`, `message_deleted`,
`member_left_channel`, `channel_left`, `channel_deleted`, `channel_history_changed` ("Bulk updates were
made to a channel's history"); delivery "at least once", may be out of order. Without events, edits and
deletes are detectable only by re-reading the same window and diffing.

Rate limits (https://docs.slack.dev/changelog/2025/05/29/rate-limit-changes-for-non-marketplace-apps/,
https://docs.slack.dev/changelog/2025/06/03/rate-limits-clarity/): for "applications that are
commercially distributed outside of the Marketplace (also called 'unlisted' apps)" created or installed
after 2025-05-29, `conversations.history` and `replies` are "1 request per minute" with "a maximum of 15
objects per request"; existing installs, Marketplace apps and "internal customer-built apps" keep Tier 3.

Scopes, corrected and complete for Orivra's needs: `channels:history`, `groups:history`,
`im:history`, `mpim:history` for history per conversation type; **`search:read`, which
`search.messages` requires** and which the first draft of this record omitted; `users:read` to
resolve user ids; **`users:read.email` to read a profile email**, which is the only deterministic
key that links a Slack user to a Gmail address — without it, Gmail and Slack identities must stay
separate and only an entity candidate may be exposed. Bot tokens see only channels the bot is in;
user tokens see what the user sees. Free plan (Help Center): messages past 90 days hidden, past one
year deleted.

**Search surface is not guaranteed.** `search.messages` is documented as a legacy API and Slack
recommends `assistant.search.context`, whose availability may be restricted by workspace or app
type. An adapter must preflight which surface the authorised installation can actually use and
degrade honestly when it is neither.

**Rate tier depends on the distribution path and must not be assumed.** Three distinct cases:
development or internal installation in the developer's own workspace; Slack Marketplace
distribution; and commercially distributed non-Marketplace installation, where
`conversations.history`/`replies` fall to 1 request per minute and 15 objects for apps created or
installed after 2025-05-29. A user-installed app is **not** automatically an "internal
customer-built app". The adapter must detect the tier it actually receives, report it, and declare
what it could not inspect.

## Constraints the invalidation design must respect

Gmail: history is best-effort; 404 forces full resync; content immutable, labels mutable; store the
historyId from the last processed page; push carries no delta.
Drive: tokens never expire; `removed: true` = gone or access lost, both mean do not serve; `version`
is the freshness key for all types; revision content is not reliably retrievable; effective access
only via `capabilities`; folder ACL changes re-scope descendants silently, the change feed is the only
signal.
Slack: no retention guarantee; `ts` is identity, `edited.ts` is version; deletes are absences on
re-read; events are at-least-once and unordered; membership loss or `channel_history_changed`
invalidates the whole channel; never persist cursors; the rate tier is a function of the
distribution path and must be detected, not assumed; `search:read` is required for
`search.messages` and the search surface itself must be preflighted; `users:read.email` gates
deterministic Gmail/Slack identity linking and its absence is a supported configuration.
