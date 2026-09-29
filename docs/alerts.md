# Alerts và runbook

Các alert dưới đây đều dựa trên triệu chứng đo được từ metrics/dashboard. Runbook không giả định sẵn nguyên nhân; cần đi theo chuỗi metric → correlation_id → structured log → Langfuse trace trước khi kết luận.

## Alert 1: High latency P95

- **Alert name:** `high_latency_p95`
- **Symptom:** P95 latency của `response_sent` vượt ngưỡng SLO, cho thấy tail latency ảnh hưởng đến người dùng.
- **Trigger/threshold:** `p95_latency_ms > 3000`
- **Duration:** Duy trì liên tục `10m` trước khi fire.
- **Severity:** `warning`
- **Owner:** `on-call-llmops`
- **Slack channel:** `#llmops-alerts`
- **Runbook:** [Alert 1 — High latency P95](#alert-1-high-latency-p95)
- **SLI/SLO liên quan:** `fast_successful_requests`, với `latency_ms <= 3000` và target `99.5%` trong cửa sổ `28d`.
- **Các bước kiểm tra:**
  1. Xác nhận P95 vẫn vượt 3000 ms trong đúng time window và alert không phải do thiếu dữ liệu.
  2. Lọc `data/logs.jsonl` trong khoảng thời gian đó, lấy `correlation_id` của các request chậm và kiểm tra `latency_ms`, `ttft_ms`, `feature`, `model` cùng trạng thái response.
  3. Mở Langfuse trace có cùng `correlation_id`, so sánh thời gian của child `retrieval` và `generation`; chỉ khoanh vùng bước ảnh hưởng khi metric, log và trace khớp nhau.
- **Mitigation ban đầu:** Thông báo incident và giữ lại correlation ID/evidence. Nếu log/trace cho thấy tải hoặc một feature cụ thể gây tail latency, tạm giảm concurrency hoặc giới hạn feature đó; nếu chưa có bằng chứng, không tự kết luận nguyên nhân và tiếp tục theo dõi trace.

## Alert 2: High error rate

- **Alert name:** `high_error_rate`
- **Symptom:** Tỷ lệ `request_failed` trên tổng `request_received` vượt guardrail, cho thấy reliability suy giảm.
- **Trigger/threshold:** `error_rate_pct > 2`
- **Duration:** Duy trì liên tục `5m` trước khi fire.
- **Severity:** `critical`
- **Owner:** `on-call-llmops`
- **Slack channel:** `#llmops-alerts`
- **Runbook:** [Alert 2 — High error rate](#alert-2-high-error-rate)
- **SLI/SLO liên quan:** Error-rate guardrail `error_rate_pct <= 2%`; đối chiếu với SLO `fast_successful_requests`.
- **Các bước kiểm tra:**
  1. Xác nhận error rate, khoảng thời gian và `error_type` breakdown từ dashboard/log metrics.
  2. Lọc structured logs của các `request_failed`, lấy `correlation_id` và kiểm tra feature, model, request/response context đã được scrub.
  3. Mở trace tương ứng trong Langfuse, kiểm tra thứ tự `retrieval`/`generation`, status và timing; không gán nguyên nhân cho provider, database hoặc prompt nếu trace chưa chứng minh.
- **Mitigation ban đầu:** Giữ traffic trong phạm vi an toàn và áp dụng fallback/rollback đã được kiểm chứng nếu log/trace chỉ rõ phạm vi ảnh hưởng; nếu chưa có bằng chứng, tiếp tục thu thập correlation ID và chuyển incident cho owner.

## Alert 3: Retrieval degradation

- **Alert name:** `retrieval_degradation`
- **Symptom:** Retrieval success rate giảm dưới guardrail, làm giảm khả năng lấy context phục vụ câu trả lời.
- **Trigger/threshold:** `retrieval_success_rate_pct < 90`
- **Duration:** Duy trì liên tục `10m` trước khi fire.
- **Severity:** `warning`
- **Owner:** `llm-platform`
- **Slack channel:** `#llmops-alerts`
- **Runbook:** [Alert 3 — Retrieval degradation](#alert-3-retrieval-degradation)
- **SLI/SLO liên quan:** Retrieval success guardrail `retrieval_success_rate_pct >= 90%`.
- **Các bước kiểm tra:**
  1. Xác nhận retrieval success rate theo feature/model và time window; kiểm tra số sample đủ lớn.
  2. Lọc các log có `tool_success = false` hoặc retrieval không thành công, lấy `correlation_id` và kiểm tra `tool_name`, `feature`, `model`.
  3. Mở trace cùng `correlation_id`, kiểm tra child retrieval và generation để phân biệt retrieval degradation với lỗi ở bước generation.
- **Mitigation ban đầu:** Nếu evidence xác nhận degradation tập trung ở một feature, tạm chuyển feature đó sang fallback retrieval hoặc giảm traffic theo runbook vận hành; nếu chưa xác định được phạm vi, không thay đổi prompt/provider và tiếp tục điều tra qua trace.
