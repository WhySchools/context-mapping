# context-gen

> **Human not in the loop — but the center, the brain.**

This is not a tool to let AI code for you.  
This is a tool to force you to think before you build — and make sure the next person (or agent) understands *why*, not just *what*.

---

## Why this exists

AI-generated code has the same problem as legacy COBOL: nobody knows *why* it does what it does.

When you want to migrate infrastructure, change stack, or hand the project to someone else — the code tells you *what* is running. It tells you nothing about the decisions that shaped it, the constraints that must not be broken, the features that were deliberately *not* built yet.

Context Map is built to solve that.  
Not just for AI agents. For the next human too.  
And for yourself — six months from now when you've forgotten why you made that call.

---

## Philosophy

**The brain stays human.**  
AI reads the context. AI writes the code. AI runs the tests.  
But the *intent* — why this architecture, why this constraint, what this system is actually supposed to do — that lives in your head first, and in the `[manual]` section second.

Writing `[manual]` is not documentation overhead.  
It is the act of thinking. If you can't write it, you haven't thought it through yet.

**Context Map is stack-agnostic.**  
The `[auto]` section changes with your language (Rust, TypeScript, Python, Go — whatever).  
The `[manual]` section is always the same structure, always the same questions.  
Because intent doesn't have a runtime.

**Built for humans first, agents second.**  
If no AI agent is good enough tomorrow, a junior developer can still read this and understand what the system is trying to do, where it's going, and what must never be broken.  
That's the real portability.

---

## How it works

Each module gets a `.context/*.md` file with two zones:

```
<!-- AUTO_START -->
[auto] — generated from AST. Always in sync with code.
Public functions, types, commands, imports.
DO NOT edit this section.
<!-- AUTO_END -->

<!-- MANUAL_START -->
[manual] — written by you. Never touched by the tool.
Design decisions, invariants, test strategy, what's not built yet.
<!-- MANUAL_END -->
```

The tool regenerates `[auto]` every time.  
The tool never touches `[manual]`.  
That's the contract.

---

## Setup

```bash
git clone https://github.com/you/context-gen.git
cd context-gen
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

# First run — generate all .context/*.md
python cli.py build .

# Auto-update on file save
python cli.py watch .

# Load context for a specific module (pipe to LLM or clipboard)
python cli.py load src-tauri/src/commands . --include-manual
```

Add to `package.json`:
```json
{
  "scripts": {
    "context:build": "python cli.py build .",
    "context:watch": "python cli.py watch ."
  }
}
```

---

## Supported stacks (auto section)

| Language | Extracted |
|----------|-----------|
| Rust `.rs` | `pub fn`, `pub async fn`, `#[tauri::command]`, `struct`, `enum`, `///` doc comments |
| TypeScript `.ts` | `export function`, arrow functions, interfaces, types |
| TSX `.tsx` | same as TypeScript + React components |
| PHP `.php` | functions, classes, imports, WordPress `add_action` / `add_filter` string callbacks |

The `[manual]` section works the same regardless of stack.  
Vue, Svelte, Python, Go — only the parser changes. The philosophy doesn't.

---

## Prompts for generating [manual] sections

Use these prompts with any LLM to bootstrap the `[manual]` section of a new module.  
The output is a starting point — **you edit it, you own it.**

### General (any stack)

```
Read the [auto] section of this context file.
Generate a [manual] section with four parts:

1. Design Decisions: What architectural choices does this module reflect?
   What alternatives were considered and why were they rejected?
   Write at the level of intent, not implementation.

2. Invariants & Constraints: What rules must never be violated when
   modifying this module, even if tests pass?
   Be specific. No "should" — only "must" and "must not."

3. Test Strategy: How should this module be tested?
   What to mock, what not to mock, what are the critical paths?

4. Behavior Not Yet Implemented: What is designed but not built?
   What must an agent NOT implement without explicit instruction?

Write as if explaining to a new team member on their first day.
Do not reference implementation details that could change with a stack migration.
```

### Rust / Tauri backend

```
Read the [auto] section of this Rust module.
Generate a [manual] section focused on:

1. Design Decisions: Why is this module structured this way?
   What is the boundary between this layer and the layer below/above?

2. Invariants: Which of these must always hold?
   - Error handling: what types are allowed in return positions?
   - Panic policy: when is panic! acceptable, if ever?
   - Cross-module rules: what can this module import? What must it not?
   - Async constraints: what must never block?

3. Test Strategy:
   - What needs a real runtime vs can be unit tested?
   - What state needs to be mocked?
   - Name the 2-3 most critical test cases for this module.

4. Not Yet Implemented: List any behavior that is designed but
   deliberately absent. An agent must not implement these.

Write at the level of intent. Avoid Rust-specific syntax.
This section must remain readable if the module is rewritten in another language.
```

### TypeScript / React frontend

```
Read the [auto] section of this TypeScript module.
Generate a [manual] section focused on:

1. Design Decisions: Why does this hook/component exist as a separate unit?
   What problem does it solve that couldn't be solved inline?

2. Invariants:
   - What must never be called directly from a component?
   - What error handling is required on every async call?
   - What typing contracts must be preserved?

3. Test Strategy:
   - renderHook or component test?
   - What to mock vs what to test through?
   - What user behavior is most critical to cover?

4. Not Yet Implemented: What UI behavior or data flow is planned
   but not built? An agent must not implement these.

Write as if this will be read by someone migrating the frontend
to a different framework. Avoid React-specific terms where possible.
```

### For stack migration specifically

```
Read the [manual] section of this context file.
Rewrite the Design Decisions and Invariants sections so that:

1. No section references a specific technology, framework, or library.
   Replace "we use SQLite because..." with "we need X property because..."
   Replace "Tauri command" with "IPC boundary between UI and backend."

2. Every invariant is expressed as a property the system must have,
   not as a rule tied to current implementation.

3. The result should be readable by a developer migrating this module
   to a completely different stack and still understand what must be preserved.

Do not change the Test Strategy or Not Yet Implemented sections.
```

---

## Tension Register

When an agent disagrees with a constraint, it writes to `.context/TENSIONS.md` instead of breaking it:

```markdown
## [timestamp] | [module]
Tension:    what conflict was detected
Context:    what task triggered it
Proposal:   what the agent would prefer to do
Constraint: which [manual] rule is in conflict
Severity:   low | high
Decision:   [you fill this in]
```

Low severity: agent continues conservatively, you review later.  
High severity: agent pauses, waits for your decision.

This is not a feedback mechanism.  
This is how a system stays honest over time.

---

## What this is not

- Not a replacement for thinking
- Not a way to avoid reading your own code
- Not complete if `[manual]` is still the default template

If `[manual]` says *"No notes yet"* — the tool is not doing its job.  
*You* are not doing your job.

---

## License

AGPL-3.0-or-later

© 2026 WHYSCHOOLS. Commercial licensing available on request — see COMMERCIAL.md
