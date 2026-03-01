# memory-mcp

MCP server for AI long-term memory — Let AI remember across sessions!

## Overview

This MCP server provides long-term memory capabilities for AI assistants using **SQLite + numpy** for vector storage. Memories are stored with semantic embeddings (intfloat/multilingual-e5-small), enabling intelligent recall based on context, emotion, and time.

**Backend: SQLite + numpy** (no external vector database required — standard library + existing deps only)

## Features

- **Semantic Memory Storage**: Save memories with emotion tags, importance levels, and categories
- **Semantic Search**: Find relevant memories using natural language queries (cosine similarity via numpy)
- **BM25 Hybrid Re-ranking**: Bigram BM25 index for Japanese/multilingual text (Phase 9)
- **Context-based Recall**: Automatically recall memories relevant to the current conversation
- **Divergent Recall**: Associative graph exploration for creative, non-obvious memory retrieval
- **Working Memory Buffer**: Fast access to recently activated memories
- **Episodic Memory**: Group memories into episodes (experiences, events)
- **Visual Memory**: Save memories with camera images
- **Audio Memory**: Save memories with audio transcripts
- **Theory of Mind (ToM)**: Perspective-taking tool for understanding others' feelings
- **Coactivation Weights**: Symmetric co-activation table for associative strength
- **Persistent Storage**: Memories stored in a single SQLite file, easy to backup and migrate

## Installation

```bash
cd memory-mcp
uv sync
uv run memory-mcp
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MEMORY_DB_PATH` | `~/.claude/memories/memory.db` | SQLite database path |

## Migrating from ChromaDB

If you have existing memories in ChromaDB (older versions used `~/.claude/memories/chroma`), run the migration script:

```bash
cd memory-mcp

# Install chromadb temporarily (only needed for migration)
uv add --dev chromadb

# Run migration
uv run python scripts/migrate_chroma_to_sqlite.py \
    --source ~/.claude/memories/chroma \
    --dest ~/.claude/memories/memory.db

# Remove chromadb after migration
uv remove --dev chromadb
```

The script migrates:
- All memories (content, embeddings, metadata)
- Coactivation weights
- Episodes

> **Note**: The migration script temporarily installs `chromadb` as a dev dependency. It is not needed for normal operation and should be removed after migration.

## Tools

### remember

Save a memory to long-term storage.

```json
{
  "content": "Today I learned about SQLite performance tuning",
  "emotion": "excited",
  "importance": 4,
  "category": "technical"
}
```

### search_memories

Search memories by semantic similarity with optional filters.

```json
{
  "query": "things I learned about databases",
  "n_results": 5,
  "category_filter": "technical",
  "emotion_filter": "excited"
}
```

### recall

Recall relevant memories based on conversation context.

```json
{
  "context": "We were discussing database optimization",
  "n_results": 3
}
```

### recall_divergent

Divergent associative recall — explores memory graph to surface non-obvious connections.

```json
{
  "context": "late night coding session",
  "n_results": 5,
  "max_branches": 3,
  "max_depth": 3,
  "temperature": 0.7
}
```

### recall_with_associations

Recall memories along with their linked memories.

```json
{
  "context": "first time I saw the night sky",
  "n_results": 3,
  "chain_depth": 2
}
```

### list_recent_memories

List the most recent memories.

```json
{
  "limit": 10,
  "category_filter": "memory"
}
```

### get_memory_stats

Get statistics about stored memories (count by category, emotion).

### get_working_memory

Get recently activated memories from the fast working memory buffer.

```json
{ "n_results": 10 }
```

### refresh_working_memory

Refresh the working memory buffer with frequently accessed memories from long-term storage.

### consolidate_memories

Run a manual replay/consolidation cycle to strengthen associations.

```json
{
  "window_hours": 24,
  "max_replay_events": 200,
  "link_update_strength": 0.2
}
```

### save_visual_memory

Save a memory with a camera image.

```json
{
  "content": "Saw a beautiful sunset from the balcony",
  "image_path": "/tmp/wifi-cam-mcp/capture_20260220_183000.jpg",
  "camera_position": { "pan_angle": -30, "tilt_angle": 20 },
  "emotion": "moved",
  "importance": 4
}
```

### save_audio_memory

Save a memory with an audio transcript.

```json
{
  "content": "User said good morning",
  "audio_path": "/tmp/audio.wav",
  "transcript": "Good morning! How are you?",
  "emotion": "happy"
}
```

### create_episode

Group memories into a named episode.

```json
{
  "title": "Morning sky search",
  "memory_ids": ["id1", "id2", "id3"],
  "participants": ["コウタ"],
  "auto_summarize": true
}
```

### search_episodes

Search through past episodes.

```json
{ "query": "night sky", "n_results": 5 }
```

### get_episode_memories

Get all memories in an episode in chronological order.

```json
{ "episode_id": "ep-xxx" }
```

### link_memories

Create a causal or relational link between two memories.

```json
{
  "source_id": "mem-a",
  "target_id": "mem-b",
  "link_type": "caused_by",
  "note": "The sunset triggered a philosophical thought"
}
```

### get_causal_chain

Trace the causal chain of a memory forward or backward.

```json
{
  "memory_id": "mem-a",
  "direction": "forward",
  "max_depth": 3
}
```

### recall_by_camera_position

Recall memories associated with a camera direction (pan/tilt angle).

```json
{
  "pan_angle": -30,
  "tilt_angle": 20,
  "tolerance": 15
}
```

### tom

Theory of Mind: perspective-taking tool. Call this before responding to understand what the other person might be feeling.

```json
{
  "situation": "User suddenly went quiet after showing me the photo",
  "person": "コウタ"
}
```

### get_association_diagnostics

Inspect associative expansion diagnostics without committing activation updates.

```json
{ "context": "night sky", "sample_size": 20 }
```

### sleep

Memory consolidation — compress similar old memories, decay low-retention ones, forget unimportant ones. Protected memories (high importance, strong emotions, first experiences, episode members) are never deleted.

```json
{
  "dry_run": true,
  "min_age_days": 14,
  "similarity_threshold": 0.85
}
```

**Three phases:**

1. **Merge** — Group old memories in the same category with cosine similarity > threshold, combine into a single summary memory
2. **Decay** — Lower the importance of memories with low retention scores (but never below 1)
3. **Forget** — Delete memories that are importance=1, emotion=neutral, no episode, old enough, and rarely accessed

**Protection rules (never touched):**
- `importance >= 4`
- Emotion is `happy`, `moved`, `excited`, or `surprised`
- Content contains "初めて" / "はじめて" / "first time" (first experiences)
- Episode members (deletion only; decay is allowed)

**Retention score formula:**
```
retention = (importance/5)*0.3 + emotion_strength*0.2 + recency*0.3 + access_frequency*0.2
```
- `recency = exp(-age_days / 30)`
- `access_frequency = min(1.0, access_count / 10)`

**Thresholds (SleepConfig defaults):**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `min_age_days` | 14 | Memories younger than this are not eligible |
| `similarity_threshold` | 0.85 | Cosine similarity required for merge grouping |
| `decay_retention_threshold` | 0.4 | Retention score below this triggers decay |
| `forget_min_age_days` | 14 | Minimum age for forgetting |
| `forget_max_access` | 3 | Maximum access count for forgetting |
| `protected_importance` | 4 | Importance >= this is always protected |
| `protected_emotions` | happy, moved, excited, surprised | These emotions are always protected |

**Cron setup (recommended: run nightly):**

```bash
# crontab -e
# 毎日 AM 4:00 に sleep を実行（dry_run=false）
0 4 * * * cd /path/to/memory-mcp && uv run python -c "
import asyncio, json
from memory_mcp.config import MemoryConfig
from memory_mcp.store import MemoryStore
from memory_mcp.sleep import SleepEngine

async def main():
    store = MemoryStore(MemoryConfig.from_env())
    await store.connect()
    try:
        engine = SleepEngine(store)
        stats = await engine.run(dry_run=False)
        print(json.dumps({
            'merged': len(stats.merged),
            'decayed': len(stats.decayed),
            'forgotten': len(stats.forgotten),
            'protected': stats.protected,
        }))
    finally:
        await store.disconnect()

asyncio.run(main())
" >> /var/log/memory-sleep.log 2>&1
```

## Emotion Labels

`happy`, `sad`, `surprised`, `moved`, `excited`, `nostalgic`, `curious`, `neutral`

## Category Labels

`daily`, `philosophical`, `technical`, `memory`, `observation`, `feeling`, `conversation`

## Claude Code Integration

Add to your `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "memory": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/memory-mcp", "memory-mcp"]
    }
  }
}
```

## Development

```bash
# Install dev dependencies
uv sync --all-extras

# Run tests
uv run pytest

# Lint
uv run ruff check .

# Type check
uv run mypy src/memory_mcp/ --ignore-missing-imports
```

## Architecture

```
memory-mcp/
├── src/memory_mcp/
│   ├── server.py       # MCP server (tool handlers)
│   ├── store.py        # SQLite MemoryStore (main backend)
│   ├── vector.py       # numpy cosine similarity utilities
│   ├── embedding.py    # intfloat/multilingual-e5-small embedding
│   ├── bm25.py         # Bigram BM25 index for hybrid re-ranking
│   ├── hopfield.py     # Hopfield network for associative recall
│   ├── episode.py      # EpisodeManager (delegates to MemoryStore)
│   ├── tom.py          # Theory of Mind tool
│   ├── desire.py       # Desire system
│   ├── config.py       # Configuration
│   └── types.py        # Emotion / Category enums
├── scripts/
│   └── migrate_chroma_to_sqlite.py  # ChromaDB → SQLite migration
└── tests/
```

## License

MIT
