# Báo cáo cá nhân — K4-L3A Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Evidence được dẫn bằng đường dẫn tương đối tới file thực tế trong `submission/evidence/`.

## 1. Thông tin học viên

- **Họ và tên:** Đinh Tiến Mạnh
- **MSSV:** 2A202602458
- **Lớp:** K4-L3A
- **Repository URL:** [https://github.com/dtmanh2906/K4-L3A-Day13-DinhTienManh-2A202602458-Monitoring-LLMOps](https://github.com/dtmanh2906/K4-L3A-Day13-DinhTienManh-2A202602458-Monitoring-LLMOps)
- **Commit SHA cuối:** TODO: chưa có dữ liệu xác minh
- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1`
- **Tên project Langfuse cá nhân:** `day13-k4-l3a-2A202602458`

## 2. Evidence index

Chỉ dẫn dưới đây trỏ tới các file thực sự tồn tại trong `submission/evidence/`.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | `evidence/15-final-pytest.png` |
| Log validator CP1 | `evidence/cp1-log-validator.png` |
| Dashboard runtime | `evidence/cp2-dashboard-runtime.png` |
| Dashboard validator | `evidence/17-final-dashboard-validator.png` |
| Structured log | `evidence/cp1-structured-log.png` |
| Correlation ID | `evidence/cp1-correlation-id.png` |
| PII redaction | `evidence/cp1-pii-redaction.png` |
| Trace list | `evidence/cp2-trace-list.png` |
| Trace waterfall | `evidence/cp2-trace-waterfall.png` |
| Trace metadata | `evidence/cp2-trace-metadata.png` |
| Generation observation | `evidence/cp2-generation.png` |
| Prompt versions | `evidence/cp2-prompt-versions.png` |
| Prompt v1 trace | `evidence/cp2-prompt-v1-trace.png` |
| Prompt v2 trace | `evidence/cp2-prompt-v2-trace.png` |
| Prompt rollback | `evidence/cp2-prompt-rollback.png` |
| Prompt rollback trace | `evidence/cp2-prompt-rollback-trace.png` |
| Alert rules | `evidence/cp2-alert-rules.png` |
| High-latency runbook | `evidence/cp2-alert-runbook-1-high-latency.png` |
| High-error-rate runbook | `evidence/cp2-alert-runbook-2-high-error-rate.png` |
| Retrieval runbook | `evidence/cp2-alert-runbook-3-retrieval-degradation.png` |
| Incident metric | `evidence/12-incident-metric.png` |
| Incident log | `evidence/13-incident-log.png` |
| Incident trace | `evidence/14-incident-trace.png` |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| API startup | Thành công; server tại `http://127.0.0.1:8000` | Thành công | Startup log có `"tracing_enabled": true`; HTTP 404 tại `/` là bình thường vì application không định nghĩa root endpoint. |
| Load test | 10 request; 10/10 HTTP 200; request ID `MISSING` | Request ID hợp lệ dạng `req-<8hex>` | CP1 giữ HTTP 200 và bổ sung correlation ID qua header `x-request-id`. |
| `validate_logs.py` | 21 records; score `30/100` | 243 records; score `100/100` | Missing required fields `0`; missing enrichment/context `0`; unique correlation IDs `119`; potential PII leaks `0`; JSON schema, correlation propagation, enrichment và PII scrubbing đều PASSED. Evidence: `evidence/16-final-log-validator.png`. |
| `validate_dashboard.py` | `HỢP LỆ: 6/6 panel có trong dashboard contract.` | `HỢP LỆ: 6/6 panel có trong dashboard contract.` | Dashboard runtime đọc dữ liệu thực từ `data/logs.jsonl`. Evidence final: `evidence/17-final-dashboard-validator.png`. |
| `pytest` | `22 passed in 2.52s` | `22 passed in 2.43s` | Final validation pass. Evidence: `evidence/15-final-pytest.png`. |
| Số traces hợp lệ | Chưa có tracing | Đã tạo ít nhất 10 traces | Trace có root `lab-agent-run`, child `retrieval` và `generation`; evidence có trace list/waterfall. |
| Số PII leak | `0` | `0` | Structured logs và trace preview không chứa raw PII. |
| Latency P95 / TTFT P95 | Chưa đo | `2169.10 ms` / `50 ms` | Cửa sổ dashboard có 60 `response_sent`. |
| Retrieval success rate | Chưa đo | `100%` | Dashboard có 60 retrieval samples và 0 failed request. |

### CP0 / Baseline

- Environment và application khởi động thành công bằng `uvicorn app.main:app --reload --env-file .env`.
- Baseline workload thành công: 10/10 request trả HTTP 200, nhưng correlation/request ID hiển thị `MISSING`.
- Baseline `validate_logs.py`: 21 records; 20 thiếu required fields; 20 thiếu enrichment/context; 0 unique correlation IDs; 0 potential PII leaks; estimated score `30/100`.
- Baseline dashboard contract validator: `6/6 panel`.
- Baseline pytest: `22 passed in 2.52s`.

Baseline trên là trạng thái trước CP1, được giữ lại để so sánh và không phải kết quả cuối.

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** `CorrelationIdMiddleware` gọi `clear_contextvars()` ở đầu request, đọc header `x-request-id`, hoặc sinh ID dạng `req-<8hex>` nếu header không có. ID được bind vào structlog context, lưu vào `request.state.correlation_id`, trả lại qua response header `x-request-id`, đồng thời ghi response time qua `x-response-time-ms`. Context được clear trong `finally`.
- **Các metadata được ghi vào structured log:** Trước event `request_received`, `app/main.py` bind `user_id_hash`, `session_id`, `feature`, `model` và `env`. Các response log có thêm `latency_ms`, `ttft_ms`, `tokens_in`, `tokens_out`, `cost_usd`, `quality_score`, `tool_name` và `tool_success`.
- **Cách bảo đảm PII được scrub trước khi ghi:** `hash_user_id()` dùng SHA-256 rút gọn 12 ký tự cho user ID. `summarize_text()` scrub trước khi tạo preview. `scrub_event` xử lý email, số điện thoại Việt Nam, CCCD và số thẻ; processor này chạy trước `JsonlFileProcessor` và JSON renderer. Không ghi raw user ID, email, phone, CCCD hoặc card number.
- **Cách kiểm chứng kết quả:** `validate_logs.py` sau CP1 ghi nhận 41 records, 0 missing required fields, 0 missing enrichment/context, 20 unique correlation IDs, 0 potential PII leaks và score `100/100`.

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** Workload tạo ít nhất 10 traces trong project Langfuse `day13-k4-l3a-2A202602458`; evidence trace list thuộc project cá nhân.
- **Cấu trúc root/retrieval/generation observations:** `lab-agent-run` là root observation; bên dưới có child observation `retrieval` loại retriever và `generation` loại generation. Retrieval ghi result count, success và latency; generation ghi model, usage, cost và latency.
- **Cách nối trace với log:** Middleware tạo correlation ID và truyền `request.state.correlation_id` vào `LabAgent.run`. Agent đưa cùng ID vào trace metadata; structured log cũng ghi ID đó, tạo liên kết Metrics → Logs → Traces.
- **Metadata trace an toàn:** Trace có `correlation_id`, `model`, `feature`, `session_id`, `prompt_source`, `prompt_version`, `prompt_label`, `prompt_name`, `query_preview` và `doc_count`. User ID dùng hash; query/prompt/answer chỉ dùng preview đã scrub.
- **Prompt name:** `day13-chat`.
- **Version/label baseline:** Version 1 với label `production`.
- **Version/label candidate:** Version 2 được tạo và promote thành label `production`.
- **Trace evidence của các version:** Evidence v1 và v2 được dẫn trong Evidence Index; không tự tạo hoặc ghi thêm trace ID không có trong repository/evidence.
- **Cách promote và rollback `production`:** Ban đầu v1 là production; sau đó promote v2 thành production và trace xác nhận `prompt_source=langfuse`, `prompt_version=2`, `prompt_label=production`. Sau rollback về v1, trace xác nhận `prompt_version=1`, `prompt_label=production`.

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** Dashboard đọc `data/logs.jsonl`, gồm đúng sáu panel theo `config/dashboard.yaml`: `latency`, `traffic`, `errors`, `cost`, `tokens`, `quality`. Runtime window có 60 response samples với P50 `154 ms`, P95 `2169.10 ms`, P99 `2172 ms`, TTFT P95 `50 ms`; traffic `60 requests`, average `1 req/min`, peak `10`; error rate `0%`, failed `0`, retrieval success `100%`; total cost `0.130443 USD`; input/output/total tokens `3236/8049/11285`; mean quality `0.880` trên 60 samples. Validator xác nhận `6/6 panel`.
- **SLO và lý do chọn:** SLO chính là `fast_successful_requests` trong cửa sổ `28d`: SLI là số `response_sent` có `latency_ms <= 3000` chia cho số `request_received`, target `99.5%`. Guardrails gồm error rate `<= 2%`, daily cost `<= 2.5 USD`, quality mean `>= 0.75` và retrieval success `>= 90%`.
- **Cách tính error budget:** `100% - 99.5% = 0.5%`. Với `N` request, số request không đạt tối đa để giữ target là `floor(N * 0.005)`. Với 60 request, budget lý thuyết là `0.3 request`, nên theo số nguyên là `0` request không đạt.
- **Ba alert và runbook tương ứng:**
  - `high_latency_p95`: `p95_latency_ms > 3000` trong `10m`, severity `warning`.
  - `high_error_rate`: `error_rate_pct > 2` trong `5m`, severity `critical`.
  - `retrieval_degradation`: `retrieval_success_rate_pct < 90` trong `10m`, severity `warning`.
  Tất cả dùng Slack channel an toàn `#llmops-alerts`, có owner/runbook trong `config/alert_rules.yaml` và `docs/alerts.md`. Workflow runbook là metric → correlation ID → structured log → Langfuse trace → xác định span/root cause → mitigation.

## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1`.
- **Incident và khoảng thời gian:** Incident `rag_slow`, affected feature `monitoring`, latency threshold `2000 ms`. Request được chọn `req-7148df0a` nhận lúc `2026-09-29T10:31:46.082827Z` và response lúc `2026-09-29T10:31:48.745658Z`, tương đương khoảng 17:31:46–17:31:49 UTC+7.
- **Triệu chứng từ metrics:** Official challenge load test ghi nhận các request chậm: `req-35ce2310` `10652.4 ms`, `req-97f3f39b` `10656.2 ms`, `req-b5d6b681` `13319.8 ms`, `req-7148df0a` `13322.8 ms`, `req-a6c7d9cf` `13321.6 ms`. Với request được chọn, structured log ghi `latency_ms=2656`, vượt threshold 2000 ms.
- **Log line và correlation ID liên quan:** `correlation_id=req-7148df0a`, `session_id=k4-l3a-challenge-s04`, `feature=monitoring`, `event=response_sent`, `latency_ms=2656`, `ttft_ms=50`, `tool_name=retrieval`, `tool_success=true`, `quality_score=0.9`. Evidence: `evidence/13-incident-log.png`.
- **Trace ID và span gây ảnh hưởng:** Langfuse trace `9de4967aea5e2a26a4c935f6bffdace7`; root `lab-agent-run` khoảng 2.66 s, child `retrieval` khoảng 2.50 s với metadata `latency_ms=2502`, còn `generation` khoảng 152 ms. Trace có cùng correlation ID `req-7148df0a`; evidence: `evidence/14-incident-trace.png`.
- **Root cause:** Khi `STATE["rag_slow"] == True`, `app/mock_rag.py` gọi `time.sleep(2.5)` trong `retrieve()`. Retrieval vì vậy là bottleneck; generation không phải bottleneck chính.
- **Phân biệt số liệu:** `13322.8 ms` là latency quan sát bởi load-test/client; `2656 ms` là latency được structured log ghi nhận cho agent/request processing. Hai giá trị không được coi là bằng nhau.
- **Fix action:** Đã chạy `python scripts/inject_incident.py --disable`; trạng thái xác nhận `rag_slow=False`, `tool_fail=False`, `cost_spike=False`.
- **Preventive measure:** Theo dõi P95 latency và retrieval success; duy trì các alert `high_latency_p95` và `retrieval_degradation`; điều tra theo Metrics → Logs → Traces; giữ correlation ID xuyên suốt request.

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:** Ban đầu hệ thống là black-box: request trả thành công nhưng thiếu correlation ID và log context. CP1 bổ sung structured logging, correlation ID, enrichment và PII protection; CP2 bổ sung tracing, prompt versioning, dashboard, SLO và alerts.
- **Một lỗi/blocker đã gặp:** HTTP 200 không đồng nghĩa hệ thống khỏe. Trong challenge, request vẫn thành công nhưng retrieval latency vượt threshold và làm tăng tail latency.
- **Cách tìm nguyên nhân và xử lý:** Dashboard phát hiện triệu chứng; correlation ID nối tới structured log; trace xác định retrieval là span chậm nhất; source `app/mock_rag.py` xác nhận `rag_slow` tạo độ trễ 2.5 giây; sau đó incident được disable.
- **Cách hiểu luồng Metrics → Logs → Traces:** Metrics cho biết triệu chứng và khoảng thời gian; logs cho biết request cụ thể qua correlation ID; traces phân rã retrieval/generation để định vị span; chỉ sau khi ba lớp khớp mới kết luận root cause và chọn mitigation.
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:** Prompt version và production label giúp kiểm soát thay đổi; rollback đưa production về version an toàn. Token/cost metrics theo dõi chi phí ngoài latency/error rate. SLO và error budget giúp định lượng mức suy giảm chấp nhận được; alerts/runbook biến metric thành quy trình điều tra.
- **Điều quan trọng nhất đã học:** Correlation ID là điểm nối thực tế giữa metrics, logs và traces. Structured logging và PII scrubbing phải được thiết kế từ đầu để điều tra được mà không làm lộ dữ liệu nhạy cảm.
- **Hạn chế hoặc phần chưa hoàn thành:** Repository URL và final commit SHA chưa được xác minh. Các evidence CP1, CP2, alert, CP3 và final validation hiện có đã được dẫn theo tên file thực tế.

## 9. Checklist trước khi nộp

- [ ] Kết quả và evidence thuộc commit SHA cuối — chưa có SHA xác minh.
- [x] Tất cả ảnh/output đã có trong Evidence Index được dẫn bằng đường dẫn tương đối.
- [x] Incident evidence nối đúng metric → log → trace.
- [x] Trace/prompt evidence thuộc project Langfuse cá nhân và không lộ key/secret.
- [ ] Repository URL và commit SHA cuối đã được xác minh.
- [x] Report không chứa secret, API key, raw PII hoặc nội dung challenge config.
