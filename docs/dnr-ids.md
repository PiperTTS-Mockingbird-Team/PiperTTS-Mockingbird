# Dynamic Network Request (DNR) Rule IDs

Chrome's declarativeNetRequest API requires that every rule have a unique
numeric `id`. This document outlines how GRAPE allocates those IDs, the ranges
in use, and how to migrate existing extensions to the new scheme.

## ID Ranges

- **1&nbsp;–&nbsp;9,999** – Reserved for static rules shipped in `rules.json` or
  other built‑in rulesets.
- **10,000&nbsp;+** – Runtime user rules. The constant
  `START_ID` (currently `10_000`) marks the beginning of this range.
  Rule IDs are allocated via `RuleIds.allocate`, which ensures IDs are
  unique and tracked across sessions.

Keeping a wide gap between static and dynamic ranges prevents accidental
collisions if the static set grows in the future.

## Allocator API

`src/background/dynamic-rule-manager.js` exposes helpers for managing dynamic rules:

- `applyDynamicRules(sites)` – Builds a rule for each domain in `sites`
  and requests IDs from the shared `RuleIds` allocator.
- `manageDynamicRules(action, sites)` – When `action` is `'apply'`,
  (re)applies rules for `sites` (or the saved blocklist if omitted). When
  `action` is `'clear'`, removes previously created dynamic rules based on
  the IDs stored in `chrome.storage.local.activeRuleIds`.

`enableBlockRules()` and `disableBlockRules()` remain in
`src/background/blocker.js` and toggle the static ruleset while clearing
dynamic rules as needed.

The allocator tracks active IDs and reuses released ones to avoid gaps in the
reserved range.

## Migration Steps

1. **Clear old IDs** – Call `manageDynamicRules('clear')` during startup to remove
   any rules created with earlier schemes.
2. **Store active IDs** – After applying rules, persist their IDs via
  `chrome.storage.local.set({ activeRuleIds })` to enable safe cleanup.
3. **Use the new range** – Ensure all dynamic rules start at `START_ID`
   (10,000) or higher.
4. **Audit other scripts** – Search for hard‑coded rule IDs elsewhere in the
   codebase and update them to use the allocator.

## Common Pitfalls

- **ID collisions** – Overlapping static and dynamic ranges will cause
  `updateDynamicRules` to reject updates. Always respect the reserved range.
- **Forgetting to persist IDs** – Without `activeRuleIds`, stale rules remain
  after reloads and can block sites unexpectedly.
- **Skipping cleanup** – Removing the extension or disabling rules without
  clearing dynamic rules leaves `activeRuleIds` behind, leading to duplicates
  on the next run.
- **Assuming persistence** – Rule IDs are not shared across browsers; syncing
  extensions requires re‑applying rules on each device.

Following these guidelines keeps DNR rule management predictable and avoids
hard‑to‑trace blocking behaviour.

## Snapshot Availability

Newer versions of Chromium expose `chrome.declarativeNetRequest.RuleIds.snapshot()`
to quickly list all dynamic rule IDs. GRAPE checks for this method at runtime and
falls back to `chrome.declarativeNetRequest.getDynamicRules()` when it is not
available, deriving the rule IDs from the returned rules. Extensions targeting
older browsers should use the same pattern.
