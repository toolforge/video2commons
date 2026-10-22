# Architecture

This document explains how video2commons is put together: where each part
runs, how a task travels from the browser to Commons, and what keeps the
system running. For builds and deployments, see [CI/CD](ci-cd.md).

- [The big picture](#the-big-picture)
- [Life of a task](#life-of-a-task)
- [The web frontend](#the-web-frontend)
- [Direct file uploads](#direct-file-uploads)
- [Queues and routing](#queues-and-routing)
- [The encoding pipeline](#the-encoding-pipeline)
- [Task states](#task-states)
- [Real-time updates](#real-time-updates)
- [Redis: the shared memory](#redis-the-shared-memory)
- [Login and permissions](#login-and-permissions)
- [Rate limiting and YouTube](#rate-limiting-and-youtube)
- [Keeping the encoders healthy](#keeping-the-encoders-healthy)
- [Configuration](#configuration)

## The big picture

video2commons is split in two halves that only talk to each other through
**Redis**:

- the **Toolforge** half faces users: a Flask web app and a Socket.IO server;
- the **Cloud VPS** half does the heavy lifting: six Celery workers, the
  *encoders*, which download, convert and upload media.

```mermaid
%%{init: {"flowchart": {"curve": "basis", "nodeSpacing": 30, "rankSpacing": 50}}}%%
flowchart TB
    user(["🧑 Browser"])

    subgraph toolforge ["☁️ Toolforge · Kubernetes"]
        direction LR
        jobs["⏰ <b>Scheduled jobs</b><br/>cleanup · yt-dlp updates"]
        io["⚡ <b>video2commons-socketio</b><br/>Node.js + Socket.IO"]
        web["🌐 <b>video2commons</b><br/>Flask + uWSGI<br/>wizard UI · REST API"]
        test["🧪 <b>video2commons-test</b><br/>same app, test instance"]
    end

    subgraph vps ["🖥️ Cloud VPS · project “video”"]
        direction TB
        redis[("🧠 <b>Redis</b><br/>video-redis-bookworm")]
        subgraph enc ["⚙️ Encoders"]
            direction LR
            subgraph light ["standard · 2 tasks each"]
                direction LR
                e1["⚙️ 01"] ~~~ e2["⚙️ 02"] ~~~ e3["⚙️ 03"] ~~~ e4["⚙️ 04"]
            end
            subgraph heavy ["heavy · 1 task each"]
                direction LR
                e5["🏋️ 05"] ~~~ e6["🏋️ 06"]
            end
        end
        nfs[("📁 NFS<br/>ffmpeg · scratch")]
    end

    sources(["📺 Video sites"])

    subgraph wikimedia ["🏛️ Wikimedia"]
        direction LR
        commons["Commons<br/>API & OAuth"]
        wcqs["Commons Query<br/>Service"]
    end

    user <-->|HTTPS| web
    user <-.->|WebSocket| io
    web <--> redis
    io <--> redis
    jobs --> redis
    redis <-->|tasks · progress| enc
    sources -->|download| enc
    enc --- nfs
    enc -->|upload| commons
    web -->|OAuth · checks| commons
    web --> wcqs

    classDef person fill:#e8f1fd,stroke:#3b82f6,stroke-width:2px,color:#1e3a8a
    classDef tf fill:#f1ebfe,stroke:#8b5cf6,stroke-width:2px,color:#3b0764
    classDef store fill:#fde8ec,stroke:#e11d48,stroke-width:2px,color:#881337
    classDef worker fill:#fef3e2,stroke:#f59e0b,stroke-width:2px,color:#78350f
    classDef big fill:#fde7d0,stroke:#ea580c,stroke-width:2px,color:#7c2d12
    classDef wm fill:#e7f8ee,stroke:#16a34a,stroke-width:2px,color:#14532d
    classDef ext fill:#f1f5f9,stroke:#64748b,stroke-width:2px,color:#1e293b
    class user person
    class web,test,io,jobs tf
    class redis,nfs store
    class e1,e2,e3,e4 worker
    class e5,e6 big
    class commons,wcqs wm
    class sources ext
    style toolforge fill:#faf7ff,stroke:#c4b5fd,color:#5b21b6
    style vps fill:#fffaf0,stroke:#fcd34d,color:#92400e
    style enc fill:#fffdf7,stroke:#fde68a,color:#92400e
    style light fill:#fffbeb,stroke:#fde68a,color:#92400e
    style heavy fill:#fff7ed,stroke:#fdba74,color:#9a3412
    style wikimedia fill:#f6fdf9,stroke:#86efac,color:#166534
```

| Part | Where | What it does |
|---|---|---|
| **Web frontend** | Toolforge tool `video2commons` ([`frontend/`](../video2commons/frontend)) | Serves the UI, logs users in with OAuth, extracts metadata from URLs, validates file names and descriptions, receives direct uploads, queues tasks. |
| **Test frontend** | Toolforge tool `video2commons-test` | The same app, deployed automatically from `master` to try changes. |
| **Socket.IO server** | Toolforge tool `video2commons-socketio` ([`video2commons-socketio/`](../video2commons-socketio)) | Pushes task progress to browsers in real time. |
| **Encoders** | Cloud VPS `encoding01`…`encoding06` ([`backend/`](../video2commons/backend)) | Celery workers running the download → encode → upload pipeline. |
| **Redis** | Cloud VPS `video-redis-bookworm` | Task queue, task results, sessions, task lists, locks, statistics and notifications. |
| **Shared code** | [`shared/`](../video2commons/shared) | Used by both halves: task status, statistics, rate limiting, error messages. |

## Life of a task

From the first click to the file on Commons:

```mermaid
sequenceDiagram
    autonumber
    actor U as 🧑 User
    participant W as 🌐 Frontend
    participant R as 🧠 Redis
    participant E as ⚙️ Encoder
    participant S as 📺 Source site
    participant C as 🏛️ Commons
    participant IO as ⚡ Socket.IO

    rect rgba(139, 92, 246, 0.08)
    note over U,W: Wizard: preparing the task
    U->>W: URL of the video (or a direct upload)
    W->>S: yt-dlp: metadata only
    S-->>W: title, author, date, license, resolution…
    W-->>U: suggested file name, description, formats
    U->>W: checks and confirms
    W->>C: is the file name valid and free?
    end

    rect rgba(225, 29, 72, 0.07)
    note over W,R: Queueing
    W->>R: Celery task on the “celery” or “heavy” queue
    W->>R: task id, title and parameters for this user
    W-)IO: “add” notification
    end

    rect rgba(245, 158, 11, 0.09)
    note over R,C: On an encoder
    R->>E: next task
    E->>S: download (yt-dlp)
    E->>E: convert (ffmpeg)
    E->>C: upload in chunks, as the user (OAuth)
    E->>C: subtitles (TimedText pages)
    E->>R: result: file name and URL
    end

    loop at every step
        E-)R: progress (text, percentage)
        R-)IO: notification
        IO-)U: live update in the task list
    end
```

The frontend never encodes anything and the encoders never talk to the
browser: everything goes through Redis. A task can be **aborted** or
**restarted** from the task list (see [Task states](#task-states)).

## The web frontend

[`frontend/app.py`](../video2commons/frontend/app.py) is a Flask app run by
uWSGI on Toolforge. It serves:

- the page itself, built from Jinja2 templates, and the browser code
  [`static/video2commons.js`](../video2commons/frontend/static/video2commons.js),
  which renders the wizard with precompiled Nunjucks templates
  (`static/templates/`);
- the **OAuth** login (`/oauthinit`, `/oauthcallback`, `/logout`);
- a JSON **API** under `/api` ([`frontend/api.py`](../video2commons/frontend/api.py));
- translations under `/i18n`, synced from translatewiki.net.

The wizard is a small state machine on the browser side:

```mermaid
stateDiagram-v2
    direction LR
    [*] --> source
    source --> playlist: playlist URL
    source --> target: single video
    playlist --> target: edit one video
    target --> playlist: back to the list
    playlist --> confirm: videos selected
    target --> confirm: name & description valid
    confirm --> [*]: task(s) queued

    state "🔗 Source<br/>URL or upload, keep audio/video, subtitles" as source
    state "📃 Playlist<br/>videos to import" as playlist
    state "📝 Target<br/>file name, description, format" as target
    state "✅ Confirm<br/>summary" as confirm

    classDef step fill:#f1ebfe,stroke:#8b5cf6,color:#3b0764
    classDef done fill:#e7f8ee,stroke:#16a34a,color:#14532d
    class source,playlist,target step
    class confirm done
```

Main API endpoints (all `POST` calls need the CSRF token given by `/api/csrf`):

| Endpoint | Role |
|---|---|
| `GET /api/status` | Tasks visible to the user (all tasks for maintainers), with worker statistics. |
| `POST /api/extracturl` | Runs yt-dlp **without downloading** to get the metadata and build a pre-filled description. Also detects playlists. |
| `POST /api/listformats` | Output formats available for the chosen audio/video combination. |
| `POST /api/validateurl` | Checks whether the video is already on Commons, with the Commons Query Service. |
| `POST /api/validatefilename`, `validatefilenameunique`, `validatefiledesc` | Checks the target file name and description against Commons. |
| `POST /api/upload/upload` | Receives a direct upload, chunk by chunk. |
| `POST /api/task/run` | Queues a task. |
| `POST /api/task/restart`, `task/abort`, `task/remove` | Manages an existing task (own tasks only, any task for maintainers). |
| `GET /api/iosession` | One-minute ticket to authenticate on the Socket.IO server. |

Output formats map to the encoding profiles of
[`encode/transcode.py`](../video2commons/backend/encode/transcode.py):
**WebM AV1/Opus** (default), WebM VP9/Opus, WebM VP8/Vorbis and Ogg
Theora/Vorbis for video, Ogg Vorbis or Opus for audio only.

## Direct file uploads

Files from the user's computer don't come from a video site, so they take a
detour: the browser sends them to the frontend, and the encoder downloads them
back from the frontend over HTTP.

```mermaid
sequenceDiagram
    autonumber
    participant B as 🧑 Browser<br/>ChunkedUploader.js
    participant W as 🌐 Frontend<br/>upload.py
    participant D as 📁 static/uploads/
    participant E as ⚙️ Encoder

    B->>W: chunk 1 (4 MB) + Content-Range
    W->>W: new filekey = uuid + original extension
    W->>D: write <filekey>
    W-->>B: Continue · filekey · offset
    loop each next chunk
        B->>W: chunk n + filekey + Content-Range
        W->>D: append if the offset matches
        W-->>B: Continue · offset
    end
    W-->>B: Success
    B->>W: run the task with url = uploads:<filekey>
    W-)E: task queued
    E->>W: GET /static/uploads/<filekey>
    W-->>E: the file
```

- [`ChunkedUploader.js`](../video2commons/frontend/static/ChunkedUploader.js)
  sends 4 MB chunks one after the other, retries failed chunks up to 5 times,
  pauses when the browser goes offline and resumes when it comes back.
- The **filekey** keeps the original extension (`<uuid>.mp4`): the encoder
  uses it to choose the download size limit (see [Limits](#limits)).
- Uploaded files are deleted by a scheduled job on Toolforge.

## Queues and routing

Converting a 4K or high-bitrate video can take a lot of memory. To avoid
taking down regular workers, such tasks go to a separate **`heavy`** queue,
served by bigger, single-task encoders.

```mermaid
%%{init: {"flowchart": {"curve": "basis"}}}%%
flowchart LR
    start(["📥 New task"]) --> restart{"Restart of a<br/>failed task?"}
    restart -- yes --> H
    restart -- no --> upload{"Direct<br/>upload?"}
    upload -- yes --> L
    upload -- no --> res{"Width or height<br/>≥ 3840 px?"}
    res -- yes --> H
    res -- no --> rate{"Bitrate known?"}
    rate -- "no" --> H
    rate -- yes --> big{"≥ 20 Mbps?"}
    big -- yes --> H
    big -- no --> L

    L[["⚙️ queue <b>celery</b>"]]
    H[["🏋️ queue <b>heavy</b>"]]

    classDef q fill:#f8fafc,stroke:#94a3b8,stroke-width:1.5px,color:#0f172a
    classDef light fill:#fef3e2,stroke:#f59e0b,stroke-width:2px,color:#78350f
    classDef heavy fill:#fde7d0,stroke:#ea580c,stroke-width:2px,color:#7c2d12
    classDef startNode fill:#e8f1fd,stroke:#3b82f6,stroke-width:2px,color:#1e3a8a
    class restart,upload,res,rate,big q
    class L light
    class H heavy
    class start startNode
```

The decision is made by the frontend, from the yt-dlp metadata
(`predict_task_type` in [`urlextract.py`](../video2commons/frontend/urlextract.py)).
Restarted tasks always go to `heavy`, in case the first attempt failed because
it was routed to the wrong queue.

| Encoders | Queues listened to | Tasks at once |
|---|---|---|
| `encoding01` → `encoding04` | `celery` | 2 |
| `encoding05`, `encoding06` | `heavy` and `celery` | 1 |

Heavy encoders also take regular tasks, so they are never idle.
Each worker takes only one task ahead (`worker_prefetch_multiplier = 1`), so
long tasks don't hold back others in a worker's local buffer.

## The encoding pipeline

Everything an encoder does for one task happens in `main()` in
[`backend/worker.py`](../video2commons/backend/worker.py):

```mermaid
%%{init: {"flowchart": {"curve": "basis", "nodeSpacing": 25, "rankSpacing": 35}}}%%
flowchart TB
    A(["📥 Task received"]) --> B{"Already running<br/>elsewhere?"}
    B -- yes --> X1(["🚫 Ignored"])
    B -- no --> C{"≥ 10 GiB free<br/>on /srv?"}
    C -- no --> X2(["⏳ Retry in 5 min<br/>max 20 times"])
    C -- yes --> D["🔒 Lock the task<br/>(7 days)"]
    D --> E["⬇️ <b>Download</b><br/>yt-dlp · size limit · subtitles"]
    E --> F["🎞️ <b>Encode</b><br/>ffmpeg, or copy streams<br/>already in a free codec"]
    F --> G["🔑 Log in to Commons<br/>with the user's OAuth token"]
    G --> H["🏷️ Add inferred categories<br/>no audio · subtitle languages"]
    H --> I["⬆️ <b>Upload</b><br/>chunks of 16 MiB · 5 retries"]
    I --> J["💬 Upload subtitles<br/>TimedText pages"]
    J --> K(["✅ Done: file URL"])
    K --> Z["🧹 Clean up<br/>temporary files · stats"]

    E & F & I -. "error or abort" .-> Y(["❌ Failed / aborted"])
    Y --> Z

    classDef step fill:#fef3e2,stroke:#f59e0b,stroke-width:2px,color:#78350f
    classDef ok fill:#e7f8ee,stroke:#16a34a,stroke-width:2px,color:#14532d
    classDef ko fill:#fde8ec,stroke:#e11d48,stroke-width:2px,color:#881337
    classDef neutral fill:#f1f5f9,stroke:#64748b,stroke-width:2px,color:#1e293b
    classDef q fill:#f8fafc,stroke:#94a3b8,stroke-width:1.5px,color:#0f172a
    class D,E,F,G,H,I,J step
    class K ok
    class Y,X1 ko
    class X2,Z,A neutral
    class B,C q
```

### Download

[`backend/download`](../video2commons/backend/download/__init__.py) wraps
yt-dlp. It picks the best video and audio streams for the requested format,
downloads the subtitles (converted to SRT), and enforces a size limit that
depends on the source container (see [Limits](#limits)): formats that
usually shrink a lot once converted, like MP4 and MOV, get more room.

### Encode

[`backend/encode`](../video2commons/backend/encode) is adapted from
MediaWiki's TimedMediaHandler:

- ffprobe inspects the source. When the video or audio stream is already in
  the target codec, it is **copied** instead of re-encoded; a file that is
  already in free formats is only remuxed.
- ffmpeg runs with the lowest CPU priority (`nice 19`), a 2-day time limit,
  and an output size cap.
- The thread count is the number of CPUs divided by the worker's
  concurrency. AV1 encoding of 4K videos is capped at 4 threads to save
  memory.
- If ffmpeg stops reporting progress for 2 hours, it is killed and the task
  fails with a "stopped responding" error.
- ffmpeg is not Debian's: it comes from a Gentoo Prefix build shared over NFS,
  which provides SVT-AV1 for AV1 encoding.

### Upload

[`backend/upload`](../video2commons/backend/upload/__init__.py) uses
Pywikibot, authenticated with the user's OAuth token: the file appears in the
user's contributions. Files over 100 MiB are sent in 16 MiB chunks. Transient
errors are retried up to 5 times with an exponential backoff (20 s, 40 s,
80 s…). Subtitles become `TimedText:` pages, and categories such as
*Videos without audio* or *Videos with French subtitles* are added to the
description.

### Limits

| Limit | Value | Where |
|---|---|---|
| Download, general case | 5 GiB | `backend/download` |
| Download, `.mp4`/`.m4v` source | 8 GiB | `backend/download` |
| Download, `.mov`/`.qt` source | 12 GiB | `backend/download` |
| Free disk space to start a task | 10 GiB | `backend/worker.py` |
| Encoding time | 2 days (killed after 2 h without progress) | `backend/encode` |
| File uploaded to Commons | < 5 GiB | `backend/upload` |
| Tasks kept in the task list | 2 weeks | `frontend/api.py` |
| Task results kept | 1 month | `backend/worker.py` |

## Task states

A task is a Celery task: its state lives in the Celery result backend (Redis
DB 1), and [`shared/tasks.py`](../video2commons/shared/tasks.py) turns it into
what the UI displays.

```mermaid
stateDiagram-v2
    direction LR
    [*] --> PENDING: queued
    PENDING --> PROGRESS: picked by an encoder
    PROGRESS --> SUCCESS: on Commons
    PROGRESS --> FAILURE: error
    PROGRESS --> ABORTED: abort button
    PENDING --> RETRY: disk full
    RETRY --> PENDING: 5 min later
    FAILURE --> [*]: restart → new task
    SUCCESS --> [*]
    ABORTED --> [*]

    classDef ok fill:#e7f8ee,stroke:#16a34a,color:#14532d
    classDef ko fill:#fde8ec,stroke:#e11d48,color:#881337
    classDef run fill:#fef3e2,stroke:#f59e0b,color:#78350f
    class SUCCESS ok
    class FAILURE,ABORTED ko
    class PENDING,PROGRESS,RETRY run
```

When a task fails, [`shared/errors.py`](../video2commons/shared/errors.py)
matches the error message against known problems (YouTube rate limiting,
bot detection, file already on Commons…) to show a translated, actionable
message instead of a raw traceback. A failed task can be restarted once: the
restart creates a new task with the same parameters.

## Real-time updates

The task list updates without reloading the page, through the Socket.IO
server in [`video2commons-socketio/index.js`](../video2commons-socketio/index.js):

```mermaid
sequenceDiagram
    autonumber
    participant B as 🧑 Browser
    participant W as 🌐 Frontend
    participant IO as ⚡ Socket.IO
    participant R as 🧠 Redis
    participant E as ⚙️ Encoder

    rect rgba(59, 130, 246, 0.07)
    note over B,R: Connection
    B->>W: GET /api/iosession
    W->>R: iosession:<ticket> → session id (60 s)
    W-->>B: ticket
    B->>IO: auth(ticket, CSRF token)
    IO->>R: ticket → session, check the CSRF token
    IO->>W: GET /api/status with the user's session
    W-->>IO: user's tasks + rooms
    IO-->>B: status (full list)
    IO->>IO: join the rooms: user + each task
    end

    rect rgba(245, 158, 11, 0.08)
    note over B,E: Updates
    E->>R: PUBLISH v2cnotif:update
    R-)IO: message
    IO-)B: update(task, status) to the task's room
    end
```

Socket.IO listens to two kinds of events:

- **`v2cnotif:*` channels**, published by the frontend and the workers:
  `add` (new task), `update` (new status, sent as is), `remove` (task removed);
- **Redis keyspace notifications** on the Celery results (DB 1): when a
  result changes, Socket.IO asks the frontend for the new status; when it
  expires, the task disappears from the list.

Without WebSocket support, the browser falls back to polling `/api/status`.

## Redis: the shared memory

One Redis server, three databases:

```mermaid
%%{init: {"flowchart": {"curve": "basis", "nodeSpacing": 20}}}%%
flowchart LR
    subgraph db2 ["DB 2 · Celery broker"]
        q1["📬 celery"]
        q2["📬 heavy"]
        un["unacked"]
    end
    subgraph db1 ["DB 1 · Celery results"]
        meta["celery-task-meta-&lt;id&gt;<br/>state, progress, result"]
    end
    subgraph db3 ["DB 3 · Application"]
        direction TB
        sess["session:&lt;sid&gt;<br/>iosession:&lt;ticket&gt;"]
        tasks["tasks:&lt;user&gt; · alltasks<br/>titles: · params: · restarted:"]
        lock["tasklock:&lt;id&gt;<br/>yt_dlp_lock:…"]
        misc["stats · sudoers<br/>commons:filename-prefix-blacklist"]
        pub["📢 channels v2cnotif:*"]
    end

    web["🌐 Frontend"] --> db2 & db3
    enc["⚙️ Encoders"] --> db2 & db1 & db3
    io["⚡ Socket.IO"] --> db1 & db3

    classDef key fill:#fde8ec,stroke:#e11d48,stroke-width:1.5px,color:#881337
    classDef app fill:#f1ebfe,stroke:#8b5cf6,stroke-width:2px,color:#3b0764
    classDef worker fill:#fef3e2,stroke:#f59e0b,stroke-width:2px,color:#78350f
    class q1,q2,un,meta,sess,tasks,lock,misc,pub key
    class web,io app
    class enc worker
    style db1 fill:#fff5f7,stroke:#fda4af,color:#9f1239
    style db2 fill:#fff5f7,stroke:#fda4af,color:#9f1239
    style db3 fill:#fff5f7,stroke:#fda4af,color:#9f1239
```

| Key | Content | Lifetime |
|---|---|---|
| `session:<sid>` | Flask session: OAuth tokens, user name, CSRF token ([`redisession.py`](../video2commons/frontend/redisession.py)) | 1 day |
| `iosession:<ticket>` | Socket.IO login ticket → session id | 60 s |
| `tasks:<user>`, `alltasks` | Task ids, per user and global | 2 weeks |
| `titles:<id>`, `params:<id>` | File name and parameters of a task (used by restarts) | 2 weeks |
| `restarted:<id>` | Id of the task created by a restart | 2 weeks |
| `tasklock:<id>` | Encoder running the task; prevents running it twice | 7 days |
| `yt_dlp_lock:<source>:<group>` | Rate-limiting lock for YouTube | 20 min max |
| `stats` | Queue length and worker activity shown in the UI | — |
| `sudoers` | Maintainers' user names | — |

## Login and permissions

Users log in with **OAuth** on Commons ([`mwoauth`](https://pypi.org/project/mwoauth/)).
The OAuth tokens are kept in the session, and the encoder receives them with
the task to upload on behalf of the user.

To use the tool, a user must be either:

- **autoconfirmed** with at least **50 edits**, or
- in the **confirmed** group on Commons, or
- a video2commons **maintainer** (and autoconfirmed).

Maintainers (the Redis `sudoers` list) see every user's tasks and can abort,
restart or remove any of them.

All `POST` API calls need the session's CSRF token.

## Rate limiting and YouTube

YouTube quickly blocks clients that make too many requests. To limit this:

- all yt-dlp requests to YouTube go through
  [`shared/ratelimiting.py`](../video2commons/shared/ratelimiting.py): a Redis
  lock allows **one YouTube download at a time across all encoders** (and one
  metadata extraction at a time on the frontend), with pauses between
  requests;
- the encoders can use YouTube cookies (`/srv/v2c/cookies.txt`), refreshed with
  the scripts in [`utils/cookies`](../utils/cookies/README.md);
- yt-dlp is updated every day, on Toolforge and on the encoders, to keep up
  with changes on the video sites.

## Keeping the encoders healthy

Each encoder runs Celery as the `v2ccelery` systemd service, set up by
[Puppet](../puppet/backend.pp). Two layers make sure a stuck or crashed
worker comes back.

**🛡️ systemd** handles crashes:

| Setting | Effect |
|---|---|
| `OOMPolicy=continue` | An ffmpeg killed for lack of memory fails its task, not the whole service. |
| `MemoryMax=90%` | Memory pressure stays inside the service, so the kernel kills an encode rather than something else. |
| `Restart=always`, `RestartSec=30` | The service comes back 30 s after any exit. |
| `ExecStopPost=pkill ffmpeg` | No orphan ffmpeg is left behind to block the next stop. |
| `TimeoutStopSec=infinity` | Restarts are **warm**: running tasks finish first, which can take hours. |

**🩺 [`healthcheck.sh`](../utils/healthcheck.sh)** runs every 5 minutes, as
root, and handles a worker that is alive but not working:

```mermaid
%%{init: {"flowchart": {"curve": "basis", "nodeSpacing": 25, "rankSpacing": 50}}}%%
flowchart LR
    h1{"State of<br/>v2ccelery?"}
    h1 -- "running,<br/>answers ping" --> ok(["✅ nothing to do"])
    h1 -- "finishing<br/>its tasks" --> ok
    h1 -- "running,<br/>no answer" --> n{"288 misses<br/>in a row?<br/><i>~24 h</i>"}
    n -- no --> wait(["⏳ count and wait"])
    n -- yes --> rs(["🔄 restart"])
    h1 -- "stopped<br/>or failed" --> rs
    h1 -- "stuck stopping<br/>&gt; 15 min" --> kill(["💥 SIGKILL everything<br/>systemd restarts it"])

    classDef q fill:#f8fafc,stroke:#94a3b8,stroke-width:1.5px,color:#0f172a
    classDef ok fill:#e7f8ee,stroke:#16a34a,stroke-width:2px,color:#14532d
    classDef act fill:#fef3e2,stroke:#f59e0b,stroke-width:2px,color:#78350f
    classDef ko fill:#fde8ec,stroke:#e11d48,stroke-width:2px,color:#881337
    class h1,n q
    class ok,wait ok
    class rs act
    class kill ko
```

- The health check is deliberately patient with a worker that doesn't answer
  pings: a worker busy on a huge file can miss them. It only restarts after
  about 24 hours of silence.
- Logs: `journalctl -u v2ccelery`, `journalctl -t v2c-healthcheck` and
  `/var/log/v2ccelery/`.

Other scheduled tasks on each encoder:

| When | What |
|---|---|
| Every hour, at :48 | Delete leftover task directories older than a day (`backend/cleanup.sh`) |
| Every hour, at :00 | Collect worker statistics for the UI (`utils/stats.py`; after a random pause, the first encoder to run it updates them for everyone) |
| Every day, at 06:32 | Update yt-dlp, and restart Celery only if the version changed |

## Configuration

Both halves read a `config.json` at the root of their checkout
([example](../config.json.example)), loaded by
[`video2commons/config.py`](../video2commons/config.py):

| Key | Used by | Purpose |
|---|---|---|
| `consumer_key`, `consumer_secret` | frontend, encoders | OAuth consumer on Commons |
| `api_url` | frontend, encoders | Commons `index.php` URL, for OAuth |
| `redis_host`, `redis_pw` | everyone | Redis server |
| `session_key` | frontend | Lets trusted internal calls bypass the login check |
| `webfrontend_uri`, `socketio_uri` | frontend, Socket.IO | Public URLs of the two Toolforge tools |

On the encoders, `config.json` is generated by Puppet from secrets stored in
GitHub (see [CI/CD](ci-cd.md#encoders-cloud-vps)). On Toolforge, it is
maintained by hand in each tool's directory.
