# TODOs

## Features
- Add end-of-game screen (social sharing, replay option)
- Improve TTS latency with streaming
- Improve prompts and LLM usage
- Investigate deploying to Render and/or Discord

## Refactoring
- Remove `app/services/game_components/` — entire directory is dead code (6 files, nothing imports from it)
- Remove `app/ai/host_service.py` — backward-compat wrapper that just re-exports from `app/ai/host/service.py`
- Remove `app/ai/main.py` — standalone test script, not imported anywhere
- Remove `app/ai/player.py` — only used by the dead `ai/main.py`
- Remove `app/ai/initialize_templates.py` — not imported anywhere
- Audit `app/ai/utils/` subdirs (`chat/`, `game/`, `audio/`) — may be unused
- Clean up `app/game_data/` — 100+ generated board JSON files, consider pruning or gitignoring
- Add `concurrently` as a root devDependency (the `dev` script references it but it's not installed)
