# Using video2commons from another tool

A tool that runs in the browser on another site, such as a user script on
Wikimedia Commons, can send the videos of its user to video2commons, which
converts them and uploads them under the user's name, as for the files
uploaded on its own page. The tool never sees the user's OAuth tokens: the
user allows it once, in a popup of video2commons, and the tool gets an API
token for the user's session.

Only the pages of the sites in `api_origins` can do this (see
[Configuration](architecture.md#configuration)). By default, that is
`https://commons.wikimedia.org`. The popup names the site, and nothing more
precise: every script that runs on the pages of a site in `api_origins` can
open it, and can read the message that carries the token, so list only the
sites whose scripts you trust.

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

The token opens the user's session of video2commons. It lasts a day, which
starts again each time the token is used. Logging out of video2commons, or
logging in to it again, ends it: the tool then asks for a new one. Each
*Allow* gives a new token.

A token lets the tool do what the user can do with their own tasks on
video2commons: upload files, start tasks, and restart, abort or remove them.
It never gives the powers of a maintainer over the tasks of other users.

## Calling the API

Send the token in the `Authorization` header; no cookie is sent. Every `POST`
needs the CSRF token of the session, from `/api/csrf`:

```js
const headers = { Authorization: `Bearer ${token}` };
const { csrf } = await (await fetch(`${V2C}/api/csrf`, { headers })).json();
```

An error comes back as an answer of status 200 with an `error` field, e.g.
`{"step": "error", "error": "Are you logged in?"}`, so check every answer for
it.

## Uploading a file

1. Check the name of the file on Commons first, without its extension: POST
   it as `filename` to `/api/validatefilename`, then to
   `/api/validatefilenameunique`. Each answer gives back the `filename`, or an
   `error`. A name that is taken would otherwise only fail after the whole
   file has been converted.

2. Send the file to `/api/upload/upload` in chunks, as
   [`ChunkedUploader.js`](../video2commons/frontend/static/ChunkedUploader.js)
   does (see [Direct file uploads](architecture.md#direct-file-uploads)). That
   file sends no `Authorization` header, so a tool needs its own copy of the
   loop:

   - each request is a form with the chunk as `file`, under the name of the
     original file, e.g. `body.append("file", chunk, file.name)`: its
     extension decides how big the file may be (12 GiB for a `.mov`, 8 GiB
     for an `.mp4`, 5 GiB otherwise);
   - the CSRF token as `_csrf_token`, and, from the second chunk on, the
     `filekey` of the first answer;
   - a `Content-Range: bytes <first>-<last>/<size>` header.

   Each answer but the last is `{"result": "Continue", "offset": …,
   "filekey": …}`: send the next chunk from `offset`, which is also where to
   start again after an error. The last answer is `"Success"`.

3. Start the task with `/api/task/run`:

   | Field | Value |
   |---|---|
   | `url` | `uploads:<filekey>` |
   | `extractor` | empty |
   | `subtitles` | `false`, as the page of video2commons sends for a file without subtitles |
   | `filename` | the name of the file on Commons, without its extension |
   | `filedesc` | the wikitext of the file page |
   | `format` | one of the formats of `/api/listformats`, e.g. `webm (AV1/Opus)` |
   | `comment` | optional: the edit summary of the upload, on one line, at most 500 characters |

   Without a `comment`, the summary says where the media was imported from.
   With one, the summary is the `comment` for an uploaded file, and the
   `comment` followed by "(imported media from …)" for a URL.

   The answer gives the `id` of the task, which also appears in the user's
   task list on video2commons.

4. Follow the task with `GET /api/status-single?task=<id>`. The answer is
   `{"value": {…}}`, and the `status` of the value is `progress` while the task
   waits or runs, then `done`, with the `url` of the file on Commons, `fail`,
   with the error in `text`, or `abort`. The value is `null` once the task is
   removed, by the user or two weeks later, so stop asking then too.

## What other sites can't do

The answers to the pages of the sites in `api_origins` carry
`Access-Control-Allow-Origin`, but not `Access-Control-Allow-Credentials`: the
answer to a request that sends the cookie of video2commons stays unreadable
for any other site, as before, so it can't get the CSRF token that a `POST`
needs. The popup can't be shown in a frame of another site.
