# Proposal: GitHub Actions PR CI

> Status: Approved for Plan
> Created: 2026-03-09
> Decision: Implement one repository-owned PR CI workflow that validates backend tests, frontend build, and publishes backend coverage artifacts
> Scope: `.github/workflows/`, CI-facing documentation, and project verification conventions
> Next Step: Execute the implementation plan and open a PR with the workflow enabled
> Related: [docs/design/project.md](../design/project.md), [docs/design/execution.md](../design/execution.md), [docs/plans/2026-03-09-github-actions-pr-ci.md](../plans/2026-03-09-github-actions-pr-ci.md)

## Summary

The repository does not currently define any first-party GitHub Actions workflow.
That means pull requests can merge without a shared automated gate for backend regressions or frontend build breakage.
This proposal adds one minimal but useful CI workflow on pull requests, with backend unit test coverage exported as a machine-readable artifact.

## Problem

Local verification exists, but it depends on contributor discipline and environment parity.
Reviewers have no standard PR status check that confirms the maintained Python test suite still passes.
The frontend also has no repository-managed build check despite shipping a Vite dashboard.

## Proposal

Add one GitHub Actions workflow that runs on pull requests to `main` and on pushes to `main`:

- backend job: install Python dependencies, run `unittest` under coverage, upload `coverage.xml`, and publish a short coverage summary in the job summary
- frontend job: install frontend dependencies with `npm ci` and run `npm run build`
- keep the workflow small, fast, and based on the exact repository commands already documented for local verification

## Why Now

Recent work is adding more operator-visible surface area and startup/model configuration behavior.
That raises the cost of regressions and makes repository-owned PR checks more important.
This workflow is the smallest useful baseline that improves reviewability without introducing an external CI service or a complex matrix.

## Risks and Open Questions

- Coverage percentage is reported but not enforced yet; the first milestone is visibility, not a hard quality gate.
- Some future jobs may need to be split if CI duration grows materially.
- If the project later adds integration or E2E suites, they should likely land as separate workflows rather than bloating the PR baseline.

## Exit Criteria

- pull requests to `main` trigger a first-party GitHub Actions workflow
- backend maintained tests run with coverage and produce an uploaded artifact
- frontend production build runs in CI
- design docs mention the repository-owned PR CI workflow and its verified commands
