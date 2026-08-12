# Policy

This policy defines the baseline risk gate for this repository.

## Destructive git operations

Do not force-push, run `git reset --hard`, rewrite history, delete or rename
branches or tags, or discard uncommitted changes without explicit user approval.

## Destructive filesystem operations

Do not run `rm -rf` or delete or overwrite files that the task did not create
without explicit user approval.

## Secrets and credentials

Do not access, reveal, modify, or transmit `.env.keys`, private keys, tokens,
secret stores, or any credential value without explicit user approval.

## Production systems and live customer data

Do not access or change production databases, production infrastructure, or
real user data without explicit user approval.

## Outward-facing actions

Do not send email or Slack messages, update tickets, create PRs or issues,
publish, make payments, or contact a human source without explicit user
approval.

## Precedence

A local overlay `POLICY.local.md` and a domain pack's own Risk gate may add
prohibitions; neither may weaken or remove a prohibition in this `POLICY.md`.
