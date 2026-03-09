# Plan: GitHub Actions PR CI

> Status: Approved
> Created: 2026-03-09
> Completed:
> PR:
> Proposal: [docs/proposals/2026-03-09-github-actions-pr-ci.md](../proposals/2026-03-09-github-actions-pr-ci.md)

## Summary

Add one repository-managed GitHub Actions workflow that validates backend unit tests with coverage and frontend production build for pull requests and pushes to `main`.

## Scope

- create `.github/workflows/pr-ci.yml`
- run maintained backend tests under coverage and upload `coverage.xml`
- run frontend install + production build
- keep workflow commands aligned with documented local verification commands
- update authoritative design docs to describe the new CI baseline

## Steps

1. Add a proposal and plan documenting the intended PR CI scope.
2. Create a GitHub Actions workflow with backend and frontend jobs.
3. Verify the workflow file shape locally as far as practical by running the same backend and frontend commands.
4. Update current-state design docs so CI expectations are part of the documented system.
