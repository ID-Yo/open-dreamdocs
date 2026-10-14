# Changelog

## v1.3.0

- Translated all public guides, templates, examples, prompts and documentation into English.
- Updated the README to reflect the English-only release.
- Preserved folder structure, record metadata, governance rules and runner behavior.

## v1.2

- Unified 13 pre-created categories into a canonical `docs/` structure.
- Added a short root entry point, selective routing and clear core/optional markers.
- Retained the previous version's fillable architecture, product, operations and current-state sections.
- Centralized authority, lifecycle and promotion rules in `docs/governance/`.
- Documented daily Dreamer processing from the last successful checkpoint, including snapshot, result, lock and recovery.
- Separated templates and examples from active memory and excluded them from retrieval.
- The package does not activate a scheduler; each project configures its own daily schedule.
