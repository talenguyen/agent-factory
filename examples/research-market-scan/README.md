# Research market scan

From this directory, run:

```bash
../../bin/factory run
../../bin/verify-research --workspace .
```

First retrieve real public sources, save their raw snapshots under `snapshots/`,
and write `report.md`. Do not invent citations. `sources.jsonl` has one real
record per line; use this shape after retrieval (replace every placeholder):

```json
{"key":"source-key","url":"https://real-source.example/","snapshot":"snapshots/source-key.html","excerpt":"verbatim bytes from that snapshot","sha256":"sha256 of the snapshot"}
```
