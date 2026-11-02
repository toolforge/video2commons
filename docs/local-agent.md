# Local YouTube downloads

If YouTube rejects a server download with “Sign in to confirm you're not a bot”,
the source form offers **Use a local agent** for individual YouTube videos,
including Shorts, mobile links and `youtu.be` links. The existing server path
remains available. A YouTube video URL with a playlist parameter selects just
that video; playlist-only links are not supported by the agent.

The agent reads metadata **and downloads on the user's computer**. Neither step
uses the Toolforge server's YouTube connection. It sends the downloaded media to
video2commons in chunks. The user then reviews the source, author, license,
description, filename and output format in the existing wizard and explicitly
confirms the Commons upload. The normal workers convert and upload the staged
file using the browser user's existing OAuth authorization.

## Install and use

1. Install Python 3.10 or newer, ffmpeg (on `PATH`), and a supported JavaScript
   runtime for yt-dlp's YouTube challenges (Node.js 22+ or Deno).
2. Install the Python libraries:
   `python -m pip install --upgrade requests "yt-dlp[default]"`.
3. Paste a YouTube video link into video2commons, choose the video/audio tracks,
   and click **Use a local agent**. Download the linked `video2commons-agent.py`.
4. Run `python video2commons-agent.py`. Alternatively, with uv installed, use
   `uv run video2commons-agent.py` to provision its Python libraries automatically.
5. Paste the full pairing code displayed in the browser into the agent. Check
   the video URL in the terminal and confirm the download. Keep the browser open.
6. Once the file is received, click **Next**, review the description and license,
   and confirm the Commons upload in video2commons.

This version ships a Python script, not a prebuilt executable. One pairing
handles one Creative Commons Attribution video, up to 5 GiB. The agent checks the
actual yt-dlp license field, not keywords in the description. Subtitles,
thumbnails, frame captures, proxies and browser-cookie extraction are outside
this contribution. The main wizard remains the final licensing review.

Local downloads are an alternative route, not a guarantee: YouTube can also
block residential connections or change its extraction requirements. Keep
yt-dlp and its JavaScript runtime current. Agent failures appear both in the
terminal and in the browser. Cancel the transfer and start again after fixing
an error. Transient connection failures during file transfer retry the current
chunk without appending it twice; restarting the agent requires a new pairing.

## Protocol and deployment

The `/api/local-agent` blueprint uses the frontend's existing Redis database and
upload staging directory. Deploy it with the normal frontend build; the agent
download endpoint serves the script from the same deployed checkout. No OAuth
consumer changes, new server services or persistent desktop credentials are
needed. The worker code is unchanged.

- Browser `start`, `status` and `cancel` requests require both the logged-in
  browser session and its CSRF token. Transfers are bound to that exact session.
- A cryptographically random, single-use pairing capability expires after ten
  minutes. Claiming it atomically consumes it and returns a separate random
  capability for that transfer only. Redis stores capability hashes.
- The agent does not receive session cookies, CSRF tokens, OAuth credentials or
  the ability to queue a Commons upload. Logout or expiry of the browser session
  revokes its capability. Transfer records expire after six hours.
- The agent makes outbound HTTPS requests only, accepts the production and test
  video2commons origins, and never follows authenticated redirects. No local
  listening port, browser extension or URL protocol registration is required.
- The server assigns the staging filename and checks metadata/video ID, allowed
  extension, declared size, chunk size/ranges and final length. Per-transfer
  locks serialize writes, completion and cancellation. Files are capped at
  5 GiB and chunks at 4,000,000 bytes.
- Cancelling removes an incomplete staging file. Ready files use the existing
  uploaded-file retention and cleanup so queued workers can still retrieve them.
  Abandoned partial files also need the deployment's normal upload cleanup.
- The server builds the usual YouTube source, license and attribution using
  `_extract_info`, with escaped, restricted metadata from the agent. As with
  manually uploaded files, client metadata is not independent proof of rights.
- Heavy-queue routing is used for local uploads. Local subtitle import is
  explicitly disabled; changing the source URL restores the regular choices.

## Validation

Run the existing JavaScript checks (`npm test`, `npm run lint`, `npm run build`)
and the Python checks (`uv run ruff check .`, `uv run ruff format --check .`).

The isolated Python integration tests exercise the real agent transfer client
against Flask and an in-memory Redis implementation, without contacting
YouTube or uploading anything to Commons:

```sh
uv run --with flask --with redis --with 'fakeredis[lua]' \
  --with requests --with 'yt-dlp[default]' \
  python -m unittest discover -s tests -p 'test_*.py'
```

For deployment acceptance, use the test frontend with a confirmed Commons
account and an explicitly CC-licensed video. Check download, cancellation,
description review, conversion and final upload. Automated tests do not assert
that a particular public IP can currently download from YouTube.
