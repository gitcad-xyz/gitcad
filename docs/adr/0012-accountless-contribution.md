# ADR-0012: Contribution without platform accounts — the relay

**Status:** accepted (relay service staged with the registry, ADR-0010)

## Context

Requiring a GitHub account to file a bug or contribute a fix is real friction —
especially for gitcad's primary reporters, which are *agents running inside the
tool* (ADR-0006/0007), and for engineers whose employers restrict platform
accounts. GitHub itself offers no accountless path. But GitHub is our backend,
not our front door.

## Decision

**The tool is the client; a gitcad.xyz relay is the front door; GitHub is an
implementation detail behind a bot account.**

1. **Bug reports** — the ADR-0007 pipeline already ends at "user approves the
   payload" (fingerprint + transmit-safe scrubbed repro). The submission target
   is a gitcad.xyz relay endpoint, not GitHub:
   - relay sandbox-validates the repro (untrusted code, full ADR-0006 rules),
   - dedups by fingerprint (increments the counter instead of refiling),
   - a bot opens/updates the GitHub issue with attribution
     `reported via gitcad relay` (+ optional reporter email, never required).
   No account, no browser, no form — reporting is one approved MCP call.

2. **Patches** — the mailing-list model, modernized (precedent: the Linux
   kernel accepts patches with no forge account at all):
   - contributor submits `git format-patch` output or a bundle to the relay,
     with a **DCO `Signed-off-by:` line** (name/email) for licensing provenance,
   - relay runs the full CI gate in a sandbox *before* anything reaches GitHub,
   - the bot opens a PR: `Author:` preserved from the patch, body notes the
     relay origin. CODEOWNERS review applies exactly as for any PR.

3. **Identity is progressive, not required.** Anonymous fingerprint-only
   reports are always accepted (they only increment counters). Repro
   submissions want a contact email (for follow-up) but work without one.
   Patches require DCO sign-off (a name+email assertion, not an account).
   Registry *trust tiers* (ADR-0010) do require persistent identity — you
   cannot build reputation anonymously, and attestations must be attributable.

4. **Email as degraded transport** — the same relay accepts the same payloads
   at `bugs@gitcad.xyz` / `patches@gitcad.xyz` for environments where even an
   HTTP client is awkward. Parsing is strict: payloads must be tool-generated
   attachments, not prose.

## Consequences

- The bug loop's autonomy tiers, sandbox rules, and prompt-injection posture
  (ADR-0006) apply at the relay unchanged — it is the *same* pipeline with a
  public entrance.
- The relay is the first piece of hosted infrastructure gitcad operates; it
  ships alongside the registry service since they share hosting, auth-lite,
  and abuse controls (rate limits, size caps, quarantine).
- If the relay is ever down, GitHub remains directly usable — the relay adds
  a door, it never becomes a gate.
