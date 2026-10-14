# Project Memory

[Documentation](../docs/00-index.md) holds accepted project knowledge. Memory preserves sources, lessons and change candidates. Use the [record format](SCHEMA.md) and verify freshness before consequential actions.

| Folder | Contents |
|---|---|
| [episodes](episodes/README.md) | Meaningful tasks, attempts, errors and outcomes |
| [facts](facts/README.md) | Proposed or accepted facts |
| [procedural](procedural/README.md) | Proposed or accepted repeatable methods |
| [contradictions](contradictions/README.md) | Unresolved and resolved contradictions |
| [archive](archive/README.md) | Terminal records with preserved sources |
| [dreamer](dreamer/README.md) | Isolated runtime state, reports and proposals |

[Dreamer policy](DREAMER_POLICY.md) is the single contract for automatic changes. [config.json](config.json) contains only the daily schedule and optional episode review interval. Null means an unset setting or no deadline. There is no universal TTL.

After meaningful work, record an episode only if it will help future work. Do not record the entire conversation. A new memory type requires a description, README and schema/validator changes; creating a folder does not automatically include it in Dreamer.

Real records and accepted proposals may be versioned in Git. Lock/state/work are local and ignored. Use one persistent checkout for Dreamer; a new clone without state reviews all real records. Review reports for sensitive data before committing.
