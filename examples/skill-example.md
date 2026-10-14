---
{
  "id": "skill-example-build",
  "type": "procedural",
  "status": "proposed",
  "project": "example",
  "scope": "build",
  "created_at": "2026-09-24T10:10:00Z",
  "source": [
    "id:ep-example-build"
  ],
  "owner": "example-owner",
  "version": 1,
  "last_verified": null,
  "success_count": 1,
  "failure_count": 0
}
---

# Example Procedure Candidate

## Trigger
Failed build.

## Preconditions
Read-only access to configuration and safe logs.

## Steps
1. Read the exact error.
2. Compare the build command and runtime version with project configuration.
3. Propose the smallest fix.

## Verification
The build and relevant test pass. Deployment occurs only within the authorized scope of a specific task.

One fictitious success illustrates a candidate; it does not justify automatic acceptance.
