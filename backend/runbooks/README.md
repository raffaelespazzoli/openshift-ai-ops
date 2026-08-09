# OpenShift Runbooks

This directory contains OpenShift operational runbooks that are chunked,
embedded, and indexed into pgvector at application startup for RAG-based
retrieval during diagnosis.

## Adding Runbooks

Place markdown (`.md`) files in this directory or in subdirectories.
The ingestion pipeline will recursively scan for all `.md` files.

### Format Guidelines

- Use heading hierarchy (`#`, `##`, `###`) to structure content — the
  chunker splits on heading boundaries and preserves the hierarchy.
- Keep individual sections under ~500 tokens for optimal chunk sizing.
- Include symptoms, diagnosis steps, and resolution procedures.

### Example Structure

```
runbooks/
  alerts/
    kube-pod-crash-looping.md
    node-memory-pressure.md
  storage/
    pvc-stuck-pending.md
  network/
    dns-resolution-failure.md
```

## How Ingestion Works

1. On app startup, the ingestion pipeline scans this directory.
2. Each `.md` file is split into chunks (~512 tokens, 64-token overlap).
3. Chunks are embedded via the configured embedding endpoint.
4. Embeddings are upserted into the `runbook_chunks` pgvector table.
5. During diagnosis, the orchestrator searches for relevant chunks by
   semantic similarity to the alert context.

Runbooks are bundled at container build time. To refresh the corpus,
rebuild the container image (per AD-13).
