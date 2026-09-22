---
name: token-efficiency
description: >-
  Habits for keeping this session's context small without losing correctness: symbol navigation
  over whole-file reads, filtered tool output, no redundant re-reads, on-demand references. Use
  throughout any session in this repo, not just when context feels large.
---

# Token Efficiency

The goal is a smaller context, never a less correct answer. If a shortcut here would risk a
wrong result or a retry, skip the shortcut.

## Exploration

- Prefer Serena's symbol tools (find symbol, find references, symbol overview) or the `LSP` tool
  over reading whole source files, when the target is a known symbol.
- Read only the file/line range on the causal path (see the `safe-change` skill). Don't open a
  file "to be safe" if search already answered the question.
- Don't re-read a file this session already read and hasn't changed since — trust prior context
  or a targeted diff instead.
- When several files might be relevant, search (`rg`, LSP `workspaceSymbol`) before opening any
  of them, and open only the ones the search confirms matter.

## Output volume

- Filter shell/test output before it enters context: grep for the failing test name, the error
  line, the specific assertion — don't paste a full pytest/vitest run when three lines answer it.
- When a command would produce huge output, filter it **at the command level** (pipe through
  `grep`/`head`/`tail`, pass a narrower path or `-k`/`::name` selector) rather than letting the
  full output land in context to be summarized afterward — the unfiltered version already cost
  the tokens by the time a summary could save them.
- Never inject a full PDF, large JSON dump, training artifact, or validation report into context.
  Query it (page count, key lookup, `jq`/`rg` extraction, a small script) and read only the
  extracted piece.
- For a repeated deterministic check (parsing the same PDF twice, recomputing the same metric),
  write a small script once and reuse its output rather than re-deriving it via more tool calls.

## Test scope

- Run the narrowest test tier per the `test-select` skill before a broader suite. Escalate only
  when blast radius requires it, never "to be sure" after a narrower tier already passed.

## Delegated work

When dispatching a subagent for mechanical, well-scoped work (a broad file search, a repetitive
lookup), prefer a cheaper model for that subagent; reserve the default/heavier model for
judgment-heavy work (root-causing, architectural decisions, anything touching the prediction
contract or ML methodology rules). Don't downgrade a subagent's model when the task requires
the judgment this repo's rules call for (e.g. `ml-audit`, `safe-change` step 6).

## Session-level habits

- Keep `CLAUDE.md` and rule files stable. Don't rewrite them mid-task to record transient state —
  that belongs in your final report or a plan, not in always-loaded instructions.
- Large reference material (long checklists, full API dumps, historical audit output) belongs
  outside `SKILL.md` bodies — in a `references/` file loaded only when actually needed, not
  inline in frontmatter-adjacent text that loads every time the skill activates.
- Recommend `/compact` at a logical phase boundary (a plan step finished, a verification pass
  complete) — not mid-investigation, and not as a reflex when a response merely looks long.
- Before recommending or running `/compact`, state: decisions made so far, files modified,
  unresolved issues, and current validation status. Losing any of these to save tokens is a
  false economy — it causes rework.

## The one rule that overrides the rest

Never trade a correctness risk for a token saving: not by skipping verification, not by
summarizing away a detail that matters, not by guessing instead of checking. A retry from a
wrong shortcut costs more context than the read it skipped.
