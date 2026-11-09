# Local operation

## Separate source from production state

Copy `.env.example` to `.env`. Use a new `DATA_DIR` when evaluating the project; never point a test checkout at a production database. Credentials, OAuth files, upload receipts, provider logs and channel analytics belong outside Git.

The sample environment disables automatic production, automatic script/final approval, Spanish automatic processing and file retention. It selects manual uploading. These settings make the initial configuration explicit; they do not replace reviewing the CLI command being run.

## Services

Production stages use configurable services for text/research, speech and visual generation, stock media, Telegram and YouTube. Blank provider keys in `.env.example` are intentional. Configure only the stages you need and select model IDs available in your own accounts.

YouTube API access uses a Google OAuth desktop client file, then a local authorization flow:

```bash
python -m orchestrator.main auth-youtube
```

The resulting token is private local state. Review account/channel identity before uploading. Additional channel profiles have separate token/data settings and may contain machine-specific defaults that must be adapted.

Telegram requires an explicit `TELEGRAM_CHAT_ID`. Group chats also require `TELEGRAM_ALLOWED_USER_IDS`; the bot does not pair itself to an arbitrary first sender.

## CLI overview

| Command | Purpose |
|---|---|
| `init` | Create the local data directory and queue database |
| `status` | Inspect queue state |
| `doctor` | Check dependencies, configured credentials and connectivity |
| `topics` | Generate proposed topics; can call models and Telegram |
| `approve <id>` | Advance a review decision for the selected episode |
| `run` | Process episodes ready for their next stage |
| `stage <stage> <id>` | Run a specific production stage |
| `watch 60` | Poll controls and queue every 60 seconds |
| `link <id> <youtube_id>` | Associate a manually uploaded episode with its YouTube ID |

All commands are prefixed with `python -m orchestrator.main`. `run`, `stage`, `watch` and publishing commands can create costs or external changes. Review configuration, channel identity and budget limits before running them.

The production topic queues are intentionally omitted. `stories.txt` uses pipe-delimited fields for the topic code, company name, key people and research angle; see `orchestrator/stages/topics.py` for the optional series field. Keep real editorial queues local.

## Testing

The Python tests exercise failure paths using temporary data and mocks. They cover areas such as concurrent database updates, duplicate-upload recovery, Telegram authorization, media rejection persistence and spending accounting. The repository also contains the existing Remotion TypeScript configuration for a static type check.

```bash
python -B -m unittest discover -s tests -v
cd remotion
npx tsc --noEmit
```

A passing unit suite does not verify provider availability, video quality, media rights or successful publication. Run integration checks separately with explicitly configured test resources.
