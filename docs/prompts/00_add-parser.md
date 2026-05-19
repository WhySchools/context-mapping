# Prompt: Add Parser Plugin

Use this prompt when adding a new language parser to context-gen.

The goal is to force a proposal-first workflow. Do not edit files during the proposal phase.

```text
You are adding a new language parser plugin to context-gen.

Follow AGENTS.md strictly:
1. Read .context/GLOBAL.md.
2. Read relevant existing parser context files:
   - .context/rust_parser.md
   - .context/ts_parser.md
   - .context/php_parser.md
3. Check .context/TENSIONS.md for OPEN entries.
4. Do not add language-specific dispatch to cli.py, merger.py, or schema.py.
5. Do not make parse_<lang>_directory() recursive.
6. Do not overwrite [manual] sections.
7. Keep load stdout clean.
8. Do not edit files until the human approves the proposal.

Task:
Design a minimal <LANGUAGE> parser plugin using tree-sitter-<LANGUAGE>.

Before coding, produce a proposal with:

1. Package availability
   - Is tree-sitter-<LANGUAGE> available?
   - What is the pip install name?
   - What is the Python import name?

2. AST probe plan
   - Minimal sample code to parse.
   - Node types to inspect.
   - How to identify functions, classes/types, imports, decorators, annotations, or equivalent syntax.

3. Extraction scope
   - Public function rule.
   - Type/class/interface rule.
   - Import rule.
   - IPC/entrypoint bridge equivalent for this ecosystem.
   - Direct limitations accepted for V1.

4. Files expected to change
   - requirements.txt
   - parsers/<lang>_parser.py
   - cli.py import line only
   - .context/parsers_<lang>_parser.md
   - Any tests or fixtures needed

5. Tests
   - Registry includes the plugin.
   - Parser extracts function/class/import.
   - Parser detects the bridge entrypoint.
   - Directory parser is not recursive.
   - Build/load verification passes.
   - [manual] sections are preserved.

6. Tensions
   - Any conflict with existing manual constraints.
   - Whether signature rendering needs a separate proposal.
   - Whether scope exceeds [manual] Behavior chưa implement.

Wait for human approval before implementation.
```

