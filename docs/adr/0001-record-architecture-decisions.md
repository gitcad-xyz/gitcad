# ADR-0001: Record architecture decisions

**Status:** accepted

## Context

gitcad is developed largely by agents. Agents drift badly without an explicit,
durable statement of *intent* — they optimize the code in front of them and lose
the plot. Code and auto-generated tests capture *what is*; they do not capture
*why*, or *what must never change*.

## Decision

We keep Architecture Decision Records in `docs/adr/`. Each ADR is short, numbered,
and immutable once accepted (superseded by a new ADR, never edited away). The set
of accepted ADRs plus `CLAUDE.md` is the **durable spec**. Everything else —
issues, snapshot tests, patches — is disposable evidence.

## Consequences

- Agents are pointed at the ADRs and the constitution before touching code.
- Changing a decision means writing a new ADR that supersedes the old one, with a
  human sign-off (see `CODEOWNERS`).
- The core principle running through all ADRs: **separate the durable spec from
  the disposable evidence.**
