# Tensions Register

> Agent ghi vào đây khi detect conflict giữa task reasoning và [manual] constraint.
> Human điền `Decision`. Không để entry ở trạng thái OPEN quá 1 sprint.

---

## 2026-05-16 | schema.py

**Status**: RESOLVED

Tension:    `signature()` hardcode Rust syntax cho mọi language
Context:    Chuẩn bị thêm PHP parser — cần render đúng PHP function signature
Proposal:   Thêm `language` parameter vào `signature()`
Constraint: Không có constraint [manual] nào cấm — đây là bug fix, không phải feature
Severity:   low
Decision:   Fix ngay. Backward compatible vì default `language="rust"`.
Rationale:  Bug ảnh hưởng correctness của [auto] section. TypeScript module hiển thị Rust syntax là sai về mặt semantics, không chỉ cosmetic.

---

## 2026-05-16 | cli.py → _process_directory

**Status**: RESOLVED

Tension:    Thêm PHP = thêm `elif php_files` vào `_process_directory`
Context:    PHP parser cần được dispatch từ `_process_directory`
Proposal:   Refactor sang Registry pattern trước khi thêm PHP
Constraint: Không có constraint cấm refactor — nhưng tốn thời gian hơn quick fix
Severity:   low
Decision:   Refactor trước. Technical debt của if/elif sẽ tái xuất hiện với mọi language mới.
Rationale:  "Thêm language mới không cần sửa cli.py" là invariant tốt hơn để giữ từ đầu. Cost refactor bây giờ thấp hơn nhiều so với sau khi có 4–5 language.

---

## 2026-05-16 | cli.py → load command

**Status**: RESOLVED

Tension:    `load` command in console output ra stdout, làm bẩn pipe
Context:    Agent workflow dùng `context-gen load ... | pbcopy` hoặc pipe vào LLM
Proposal:   Suppress console output trong `load`, dùng stderr cho errors
Constraint: Không có constraint cấm — đây là functional bug
Severity:   high
Decision:   Fix. `stdout` của `load` phải sạch tuyệt đối.
Rationale:  Noise trong stdout = corrupt LLM prompt. Agent không có cách filter noise này. Bug silent nhưng impact cao.

---

## 2026-05-16 | php_parser.py → WordPress hooks

**Status**: RESOLVED

Tension:    `add_action($hook, [$this, 'method'])` — callback là array, không phải string literal
Context:    Detect WP hooks làm "IPC bridge" tương đương Tauri commands
Proposal:   Chỉ handle string literal callbacks, bỏ qua array/closure callbacks
Constraint: Không có constraint — cần define scope
Severity:   low
Decision:   Accept limitation. Ghi rõ trong docstring. String literal là pattern phổ biến nhất trong WP plugins. Array callback và closure là advanced pattern, có thể handle ở V3.
Rationale:  Perfect là kẻ thù của done. 80% coverage của string callbacks đã đủ useful. False negative (bỏ sót hook) tốt hơn false positive (detect sai).

---

## OPEN | global_context.py → PHP stack detection

**Status**: OPEN

Tension:    `generate_global_context()` không detect PHP — GLOBAL.md không list PHP trong Tech Stack
Context:    Sau khi thêm php_parser, WP projects vẫn không thấy "PHP" trong stack overview
Proposal:   Thêm `has_php = any(root.glob("**/*.php"))` và skip vendor/
Constraint: Chưa có constraint rõ ràng
Severity:   low
Decision:   [human fill in]
