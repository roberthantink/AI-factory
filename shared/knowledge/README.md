# Shared Knowledge

This directory holds cross-project knowledge that any agent can access.

Place files here for information that isn't specific to a single project,
for example:

- **Common patterns:** Reusable architectural patterns, design patterns
- **Library docs:** Summaries of frequently used libraries or APIs
- **Lessons learned:** Cross-project learnings that all agents benefit from
- **Style guides:** Organization-wide coding or writing standards

Files can be Markdown (for prose an agent reads as context) or JSONL
(for structured, searchable entries).

This directory is loaded at memory tier L2 via semantic search.
