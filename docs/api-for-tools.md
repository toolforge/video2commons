# Using video2commons from another tool

A tool that runs in the browser on another site, such as a user script on
Wikimedia Commons, can send the videos of its user to video2commons, which
converts them and uploads them under the user's name, as for the files
uploaded on its own page. The tool never sees the user's OAuth tokens: the
user allows it once, in a popup of video2commons, and the tool gets an API
token for the user's session.

Only the pages of the sites in `api_origins` can do this (see
[Configuration](architecture.md#configuration)). By default, that is
`https://commons.wikimedia.org`.

## Getting a token

1. Open `/connect` in a popup, with the origin of your page:

   ```js
   const V2C = "https://video2commons.toolforge.org";

   window.open(
     `${V2C}/connect?origin=${encodeURIComponent(location.origin)}`,
     "video2commons",
     "width=500,height=600",
   );
   ```

   Open it from a click, so that it is not blocked, and without `noopener`:
   the token is sent to the window that opened the popup.

2. The user logs in to video2commons if they aren't yet, and allows your
   site.

3. The popup sends the token to your page, addressed to your origin only, and
   closes itself:

   ```js
   window.addEventListener("message", (event) => {
     if (event.origin !== V2C || event.data?.type !== "video2commons-token") {
       return;
     }
     const { token, username } = event.data;
     // ...
   });
   ```

The token opens the user's session of video2commons. It lasts as long as the
session, a day that starts again each time it is used, and logging out of
video2commons ends it.

## Calling the API

Send the token in the `Authorization` header; no cookie is sent. Every `POST`
needs the CSRF token of the session, from `/api/csrf`:

```js
const headers = { Authorization: `Bearer ${token}` };
const { csrf } = await (await fetch(`${V2C}/api/csrf`, { headers })).json();
```

Then, for a video on the user's computer:

1. Send it to `/api/upload/upload` in chunks, as
   [`ChunkedUploader.js`](../video2commons/frontend/static/ChunkedUploader.js)
   does (see [Direct file uploads](architecture.md#direct-file-uploads)). Each
   request is a form with the chunk as `file`, the CSRF token as
   `_csrf_token` and, from the second chunk on, the `filekey` of the first
   answer, with a `Content-Range: bytes <first>-<last>/<size>` header. The
   answer is `Continue` until the last chunk, then `Success`.

2. Start the task with `/api/task/run`:

   | Field | Value |
   |---|---|
   | `url` | `uploads:<filekey>` |
   | `extractor` | empty |
   | `subtitles` | `false` |
   | `filename` | the name of the file on Commons, without its extension |
   | `filedesc` | the wikitext of the file page |
   | `format` | one of the formats of `/api/listformats`, e.g. `webm (AV1/Opus)` |
   | `comment` | optional: the edit summary of the upload, at most 500 characters. Without it, the summary says where the media was imported from. |

   The answer gives the `id` of the task, which also appears in the user's
   task list on video2commons.

3. Follow the task with `GET /api/status-single?task=<id>`: its `status` is
   `progress` while it waits or runs, then `done`, with the `url` of the file
   on Commons, or `fail`, with the error in `text`.

## What other sites can't do

The answers to the pages of the sites in `api_origins` carry
`Access-Control-Allow-Origin`, but not `Access-Control-Allow-Credentials`: the
answer to a request that sends the cookie of video2commons stays unreadable
for any other site, as before, so it can't get the CSRF token that a `POST`
needs. The popup can't be shown in a frame, so a page can't get the user to
allow it without seeing it.
