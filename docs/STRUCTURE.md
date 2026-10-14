# Documentation Structure

All 13 initial topic folders exist from day one. Their `README.md` files are instructions, not project facts. `overview/` and `governance/` are core entry points; the others are optional and are filled in only when the project has that area.

| Folder | Marker | Contents |
| --- | --- | --- |
| `overview/` | core | purpose, scope, terminology and project map |
| `architecture/` | optional | components, data, integrations and technical contracts |
| `product/` | optional | users, requirements and product behavior |
| `design/` | optional | UX, visual rules and accessibility |
| `engineering/` | optional | conventions, development, builds and technical checks |
| `security/` | optional | access, threats and security rules |
| `privacy/` | optional | personal data, retention and processors |
| `qa/` | optional | test strategy, scenarios and acceptance criteria |
| `operations/` | optional | environments, releases, monitoring and incidents |
| `procedures/` | optional | repeatable, verifiable instructions |
| `decisions/` | optional | accepted decisions with context and consequences |
| `governance/` | core | ownership, reviews and process rules |
| `status/` | optional | temporary current state with verification date |

## Adding a future folder

1. Check whether the topic already has a canonical home. A new folder is warranted when it has a separate owner, lifecycle or several expected documents that do not clearly belong in an existing folder.
2. Choose a short lowercase name with hyphens. Create `README.md` with a `core` or `optional` marker, purpose, inclusions, exclusions, owner/review and links to related areas.
3. Add the folder to this table and each actual canonical document to `00-index.md`. Do not copy authority, lifecycle or promotion rules outside `governance/`.
4. When moving content, update all entry points and leave a reference when history requires it. Do not delete historical evidence without a separate decision.

Possible future folders include `integrations/`, `research/`, `api/`, `data/` or `agents/`. They are not required for every project. Add new memory types in `memory/` using the same principle and describe them in `memory/README.md`.
