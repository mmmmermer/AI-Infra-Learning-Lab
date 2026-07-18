# M05 Split Migration Evidence

This directory records the one-time structural migration of the 7,826-line M05 source.

`manifest.json` contains:

- the SHA-256 of the source immediately before splitting;
- the original line range assigned to each of the 13 chapter files;
- each chapter SHA-256 immediately after the lossless split;
- the preserved introduction and completion ranges.

The chapter hashes are migration-time evidence, not permanent checksums. Later answer isolation,
clarification and code-role edits intentionally change the current chapter files. Re-running
`split_m05_textbook.ps1` after this manifest exists returns `already_completed` and does not overwrite
those edits.
