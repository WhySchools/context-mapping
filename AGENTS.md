# AGENTS.md — context-gen

> Protocol này áp dụng cho agent làm việc trên **context-gen tool itself**.
> Không nhầm với AGENTS.md của dự án *sử dụng* context-gen.

---

## 0. Đọc trước khi làm bất cứ thứ gì

```bash
# Bước 1 — nạp overview
cat .context/GLOBAL.md

# Bước 2 — nạp context của module liên quan đến task
python cli.py load <module_path> . --include-manual

# Bước 3 — kiểm tra tensions đang OPEN
cat .context/TENSIONS.md | grep -A8 "Status.*OPEN"
```

Nếu bước 2 trả về `[manual]` vẫn còn `_Chưa có ghi chú._` → **DỪNG. Hỏi lại human trước khi implement.**

---

## 1. Architecture — những gì agent phải biết

### Plugin Registry

`cli.py` không biết ngôn ngữ nào tồn tại. Nó chỉ loop qua `REGISTRY`.

```
schema.REGISTRY
  ├── "rust"       ← registered bởi parsers/rust_parser.py
  ├── "typescript" ← registered bởi parsers/ts_parser.py
  └── "php"        ← registered bởi parsers/php_parser.py
```

**Thêm language mới**: tạo `parsers/<lang>_parser.py`, gọi `register_plugin()` ở cuối file, thêm `import parsers.<lang>_parser` vào `cli.py`. Không sửa gì khác.

**Không được**: thêm `if language == "..."` vào `cli.py`, `merger.py`, hoặc `schema.py`.

### Merge contract — invariant cốt lõi

```
merger.py chỉ replace vùng AUTO_START...AUTO_END.
Vùng MANUAL_START...MANUAL_END KHÔNG BAO GIỜ bị động vào.
```

Bất kỳ thay đổi nào trong `merger.py` phải verify lại invariant này bằng test.

### `load` command — stdout contract

```bash
python cli.py load <path> . --include-manual | <anything>
```

Stdout của `load` phải sạch tuyệt đối — chỉ có content của context file. Errors đi vào stderr. Không được print bất cứ thứ gì ra stdout trong code path của `load`.

---

## 2. Workflow bắt buộc cho mỗi task

```
1. Đọc .context/GLOBAL.md
2. python cli.py load <module> . --include-manual
3. Kiểm tra TENSIONS.md — có OPEN entry nào liên quan không?
4. Nếu [manual] còn template → DỪNG, hỏi human
5. Đừng viết những gì liên quan đến local environment 
6. Viết test FAIL trước
7. Implement cho đến khi test PASS
8. python cli.py build . --quiet   ← verify tool tự build được
9. Cập nhật .context/<module>.md [manual] nếu có decision mới
10. Nếu detect tension → ghi vào TENSIONS.md trước khi tiếp tục
```

---

## 2.1. Environment

### WSL

Khi làm việc trên Windows và có Debian WSL, ưu tiên chạy toolchain Python trong WSL thay vì Windows Store `python.exe`.

Nếu repo nằm trên Windows filesystem, ví dụ:

```bash
/mnt/d/Github/context-mapping
```

KHÔNG tạo venv bên trong repo bằng:

```bash
python3 -m venv .venv
```

Lý do: venv trên `/mnt/<drive>` có thể fail với lỗi permission kiểu:

```text
Operation not permitted: '/mnt/d/Github/context-mapping/.venv/bin/activate.csh'
```

Phương án đúng: tạo venv trong Linux filesystem, rồi dùng nó khi đứng trong repo Windows mount.

```bash
mkdir -p ~/.venvs
python3 -m venv ~/.venvs/context-mapping
source ~/.venvs/context-mapping/bin/activate
cd /mnt/d/Github/context-mapping
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install tree-sitter-php watchdog
```

Mỗi session mới:

```bash
source ~/.venvs/context-mapping/bin/activate
cd /mnt/d/Github/context-mapping
```

Nếu `.venv` đã bị tạo dở trong repo Windows mount, có thể xóa nó trước khi tiếp tục:

```bash
rm -rf /mnt/d/Github/context-mapping/.venv
```

Phương án tốt nhất về lâu dài: clone repo vào Linux filesystem (`~/context-mapping`) và tạo `.venv` trong repo Linux đó.

---

## 3. Tension detection — khi nào ghi vào TENSIONS.md

Ghi tension khi agent nhận ra một trong những dấu hiệu sau, **trước khi** thực hiện action:

- Task yêu cầu sửa `cli.py`, `merger.py`, hoặc `schema.py` bằng cách thêm `if language == "..."` → tension với invariant registry
- Task yêu cầu print gì đó ra stdout trong `load` command → tension với stdout contract
- Task yêu cầu xóa hoặc overwrite `[manual]` section → tension với merge contract
- Task yêu cầu parser recursive scan → tension với "parse không recursive" invariant
- Task scope lớn hơn những gì `[manual] Behavior chưa implement` cho phép

**Format** (dùng cho tension do agent detect thủ công):
```markdown
## YYYY-MM-DD | <module>
Status:     OPEN
Tension:    <mô tả conflict cụ thể>
Context:    <đang làm task gì>
Proposal:   <agent muốn làm gì>
Constraint: <invariant nào bị conflict — trích dẫn từ [manual]>
Severity:   low | high
Decision:   [human fill in]
```

> **Lưu ý**: `tensions_writer.py` sinh staleness entries tự động theo format khác (dùng `###` headings, `Decision: Pending`).
> Khi grep TENSIONS.md để tìm entries cần review, dùng cả hai:
> ```bash
> # Agent-written tensions (manual format)
> grep -A8 "Status.*OPEN" .context/TENSIONS.md
> # Staleness warnings (auto-generated format)
> grep -B2 "Decision" .context/TENSIONS.md | grep "Pending" -A2
> ```

**Routing**:
- `low` → ghi tension, tiếp tục theo hướng conservative nhất, human review sau
- `high` → ghi tension, **dừng task**, đợi human fill `Decision`

---

## 4. Thêm parser mới — checklist

Khi được yêu cầu thêm language mới (ví dụ Python, Go, Vue):

Trước khi implement parser mới, dùng prompt template `docs/prompts/add-parser.md`. Agent phải chạy proposal phase trước, human approve rồi mới code.

```
□ Kiểm tra tree-sitter-<lang> có trên PyPI không
□ Probe AST node types trước khi viết parser
  python3 -c "... parser.parse(sample); walk(tree.root_node)"
□ Xác định "IPC bridge" tương đương cho language đó
  (tauri::command, add_action, URL endpoint, gRPC handler...)
□ Tạo parsers/<lang>_parser.py với register_plugin() ở cuối
□ Thêm import parsers.<lang>_parser vào cli.py (1 dòng duy nhất)
□ Thêm skip_dirs phù hợp với ecosystem
  (vendor/ cho PHP, __pycache__/ cho Python, target/ cho Rust...)
□ Viết .context/parsers_<lang>_parser.md với [manual] đầy đủ
□ Chạy: python cli.py build /tmp/test-<lang>-project .
□ Verify output trong .context/*.md đúng syntax
```

---

## 5. Files không được sửa nếu không có explicit instruction

| File | Lý do |
|------|-------|
| `.context/GLOBAL.md` [auto] section | auto-generated, sẽ bị overwrite |
| `.context/TENSIONS.md` entries đã RESOLVED | lịch sử không được sửa |
| `MANUAL_SECTION` template trong `schema.py` | agent dựa vào template để detect [manual] chưa điền |
| `AUTO_START` / `AUTO_END` markers trong `schema.py` | thay đổi markers = break toàn bộ merge logic |
| Hash trong `AUTO_START` marker của `.context/*.md` | merger V3 inject `\| hash: <8chars> \| built: <timestamp>` vào marker — đây là metadata cho staleness detection, không phải lỗi format |

---

## 6. Verification gate

Sau mỗi thay đổi, phải pass tất cả:

```bash
# Tool tự build được không bị crash
python cli.py build /tmp/test-project . --quiet

# load stdout sạch (không có noise — staleness warning đi stderr, không stdout)
python cli.py load /tmp/test-project/src . | python3 -c "
import sys
content = sys.stdin.read()
assert '<!-- AUTO_START -->' in content or len(content) > 0
print('stdout OK:', len(content), 'chars')
"

# Registry đủ plugins
python3 -c "
import parsers.rust_parser, parsers.ts_parser, parsers.php_parser
from schema import REGISTRY
assert set(REGISTRY.keys()) == {'rust', 'typescript', 'php'}, REGISTRY.keys()
print('Registry OK:', list(REGISTRY.keys()))
"

# [manual] không bị xóa sau build
python cli.py build /tmp/test-project . --quiet
grep -q 'MANUAL_START' /tmp/test-project/.context/*.md && echo "MANUAL preserved OK"

# Staleness detection hoạt động — hash được inject vào marker sau build
python cli.py build /tmp/test-project . --quiet
grep -q 'AUTO_START | hash:' /tmp/test-project/.context/*.md && echo "Hash injection OK"
```
