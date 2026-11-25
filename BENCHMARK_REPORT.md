# Benchmark & Observability Report — Day 14

> Mọi con số phần 1–3 bên dưới được lấy trực tiếp từ các file JSON trong `reports/`.
> Phần 4–5 (Observability stack & Locust scaling) cần Docker Compose / WSL2 nên sẽ điền sau khi bật Virtualization.

**Họ tên:** Hồ Sỹ Tùng  
**Ngày chạy:** 2026-11-25  
**Môi trường:** Windows (Acer Nitro AN515-57, Intel Core i5-11400H, Python 3.11.9)  

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | 95% người dùng nhận phản hồi dưới 0.5 giây, đủ mượt cho tác vụ chat với mock LLM (~120–200ms). |
| Error rate `/ask` | < 2.0 % | Cho phép tối đa 2% lỗi upstream tạm thời (`MOCK_ERROR_RATE=0.01`), đảm bảo độ tin cậy dịch vụ. |
| Accuracy trên golden dataset | ≥ 80 % | Đảm bảo chất lượng trả lời đạt ngưỡng tối thiểu và không regression khi deploy bản mới. |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.39 | 195.7 | 228.8 | 1691.9 | 1.67% | PASS |
| 10 | 43.11 | 191.9 | 263.1 | 1673.1 | 0.33% | PASS |
| 50 | 96.12 | 212.2 | 529.2 | 1715.7 | 1.00% | FAIL (p95 > 500ms) |
| 100 | 47.57 | 818.5 | 5019.6 | 5423.9 | 2.33% | FAIL (p95 & error rate) |

**Nhận xét:** RPS tăng gần tuyến tính từ concurrency 1 (4.39 req/s) lên 10 (43.11 req/s) và đạt đỉnh quanh concurrency 50 (96.12 req/s), nhưng đến concurrency 100 thì **giảm mạnh xuống 47.57 req/s** và p95 vọt lên 5019.6 ms. Nguyên nhân là một process uvicorn đơn lẻ bị bão hòa (event loop / CPU / socket queue bị nghẽn), các request phải xếp hàng chờ xử lý.

### 2.2 Tail latency

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 209.1 | 471.5 | 525.3 |
| 0.03 (mặc định) | 272.3 | 450.6 | 1716.6 |
| 0.1 | 365.1 | 1694.9 | 1720.3 |

**Nhận xét:** `p95` và `p99` nhạy nhất với request chậm: khi tăng `MOCK_SLOW_RATE` từ 0 lên 0.1, `avg` chỉ tăng từ 209.1 ms lên 365.1 ms (trông vẫn "nhanh"), trong khi `p95` nhảy vọt từ 471.5 ms lên 1694.9 ms và `p99` lên 1720.3 ms. Đặt SLO theo `average` sẽ che giấu trải nghiệm tệ của nhóm người dùng gặp tail latency.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.35% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 57.4 | 108.7 | 112.8 |
| Tổng cost (USD) | $0.000409 | $0.000756 | $0.000783 |
| Cost / câu đúng (USD) | $0.00040875 | $0.00003599 | $0.00003406 |
| Quality gate | FAIL (baseline) | PASS | PASS (min-accuracy 1.0) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry `(["jwt", "api key"], ...)` vào `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` (và đồng bộ sang `production/utils/mock_llm.py`) giải thích JWT có chữ ký số và thời gian hết hạn. |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry `(["kubernetes", "hpa"], ...)` vào `KNOWLEDGE_BASE` giải thích Kubernetes HPA scale dựa trên CPU, memory và custom metrics. |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**
- Agent v2 tốn gần gấp đôi số token mỗi câu (112.8 vs 57.4 tokens) và thêm ~20ms retrieval, nhưng độ chính xác tăng từ **4.35% lên 100.0%**.
- Tính theo **cost / câu đúng**, v2 (`$0.00003406`) **rẻ hơn ~12 lần** so với v1 (`$0.00040875`), chứng minh RAG mang lại hiệu quả vượt trội dù chi phí mỗi request cao hơn.

*(CI Quality Gate: trong GitHub Actions có thể chạy `python eval/run_eval.py --url http://localhost:8002 --min-accuracy 0.8 --baseline reports/eval_v2_fixed.json` — lệnh trả exit code `1` nếu accuracy dưới ngưỡng hoặc có regression, giúp tự động chặn merge PR.)*

---

## 4. Observability stack (production — Cần Docker/WSL2)

### 4.1 Screenshot

- [ ] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals)
- [ ] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian)
- [ ] Một trace lỗi trong Jaeger (có event `exception`)
- [ ] Trang Alerts của Prometheus với ít nhất 1 alert đang **firing**

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | | | |
| B | `MOCK_SLOW_RATE=0.3` | | | |
| C | `LLM_MODEL=mock-llm-large` | | | |
| D | `docker pause` 1 instance | | | |
| E | `AGENT_VERSION=v1` | | | |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Chạy eval tự động trên golden dataset trong pipeline CI/CD trước khi deploy (quality gate), kết hợp theo dõi feedback người dùng / LLM-as-a-judge trên mẫu traffic production.

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút — Cần Docker/WSL2)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | | | | | |
| 3 | | | | | |

**Giải thích kết quả:** *(Sẽ cập nhật sau khi chạy Locust với Docker Compose.)*

---

## 6. Kết luận

- 3 điều học được về benchmark & observability:
  1. `average` latency che giấu tail latency; SLO phải đặt theo `p95`/`p99`.
  2. So sánh chất lượng giữa hai phiên bản nên dùng `cost / câu đúng` và chạy regression eval trên golden dataset trong CI.
  3. Metrics (Prometheus), Traces (Jaeger) và JSON Logs gắn `trace_id` bổ trợ nhau để tìm nguyên nhân gốc nhanh chóng.
