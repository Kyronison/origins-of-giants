# Architecture

## State and artifacts

`orchestrator/db.py` stores one row per episode in a SQLite `videos` table. The row contains the status, title, structured payload, YouTube ID and timestamps. Payload updates merge inside a write transaction; callers can require an expected status to avoid applying stale transitions.

The normal production path is:

```text
idea → approved_topic → scripted → approved_script → assets
     → rendered → qc_passed → approved_final → uploaded
     → published → analyzed
```

Additional states cover rejection, failed quality checks and manual uploading. `orchestrator/main.py` dispatches ready stages. OS-level locks prevent simultaneous workers from advancing the same pipeline.

Large episode artifacts live under the configured data directory, separately from the source repository:

```text
data/
  pipeline.db
  spend.sqlite3
  videos/<episode-id>/
    facts.csv
    script.md
    storyboard.json
    voice.mp3
    words.json
    timeline.json
    final.mp4
```

The exact files vary by format and stage. These production files are excluded from the repository.

## Production modules

| Concern | Main code |
|---|---|
| Topic selection | `stages/topics.py`, `series.py` |
| Script, facts and entity extraction | `stages/story.py`, `stages/script.py`, `stages/claims.py` |
| Narration and media | `stages/assets.py`, `stages/story_assets.py`, `stages/archive.py`, `stages/voice_chain.py` |
| Timing and sound | `stages/pauses.py`, `stages/sound.py`, `loudness.py` |
| Rendering | `stages/render.py`, `remotion/src/Main.tsx` |
| Media/release checks | `stages/preflight.py`, `stages/qc.py`, `gates.py`, `visual_integrity.py` |
| Publishing | `stages/publish.py`, `stages/upload.py` |
| Measurement | `stages/metrics.py`, `stages/analytics.py` |

## Python-to-Remotion contract

Python produces a timeline with scene IDs, types, start/end times, scene data and references to media slots. Word timings connect narration to visual changes. The renderer receives JSON props and the episode directory as its public asset directory.

`remotion/src/theme.ts` defines the shared TypeScript shapes. `SceneRouter.tsx` selects components for maps, people, text, numerical graphics and media. The `Main` composition combines scenes, transitions, overlays, narration, music and subtitles. Separate compositions support vertical and illustrated formats.

The bundled sample follows this contract with text scenes and audio disabled. It needs no production asset files.

## Recovery and review

- Queue state persists across process restarts.
- Process locks coordinate queue and manual operations.
- Review approvals and visual-integrity records can be bound to the current artifact contents.
- Upload receipts record the remote ID independently of the queue database. An ambiguous interrupted upload requires reconciliation before retrying.
- Spending records attribute service requests to episodes and stages. Some requests require a reservation before purchase; provider balance movements and per-call receipts are distinct evidence.

These mechanisms depend on the selected configuration. The public environment template enables review-first settings; production-specific profiles can use different settings.

## Additional formats

The same repository contains Spanish-language stages, an illustrated everyday-history lane (`ancestors_*`) and science-explainer code (`space_*`). The science renderer uses values checked by `space_physics.py` and distinguishes established claims, uncertain estimates and illustrations in its visual labels.

Reusable editorial-repair helpers live in `orchestrator/tools/`. Their tests import those modules directly and require no production scratch data.

The illustrated-history regression tests use explicitly synthetic research and narration in `tests/fixtures/ancestors_pilot/`. These files exercise schema, queue and upload behavior without including a production episode's private seed files. Fixture claims are placeholders, not historical evidence.
