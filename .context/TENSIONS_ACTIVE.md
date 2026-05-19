# Tensions — Active

> Chỉ chứa Status: RESOLVED_ACTIVE entries của milestone hiện tại.
> Agent đọc file này với tag filter (xem AGENTS.md Section 3.1).
> Move sang TENSIONS_HISTORY.md chỉ khi human approve milestone transition.

---

## 2026-05-16 | schema.py
Status:     RESOLVED_ACTIVE
Tension:    `signature()` hardcode Rust syntax cho mọi language
Context:    Chuẩn bị thêm PHP parser — cần render đúng PHP function signature
Proposal:   Thêm `language` parameter vào `signature()`
Constraint: Không có constraint [manual] nào cấm — bug fix
Severity:   low
Tags:       schema, parser
Milestone:  V0
Resolved:   2026-05-16
Decision:   Fix ngay. Backward compatible vì default `language="rust"`.

---

## 2026-05-16 | cli.py → _process_directory
Status:     RESOLVED_ACTIVE
Tension:    Thêm PHP = thêm `elif php_files` vào `_process_directory`
Context:    PHP parser cần được dispatch từ `_process_directory`
Proposal:   Refactor sang Registry pattern trước khi thêm PHP
Constraint: Không có constraint cấm refactor
Severity:   low
Tags:       cli, registry, parser
Milestone:  V0
Resolved:   2026-05-16
Decision:   Refactor trước. Technical debt của if/elif sẽ tái xuất hiện với mọi language mới.

---

## 2026-05-16 | cli.py → load command
Status:     RESOLVED_ACTIVE
Tension:    `load` command in console output ra stdout, làm bẩn pipe
Context:    Agent workflow dùng `context-gen load ... | pbcopy` hoặc pipe vào LLM
Proposal:   Suppress console output trong `load`, dùng stderr cho errors
Constraint: Functional bug — stdout phải sạch tuyệt đối
Severity:   high
Tags:       cli, stdout
Milestone:  V0
Resolved:   2026-05-16
Decision:   Fix. `stdout` của `load` phải sạch tuyệt đối.

---

## 2026-05-16 | php_parser.py → WordPress hooks
Status:     RESOLVED_ACTIVE
Tension:    `add_action($hook, [$this, 'method'])` — callback là array, không phải string literal
Context:    Detect WP hooks làm IPC bridge tương đương Tauri commands
Proposal:   Chỉ handle string literal callbacks, bỏ qua array/closure callbacks
Constraint: Cần define scope
Severity:   low
Tags:       php, parser, woocommerce
Milestone:  V0
Resolved:   2026-05-16
Decision:   Accept limitation. String literal là pattern phổ biến nhất trong WP plugins.

---

## 2026-05-17 | global_context.py → PHP stack detection
Status:     RESOLVED_ACTIVE
Tension:    `generate_global_context()` không detect PHP
Context:    Sau khi thêm php_parser, WP projects không thấy PHP trong stack overview
Proposal:   Thêm `has_php = any(root.glob("**/*.php"))` và skip vendor/
Constraint: Chưa có constraint rõ ràng
Severity:   low
Tags:       php, global-context
Milestone:  V0
Resolved:   2026-05-17
Decision:   Already fixed. `_has_source_file()` đã handle skip_dirs đúng cách.

---
