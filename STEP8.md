# Báo Cáo Phân Tích Kết Quả (Bước 8 & Bước 9 - GUIDE.md)

- **Họ và tên**: Chung Văn Duy
- **Mã số sinh viên (MSSV)**: 2A202602854
- **Lớp / Khóa**: K4 - Giai đoạn 2, Track 3 (Day 17)
- **Repository**: [K4-DAY17-ChungVanDuy-2A202602854](https://github.com/CoderNVU/K4-DAY17-ChungVanDuy-2A202602854.git)

---

## 1. Bảng Số Liệu Thực Nghiệm Benchmark Độc Lập

Kết quả chạy từ lệnh chuẩn `python src/benchmark.py`:

### 1.1. Standard Benchmark (`data/conversations.json` - 10 hội thoại, user `dungct`)
| Agent | Agent tokens only | Prompt tokens processed | Cross-session recall | Response quality | Memory growth (bytes) | Compactions |
|:---|---:|---:|---:|---:|---:|---:|
| **Baseline** | 3,135 | 22,647 | **0.0%** | 50.0% | 0 | 0 |
| **Advanced** | 5,982 | 37,585 | **100.0%** | **100.0%** | 280 | 4 |

### 1.2. Long-Context Stress Benchmark (`data/advanced_long_context.json` - 16 turns dài, user `dungct_stress`)
| Agent | Agent tokens only | Prompt tokens processed | Cross-session recall | Response quality | Memory growth (bytes) | Compactions |
|:---|---:|---:|---:|---:|---:|---:|
| **Baseline** | 519 | 24,124 | **0.0%** | 50.0% | 0 | 0 |
| **Advanced** | 1,252 | **13,498** | **100.0%** | **100.0%** | 229 | **11** |

---

## 2. Trả Lời 4 Câu Hỏi Trọng Tâm Của Bước 8 (GUIDE.md)

### Câu 1: Vì sao Advanced có recall tốt hơn Baseline?
- **Baseline Agent** chỉ duy trì bộ nhớ ngắn hạn trong bộ nhớ RAM của một `thread_id` duy nhất. Khi người dùng mở một thread mới để hỏi lại các thông tin cá nhân (recall queries), Baseline không thể truy cập lại dữ liệu của phiên trước và phản hồi chưa có thông tin. Do đó, điểm **Cross-session recall của Baseline là 0.0%**.
- **Advanced Agent** được trang bị tầng **Persistent Memory** với file `User.md` lưu trữ độc lập trên ổ đĩa (`state/profiles/{user_id}/User.md`). Bất kể người dùng tạo thread mới hay khởi động lại phiên làm việc, Agent luôn nạp lại hồ sơ này vào prompt ngữ cảnh. Nhờ đó, Advanced Agent nhớ chính xác toàn bộ facts (tên, nơi ở, nghề nghiệp, đồ uống yêu thích, thú cưng, style trả lời) và đạt điểm **Cross-session recall tuyệt đối 100.0%**.

### Câu 2: Vì sao Advanced có thể tốn hơn ở hội thoại ngắn?
- Trong bộ dữ liệu Standard Benchmark (10 hội thoại thông thường), tổng `Prompt tokens processed` của Advanced là **37,585 tokens**, cao hơn mức **22,647 tokens** của Baseline.
- **Lý do**: Ở mỗi lượt trò chuyện, Advanced Agent phải chịu một khoản chi phí cố định (overhead) để nạp nội dung file `User.md` (~60–80 tokens) và system prompt hướng dẫn vào context window. Khi hội thoại còn ngắn (chưa vượt ngưỡng kích hoạt compaction), khoản overhead này tích lũy qua 10 phiên khiến tổng prompt tokens của Advanced cao hơn Baseline.
- **Đánh đổi**: Chi phí này là hoàn toàn xứng đáng vì nó đổi lại khả năng nhận diện người dùng xuyên suốt các phiên làm việc thay vì một agent hoàn toàn mất trí nhớ sau mỗi lần đóng phiên.

### Câu 3: Vì sao Compact giúp Advanced có lợi thế ở hội thoại dài?
- Trong hội thoại rất dài (Stress Benchmark với 16 lượt chứa nhiều văn bản tin tức dày đặc), **Baseline Agent** tích lũy toàn bộ lịch sử thô qua từng lượt khiến chi phí ngữ cảnh tăng vọt lên **24,124 prompt tokens**.
- **Advanced Agent** tích hợp `CompactMemoryManager`: khi tổng tokens của các tin nhắn active vượt ngưỡng `compact_threshold_tokens`, hệ thống tự động kích hoạt **11 lần nén (compactions)**, chuyển các tin nhắn cũ thành bản tóm tắt luân phiên (rolling summary) và chỉ giữ lại $K$ tin nhắn gần nhất.
- Kết quả: Lượng prompt tokens của Advanced giảm xuống chỉ còn **13,498 tokens** (tiết kiệm **44.05%** chi phí xử lý ngữ cảnh so với Baseline) mà vẫn duy trì khả năng recall 100.0%.

### Câu 4: File memory tăng trưởng ra sao và rủi ro gì đi kèm?
- Dung lượng file `User.md` tăng từ 0 lên **280 bytes** sau 10 phiên hội thoại của user `dungct` và đạt **229 bytes** trong stress test.
- **Rủi ro đi kèm trong môi trường production**:
  1. **Memory Bloat (Phình to bộ nhớ)**: Nếu người dùng trò chuyện hàng trăm phiên, file `User.md` có thể chứa hàng nghìn facts vụn vặt hoặc mâu thuẫn, làm phình to context window và tăng chi phí token vĩnh viễn.
  2. **I/O Latency**: Việc liên tục đọc/ghi file từ ổ cứng ở mỗi lượt chat có thể gây nghẽn cổ chai I/O khi hệ thống mở rộng phục vụ hàng nghìn người dùng đồng thời (cần bổ sung cache in-memory như Redis).
  3. **Lossy Compression & Hallucination**: Khi nén lịch sử cũ vào summary, có rủi ro các chi tiết kỹ thuật tinh tế bị lược bỏ hoặc bị LLM tóm tắt sai lệch so với ý định ban đầu của người dùng.

---

## 3. Phần Bonus Triển Khai Thực Tế (Mức 90 – 100 Điểm)

Để đạt điểm số tối đa theo Rubric, hệ thống đã cài đặt 3 giải pháp kỹ thuật nâng cao trực tiếp trong code:

### 3.1. Confidence Thresholding & Noise Filtering (Lọc độ tin cậy)
- **Vấn đề giải quyết**: Tránh tình trạng Agent lưu nhầm câu hỏi truy vấn của người dùng thành facts (ví dụ câu hỏi: *"Nếu ai đó nhắc Huế, Hà Nội hay product manager, đâu mới là nghề nghiệp và nơi ở hiện tại của mình?"*). Nếu không có bộ lọc, Agent sẽ bắt nhầm "Hà Nội" hoặc "product manager" làm ghi đè hồ sơ.
- **Giải pháp**: Tự động nhận diện cấu trúc nghi vấn (`is_query`), câu nói đùa (*"product manager chỉ là câu đùa"*), hoặc địa điểm công tác tạm thời (*"Hà Nội chỉ là nơi mình vừa bay ra họp 2 ngày"*), từ chối trích xuất trừ khi có câu khẳng định đính chính rõ ràng.
- **Kết quả**: Ngăn chặn 100% tình trạng ô nhiễm hồ sơ, giúp recall trong stress test đạt điểm tuyệt đối **100.0%**.

### 3.2. Conflict Handling & Additive Merging (Xử lý xung đột & đính chính)
- **Vấn đề giải quyết**: Khi người dùng thay đổi nơi ở (Đà Nẵng $\rightarrow$ Huế $\rightarrow$ Đà Nẵng) và nghề nghiệp (Backend $\rightarrow$ MLOps), hệ thống không được lưu song song cả hai facts mâu thuẫn trong `User.md`.
- **Giải pháp**:
  - Nhận diện các mẫu câu đính chính: ghi đè thông tin mới nhất vào `User.md` và loại bỏ hoàn toàn fact cũ lỗi thời.
  - Áp dụng cơ chế **Additive Merging** cho sở thích kỹ thuật (hợp nhất: Python $\cup$ AI $\cup$ MLOps) để không làm mất các mối quan tâm cũ khi người dùng nhắc đến chủ đề mới.

### 3.3. Structured Markdown Profile Schema
- Cấu trúc `User.md` thành các mục chuẩn Markdown rõ ràng (`Core Facts`, `Interests`), giúp con người dễ dàng kiểm tra, chỉnh sửa thủ công và giúp LLM dễ dàng parse khi sinh câu trả lời.
