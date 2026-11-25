# Day 14 Lab - Mission Answers

> **Họ và tên:** Hồ Sỹ Tùng  
> **Lớp / MSSV:** K5-L3A / 2A202603650  

---

## Part 1: Localhost vs Production (CP1)

### Exercise 1.1: Phát hiện anti-patterns trong `01-localhost-vs-production/develop/app.py`

1. **Hardcode secrets trong source code** (dòng 17–18): `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"` — nếu push lên GitHub sẽ bị lộ ngay lập tức.
2. **Không có quản lý cấu hình qua biến môi trường** (dòng 21–22): `DEBUG = True` và `MAX_TOKENS = 500` được gán cứng trong code, không tách biệt theo môi trường dev/staging/prod.
3. **Dùng `print()` thay cho structured logging và log lộ secret** (dòng 33–34, 38): `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` làm lộ API key ra stdout và khó parse trên hệ thống tập trung (Loki, Datadog).
4. **Thiếu health check / readiness endpoint** (không có `/health` và `/ready`): nền tảng cloud/orchestrator không thể kiểm tra tiến trình còn sống hay đã sẵn sàng nhận traffic.
5. **Hardcode `host="localhost"`, `port=8000` và `reload=True`** (dòng 49–54):
   - `host="localhost"` chỉ nhận kết nối nội bộ, không chạy được trong container/cloud (cần `0.0.0.0`).
   - `port=8000` cố định, không đọc biến `PORT` do nền tảng cloud cấp.
   - `reload=True` bật auto-reload trong production gây tốn tài nguyên và không ổn định.
6. **Không xử lý graceful shutdown và không cấu hình CORS**: tiến trình bị ngắt đột ngột khi nhận `SIGTERM`, có thể làm đứt request đang chạy.

### Exercise 1.2: Kết quả chạy bản `develop`

```bash
curl -X POST "http://localhost:8000/ask?question=Hello"
```

Output:

```json
{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

### Exercise 1.3: So sánh `develop/app.py` và `production/app.py`

Kết quả test bản `production`:
- `GET /health`: `{"status":"ok","uptime_seconds":2.5,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T09:21:56.888260+00:00"}`
- `GET /ready`: `{"ready":true}`
- `POST /ask` (`{"question":"Hello"}`): `{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","model":"gpt-4o-mini"}`

Bảng so sánh:

| Feature | Develop (`develop/app.py`) | Production (`production/app.py`) | Tại sao quan trọng? |
| --- | --- | --- | --- |
| **Config & Secrets** | Hardcode `OPENAI_API_KEY`, `DATABASE_URL`, `DEBUG`, `PORT` trực tiếp trong code | Đọc từ biến môi trường qua `config.settings` và `.env` (không commit `.env`) | Tránh lộ secret trên Git; cùng một artifact chạy được ở nhiều môi trường (dev/staging/prod) chỉ bằng cách đổi env vars (12-Factor App). |
| **Health & Readiness** | Không có endpoint kiểm tra sức khỏe | Có `/health` (liveness), `/ready` (readiness trả 503 khi chưa sẵn sàng), `/metrics` | Orchestrator/cloud dùng `/health` để restart container khi treo, và `/ready` để Load Balancer chỉ route traffic khi app sẵn sàng. |
| **Logging** | `print(...)` dạng text thuần, thậm chí log cả `OPENAI_API_KEY` | `logging` cấu hình JSON (`{"time":...,"level":...,"msg":...}`), chỉ log metadata (`question_length`, `client_ip`), không log secret | Log JSON dễ thu thập/tìm kiếm ở Loki/Datadog và bảo đảm an toàn thông tin. |
| **Shutdown** | Tắt đột ngột | Có `lifespan` context manager (set `is_ready = False`, đợi in-flight requests) và `signal.signal(signal.SIGTERM, handle_sigterm)` | Khi deploy phiên bản mới hoặc scale down, container có thời gian hoàn tất các request đang xử lý thay vì trả lỗi 502/đứt kết nối cho người dùng. |
| **Host, Port & Debug** | `host="localhost"`, `port=8000`, `reload=True` | `host=settings.host` (`0.0.0.0`), `port=settings.port` (từ `PORT`), `reload=settings.debug` (`False` ở prod) | Container/cloud yêu cầu bind `0.0.0.0` và lắng nghe đúng cổng `PORT` do nền tảng cấp; tắt `reload` để ổn định hiệu năng. |

---

## Part 2: Docker (CP2 — Cần Docker/WSL2)

### Exercise 2.1 — Basic Container

- Container: `agent-develop-container`
- Container runtime: Podman (Docker CLI compatibility)
- Status: Running
- Application: Python / Uvicorn
- Port mapping: `8000:8000`
- Health endpoint: `/health`
- HTTP status: `200 OK`
- Response: `{"status":"ok","uptime_seconds":367.9,"container":true}`

**Result: PASS**

The application was successfully built into a container image and launched using Podman. The health endpoint returned HTTP 200 OK, confirming that the application is running and accessible through the published port.

### Exercise 2.2 – Layer Cache

Cả hai Dockerfile đều build thành công. Khi build lại mà không thay đổi mã nguồn, toàn bộ các layer đều sử dụng cache. Sau khi thay đổi file `main.go`, các layer `COPY main.go` và `go build` phải build lại, trong khi những layer trước đó không thay đổi vẫn sử dụng cache.

Chiến lược `deps-first` hiệu quả hơn vì tách bước tải thư viện phụ thuộc khỏi mã nguồn. Khi chỉ thay đổi source code, các dependency không cần tải lại, giúp tiết kiệm thời gian build và tối ưu quá trình phát triển.

### Exercise 2.3 – Single-stage vs Multi-stage Build

**Kết quả thực nghiệm:**

| Kiểu build | Kích thước image |
|---|---:|
| Single-stage | 921 MB |
| Multi-stage | 14.7 MB |

**Mức giảm kích thước:**

\[
\frac{921-14.7}{921}\times100\%\approx98.40\%
\]

Multi-stage build giúp giảm kích thước image khoảng **98,40%**, từ 921 MB xuống 14,7 MB.

**Kết luận:**

Single-stage build tạo image có kích thước lớn vì image có thể chứa cả môi trường build, compiler và các thành phần không cần thiết khi chạy ứng dụng. Multi-stage build tách giai đoạn build và giai đoạn chạy, chỉ sao chép các thành phần cần thiết sang image cuối cùng. Do đó, Multi-stage build giúp image nhẹ hơn, giảm dung lượng lưu trữ, giảm thời gian truyền tải và tối ưu quá trình triển khai ứng dụng.

### Exercise 2.4 – Production Compose

**Kết quả triển khai:**

Sử dụng Podman Compose để triển khai môi trường production gồm các service Agent, Redis, Qdrant và Nginx. Các service được kết nối thông qua mạng nội bộ của Compose, đồng thời sử dụng volumes để lưu trữ dữ liệu Redis và Qdrant.

| Service | Kết quả |
|---|---|
| Agent | Running |
| Redis | Healthy |
| Qdrant | Healthy |
| Nginx | Started |

**Kiểm tra Health Check:**

Thực hiện request đến endpoint `http://localhost:8080/health` thông qua Nginx.

Kết quả trả về HTTP `200 OK`, với nội dung JSON:

```json
{
  "status": "ok",
  "uptime_seconds": 235.4,
  "version": "2.0.0"
}
```

**Điều chỉnh cấu hình:**

Do sử dụng Podman rootless trên WSL, không thể bind trực tiếp các cổng đặc quyền 80 và 443 trên host. Vì vậy, thay đổi port mapping của Nginx từ `80:80` thành `8080:80` và từ `443:443` thành `8443:443`. Các port bên trong container được giữ nguyên.

**Kết luận:**

Triển khai Production Compose thành công. Các service Agent, Redis, Qdrant và Nginx đã khởi chạy. Request health check đi qua Nginx và nhận phản hồi HTTP 200 OK. Hệ thống đã hoàn thành kiểm tra cơ bản về triển khai đa service, kết nối nội bộ và reverse proxy trong môi trường Podman.
---



## Part 3: Cloud Deployment (CP6)

*(Phần deploy URL thực tế cần hoàn thành CP5/Docker trước; đã hoàn thành Exercise 3.3 bên dưới.)*

### Exercise 3.3: Mô tả pipeline Cloud Run (`cloudbuild.yaml` & `service.yaml`)

- **Pipeline CI/CD (`03-cloud-deployment/production-cloud-run/cloudbuild.yaml`):** Khi push lên nhánh `main`, Google Cloud Build tự động chạy 4 bước tuần tự (`waitFor`): (1) `test` chạy `pytest tests/ -v` trên `python:3.11-slim`, (2) `build` đóng gói Docker image gắn tag `$COMMIT_SHA` và `latest` (dùng `--cache-from` để tận dụng layer cache), (3) `push` đẩy image lên Google Container Registry (`gcr.io/$PROJECT_ID/ai-agent`), và (4) `deploy` triển khai lên Cloud Run ở region `asia-southeast1` kèm env vars và secret `OPENAI_API_KEY` từ Secret Manager.
- **Cấu hình dịch vụ (`service.yaml`):** Khai báo IaC cho Knative/Cloud Run với `minScale: "1"` (tránh cold start), `maxScale: "10"`, `containerConcurrency: 80`, giới hạn tài nguyên `cpu: "1"` / `memory: 512Mi`, inject secrets qua `secretKeyRef`, và gắn `livenessProbe` (`/health`) + `startupProbe` (`/ready`).

---

## Part 4: API Security (CP3)

### Exercise 4.1: API Key Authentication (`04-api-gateway/develop/app.py`)

Chạy server với `AGENT_API_KEY=secret-key-123`.

1. **Không có API key (`401 Unauthorized`):**

```http
HTTP/1.1 401 Unauthorized
date: Wed, 25 Nov 2026 09:24:33 GMT
server: uvicorn
content-length: 67
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```

2. **Có `X-API-Key: secret-key-123` (`200 OK`):**

```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 09:24:33 GMT
server: uvicorn
content-length: 122
content-type: application/json

{"question":"hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

### Exercise 4.2 & 4.3: JWT Authentication & Rate Limiting (`04-api-gateway/production/app.py`)

Lấy JWT token tại `POST /auth/token` với tài khoản `student` / `demo123` (giới hạn 10 requests/phút). Token đã được che khi dán: `Authorization: Bearer <REDACTED_JWT_TOKEN>`.

1. **Gọi `POST /ask` với JWT hợp lệ (`200 OK`):**

```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 09:24:59 GMT
server: uvicorn
content-length: 196
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"question":"what is docker?","answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!","usage":{"requests_remaining":9,"budget_remaining_usd":1.9e-05}}
```

2. **Vòng lặp test Rate Limit (10 requests/phút):**
   - Requests #1 → #10: `HTTP 200`
   - Request #11: `HTTP 429`

```http
HTTP/1.1 429 Too Many Requests
date: Wed, 25 Nov 2026 09:25:00 GMT
server: uvicorn
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795598761
retry-after: 59
content-length: 98
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

### Exercise 4.4: Cách hoạt động của Cost Guard (`04-api-gateway/production/cost_guard.py`)

- **Phân biệt Rate Limit vs Cost Guard:** Rate limit bảo vệ **tốc độ** (số request/phút để chống spam/DDoS), còn Cost Guard bảo vệ **ngân sách tiền** (tổng chi phí token LLM theo ngày/tháng) vì một request prompt dài có thể tốn gấp nhiều lần request ngắn.
- **Cơ chế trong `CostGuard`:**
  1. **Trước khi gọi LLM (`check_budget(user_id)`):** Kiểm tra tổng chi phí toàn hệ thống (`global_daily_budget_usd = $10.0`, vượt ngưỡng trả `503`) và chi phí trong ngày của từng user (`daily_budget_usd = $1.0`, vượt ngưỡng trả `402 Payment Required`). Nếu đạt ≥ 80% ngân sách (`warn_at_pct = 0.8`), ghi log cảnh báo.
  2. **Sau khi gọi LLM (`record_usage(user_id, input_tokens, output_tokens)`):** Tính chi phí theo đơn giá input/output token (`PRICE_PER_1K_INPUT_TOKENS`, `PRICE_PER_1K_OUTPUT_TOKENS`), cộng dồn vào bản ghi theo ngày (`YYYY-MM-DD`) của user và tổng chi phí toàn cục.
  3. **Trong production:** Trạng thái usage được lưu ở **Redis** (thay vì dict in-memory) để chia sẻ chính xác giữa nhiều instance/container.

---

## Part 5: Scaling & Reliability (CP4 — Cần Docker/WSL2)

### CP4 – Scaling & Reliability

**Mục tiêu:** Triển khai hệ thống nhiều Agent instance, kiểm tra khả năng mở rộng, quản lý trạng thái dùng chung và khả năng phục hồi khi một instance dừng.

**1. Scaling & Stateless**
- Scale hệ thống lên 3 Agent instance bằng Podman Compose.
- Redis được sử dụng để lưu trữ trạng thái hội thoại dùng chung.
- Thực hiện 5 requests liên tiếp trên cùng Session ID.
- Các requests được xử lý bởi 3 instance khác nhau.
- Conversation history vẫn được duy trì, tổng cộng 10 messages.

**Kết quả:** PASS – Stateless Scaling.

**2. Health Check**
- Kiểm tra endpoint `/health`.
- Kết quả trả về `status: ok`.
- Redis connection được xác nhận `redis_connected: true`.
- Instance ID và uptime được trả về thành công.

**Kết quả:** PASS.

**3. Readiness Check**
- Kiểm tra endpoint `/ready`.
- Kết quả trả về `ready: true`.
- Instance xác nhận sẵn sàng tiếp nhận request.

**Kết quả:** PASS.

**4. Graceful Shutdown**
- Thực hiện dừng Agent-1 với thời gian chờ 10 giây.
- Uvicorn nhận tín hiệu shutdown.
- Application shutdown và Lifespan shutdown được thực hiện.
- Log xác nhận `Application shutdown complete`.
- Agent-2 và Agent-3 tiếp tục hoạt động khi Agent-1 dừng.

**Kết quả:** PASS – Graceful Shutdown.

**Kết luận:** Hệ thống đã kiểm thử thành công khả năng Stateless Scaling, Health Check, Readiness Check và Graceful Shutdown. Redis giúp duy trì trạng thái hội thoại dùng chung giữa các Agent instance, trong khi việc dừng một instance không làm các instance còn lại ngừng hoạt động.

**Công cụ:** Podman, Compose, Redis, FastAPI, Uvicorn, Python.

---

## Part 6: Final Project (`06-lab-complete/`)

### Part 6 – Final Project: Production Readiness

**Result: 10/12 criteria passed, 39/39 checks passed.**

The application was implemented with production-ready features including multi-stage Dockerfile, Docker Compose deployment configuration, Redis integration, health and readiness endpoints, API Key authentication, rate limiting, cost guard, environment-based configuration, structured JSON logging, graceful shutdown, and Railway/Render deployment configurations.

Runtime verification confirmed:

- Health endpoint returns HTTP 200.
- Readiness endpoint returns HTTP 200 when Redis is available and HTTP 503 when Redis is unavailable.
- API Key authentication returns HTTP 401 for missing or invalid keys and HTTP 200 for valid keys.
- Rate limiting returns HTTP 429 after exceeding the configured limit of 5 requests.
- Rate-limit state persists across Agent restarts through Redis.
- Cost guard returns HTTP 402 when the budget is exhausted.
- Application configuration is loaded from environment variables.
- Structured logs are valid JSON.
- Graceful shutdown using SIGTERM allows the active request to complete successfully and exits with code 0.
- Railway and Render deployment configurations are prepared.

**Limitation:** Docker-specific runtime tests, including image size verification and `docker stop`, could not be completed because Docker Engine was unavailable. Podman was used as the container runtime during the lab.

**Checklist: 10/12 criteria passed.**

