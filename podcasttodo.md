# Podcast Integration TODO

**Decision:** Do **not** add a podcast player to this project.

`pdfresearch` is intentionally local-first, code-only corpus-processing infrastructure. A Spotify/media UI would add unrelated network/media surface area to a tool whose value is deterministic local processing, privacy separation and auditable outputs.

## TODO / decision record
- [ ] Keep the CLI/corpus pipeline free of podcast/media dependencies.
- [ ] Do not add Spotify SDKs, embeds, tracking, remote episode lookup or playback code.
- [ ] If Josh wants research-method podcasts, surface them in **Research Atlas**, **ResearchGems** or **JoshHub** instead.
- [ ] Preserve the project's code-only/private-corpus boundary.

## Shared direction
No Josh Podcast Dock implementation belongs in this repository.
