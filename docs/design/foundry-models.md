# Nhiều model trên Azure AI Foundry

Cập nhật: 2026-11-27. Nhánh `feat/foundry-models` (tách từ `feat/azure-openai`). Người làm: Kiên.

## Mục tiêu

- Nhóm và thầy thử app với nhiều model khác nhau ngay trên bản deploy: chọn model trong nút cài đặt cạnh ô nhập,
  hỏi, đánh giá 👍/👎. Không cần key mới, không cần tài khoản ở dịch vụ khác.
- Mọi model nằm trên **một** resource Azure AI Foundry (một endpoint, một key), trừ vào credit Azure for Students,
  khai báo bằng Terraform như phần còn lại của `infra/azure/`.
- Người dùng chỉ chọn được model đã deploy (danh sách), không gõ tên tùy ý.

Ngoài phạm vi: OpenRouter, giới hạn số câu mỗi tài khoản, chạy eval cho từng model (xem "Chưa quyết").

## Căn cứ chọn

- OpenRouter tốn tiền của Kiên (nạp trước, phí 5,5%); model free giới hạn khoảng 50 request/ngày nếu chưa nạp tiền
  (nguồn thứ ba, chưa kiểm chứng). GitHub Models có tin đã ngừng 30/07/2026 (nguồn thứ ba).
- Quota của subscription ở `koreacentral` (`az cognitiveservices usage list -l koreacentral`, 27/11), đơn vị nghìn
  token mỗi phút:

| Model | Hãng | Quota | Giá vào / ra mỗi 1M token (Retail Prices API, 27/11) | Một câu như P02 (đoán) |
|---|---|---|---|---|
| `gpt-4.1-mini` (đang dùng) | OpenAI | 200 (dùng 50) | $0.40 / $1.60 | $0.008 |
| `gpt-5-mini` | OpenAI, reasoning | 500 | $0.25 / $2.00 | $0.007 + token suy nghĩ |
| `gpt-oss-120b` | OpenAI open-weight, reasoning | 5000 | $0.15 / $0.60 | $0.003 + token suy nghĩ |
| `Llama-3.3-70B-Instruct` | Meta | 20 | $0.71 / $0.71 | $0.010 |
| `mistral-medium-2505` | Mistral AI | 20 | chưa rõ (không thấy trong API) | chưa rõ |

  P02 là 12.264 token vào + 1.675 token ra ([architecture.md](architecture.md)). DeepSeek, Kimi, Qwen, `gpt-5.x` có
  trong catalog nhưng quota bằng 0.

## Thiết kế

### Terraform (`infra/azure/foundry.tf`)

| Resource | Nội dung |
|---|---|
| `azurerm_cognitive_account.foundry` | `kind = "AIServices"`, `sku_name = "S0"`, `location = var.openai_location`, `custom_subdomain_name = var.foundry_subdomain` (`co5151-g3-foundry`) |
| `azurerm_cognitive_deployment.foundry` | `for_each = var.foundry_models`; tên deployment = tên model; `model { format, name, version }`, `sku { GlobalStandard, capacity }` |

- `var.foundry_models`: map tên → `{ format, version, capacity }`. Thêm model = thêm một dòng rồi `apply`.
- Output `foundry_base_url` (`https://<subdomain>.openai.azure.com/openai/v1/`) và `foundry_models` (tên nối bằng
  dấu phẩy) để chép vào `.env`. Key lấy bằng `az ... keys list` như Azure OpenAI.
- Resource `OpenAI` cũ giữ nguyên đến khi Foundry chạy ổn (xem "Chưa quyết" 1).
- Model không phải của OpenAI cần resource loại `AIServices`; resource loại `OpenAI` chỉ deploy được model OpenAI
  (memory, chưa kiểm chứng; nếu sai thì vẫn dùng resource mới cho gọn).

### Backend

1. **Profile theo model** (`ModelProfile` trong `infrastructure/llm.py`). Model cùng một endpoint nhận tham số khác
   nhau, nên tham số tính theo model, không theo provider:
   - `temperature`: dòng `gpt-5` chỉ nhận giá trị mặc định → không gửi;
   - `json_schema`, `max_tokens_param`, `reasoning_effort` (`gpt-5-mini`: `minimal`, `gpt-oss-120b`: `low`);
   - `reasoning_headroom`: token suy nghĩ tính vào giới hạn token ra; router chỉ cho 32 token, model reasoning sẽ
     trả về rỗng. Cộng thêm phần này vào giới hạn khi gọi model reasoning.
   Không có profile thì dùng mặc định của provider như hiện nay. Giá trị cụ thể chốt sau khi gọi thử mỗi model một
   lần (commit 2).
2. **Provider `foundry`**: `base_url_env = AZURE_FOUNDRY_BASE_URL`, `key_env = AZURE_FOUNDRY_API_KEY`, danh sách
   model từ `AZURE_FOUNDRY_MODELS` (model đầu là mặc định). Thêm trường chung `models_env` vào `Provider`.
3. Port `ChatModels` thêm `models(provider) -> list[str]` (rỗng = gõ tự do như cũ). `GET /llm/providers` trả thêm
   `models: {provider: [...]}`. `Conversations` từ chối model không có trong danh sách của provider đó, để không ai
   gọi được deployment hay model ngoài ý muốn.

### Giao diện

Nút cài đặt: provider có danh sách model thì hiện `Select`, không có thì giữ `TextInput`. Khung chi tiết của mỗi câu
trả lời đã có dòng "LLM" (`present.py`), người test biết câu nào do model nào trả lời.

### Gửi cho người test

- Kiên gửi qua kênh riêng (Zalo/Messenger), không đưa vào git: link app, tài khoản (`sv001`…`sv008`, `cvht01`),
  mật khẩu `DEPLOY_DEMO_PASSWORD`, và cách thử: nút cài đặt cạnh ô nhập → chọn nhà cung cấp `foundry` và model →
  hỏi → bấm 👍/👎, ghi nhận xét.
- Kiên so sánh trong console (trace ghi `provider/model` của từng câu, cùng feedback).
- Chặn tiêu tiền: `capacity` từng deployment (tốc độ token), budget $20 gửi email cảnh báo (`budget.tf`).

## Kế hoạch commit

Mỗi bước: `ruff`, `pytest`; bước Terraform thêm `terraform fmt -check`, `validate`.

| # | Commit | Nội dung | Trạng thái |
|---|---|---|---|
| 1 | `docs(design): models on Azure AI Foundry` | file này, link trong `docs/README.md` | |
| 2 | `feat(infra): Foundry account and model deployments` | `foundry.tf`, biến, output. Apply; gọi thử mỗi model một câu ngắn có `json_schema` (báo token) | |
| 3 | `feat(backend): per-model parameters` | `ModelProfile`, profile cho các model ở bảng trên; test (không gọi LLM thật) | |
| 4 | `feat(backend): foundry provider with a fixed model list` | `models_env`, provider `foundry`, `ChatModels.models`, API trả `models`, kiểm tra model; `.env.example`; test | |
| 5 | `feat(web): pick the model from a list` | `Select` khi có danh sách; test | |
| 6 | `docs: Foundry models` | README gốc, README infra (lấy key), `architecture.md`. Deploy lên VM, hỏi thử mỗi model một câu | |

## Chưa quyết

1. **Gộp `gpt-4.1-mini` vào resource Foundry** rồi xóa resource `OpenAI` cũ và provider `azure`: gọn hơn (một
   provider), nhưng đổi cấu hình bản deploy đang chạy. Đề xuất làm sau buổi test, nhánh riêng.
2. **Endpoint v1 cho model không phải OpenAI** (`/openai/v1/chat/completions`, `model` = tên deployment): memory,
   chưa kiểm chứng; kiểm ở commit 2.
3. **Azure for Students có cho deploy Llama/Mistral không** (model của bên thứ ba): chỉ biết khi apply. Bị từ chối
   thì bỏ model đó khỏi `foundry_models`.
4. **`json_schema` với Llama/Mistral**: chưa rõ; mặc định tắt (Advisor đã chạy được khi không có structured output,
   như provider `kimi`), bật nếu gọi thử thành công.
5. **Giới hạn số câu mỗi tài khoản mỗi ngày**: chưa có. Làm nếu chi phí buổi test cao hơn dự kiến.
6. **Eval theo từng model**: tốn token, chỉ chạy khi Kiên bảo.
