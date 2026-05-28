<!--
Thanks for opening a PR! This template is a guide, not a gate — feel
free to delete sections that don't apply. The goal is just to give the
reviewer enough context to merge confidently.
-->

## What does this change?

A one- or two-line summary of the change. Link any related issue
(e.g. `Closes #42`).

## Why?

A few sentences on the problem being solved. Bug? Missing feature?
Refactor for clarity? If it's not obvious from the diff, this part
matters most.

## How does it work?

A quick walkthrough of the approach. Pointers to the key files /
functions if the diff is large.

## Testing

How you verified it works. Examples:

- New unit tests added (which?)
- Existing tests still pass (`pytest`)
- Manual end-to-end run: walked through the wizard, drove an iRacing
  session, etc.
- UI change: include a screenshot or short video if helpful

## Checklist

Quick sanity checks before requesting review:

- [ ] `pytest` passes locally
- [ ] `ruff check .` passes (style is enforced by the linter, not by
      hand)
- [ ] Tests added / updated for any behavior change
- [ ] Public APIs documented in docstrings
- [ ] CHANGELOG.md updated if user-facing

## Anything else?

Caveats, open questions, follow-up work — anything the reviewer should
know that doesn't fit above.
