# LLM trên Azure OpenAI

Cập nhật: 2026-11-26. Nhánh `feat/azure-openai` (tách từ `feat/deploy`). Người làm: Kiên.

## Vì sao

- VM ở `eastasia` (Hong Kong) gọi Gemini bị từ chối: log `co5151-api` ngày 26/11, mọi lời gọi trả
  `400 'User location is not supported for the API use.' FAILED_PRECONDITION`, app trả câu dự phòng.
- Dời VM sang region khác thì mất VM miễn phí: B2ats v2 chỉ dùng được ở `eastasia` (xem [deploy.md](deploy.md),
  "Chưa quyết" 1); `koreacentral` chỉ có cỡ trả phí (B2ts v2 $0.013/giờ, Azure Retail Prices API 26/11).
- Azure for Students có quota Azure OpenAI ở `koreacentral` (`az cognitiveservices usage list -l koreacentral`,
  26/11: `OpenAI.GlobalStandard.gpt4.1-mini 0 / 200`), không có ở `eastasia` (chỉ quota fine-tune và provisioned
  bằng 0). Token trừ vào credit $100, không cắm thẻ.

## Mục tiêu

- App (cả local lẫn bản deploy) gọi `gpt-4.1-mini` trên một resource Azure OpenAI của nhóm ở `koreacentral`; VM vẫn
  ở `eastasia`, miễn phí.
- Resource khai báo bằng Terraform cùng chỗ với VM (`infra/azure/`).
- Đi qua `PROVIDERS` như provider khác: thêm một provider `azure`, không viết client riêng. Gemini, OpenAI, Kimi vẫn
  dùng được như cũ.

## Thiết kế

### Model

`gpt-4.1-mini` phiên bản `2025-04-14`, SKU `GlobalStandard` (`az cognitiveservices model list -l koreacentral`, 26/11:
trạng thái `Legacy`, ngừng chạy 2027-04-14). Chọn vì:

- là model mặc định của provider `openai` sẵn có trong repo;
- nhận `temperature=0`, `response_format` json_schema và `max_completion_tokens` mà `OpenAICompatibleChatModel` gửi;
  dòng GPT‑5 là model reasoning, không nhận `temperature` khác mặc định (memory, chưa kiểm chứng);
- giá $0.40 / $1.60 mỗi 1M token vào/ra (Global, Retail Prices API 26/11). Một câu như P02 (12.264 + 1.675 token,
  [architecture.md](architecture.md)) khoảng $0.008.

`GlobalStandard` nghĩa là Azure có thể xử lý request ở datacenter khác ngoài `koreacentral`. Dữ liệu sinh viên là
mô phỏng nên chấp nhận được.

### Terraform (`infra/azure/openai.tf`)

| Resource | Nội dung |
|---|---|
| `azurerm_cognitive_account.openai` | `kind = "OpenAI"`, `sku_name = "S0"`, `location = var.openai_location` (`koreacentral`), `custom_subdomain_name = var.openai_subdomain` (`co5151-g3-openai`, phải duy nhất toàn cầu), nằm trong resource group của app |
| `azurerm_cognitive_deployment.chat` | tên = tên model (`gpt-4.1-mini`), model `OpenAI` / `gpt-4.1-mini` / `2025-04-14`, `sku { name = "GlobalStandard", capacity = var.openai_capacity }` (đơn vị nghìn token mỗi phút, đoán; mặc định 50, quota 200) |

- Provider `Microsoft.CognitiveServices` thêm vào `resource_providers_to_register`.
- Output `openai_base_url` = `<endpoint>openai/v1/` (không phải secret).
- Key: lấy bằng `az cognitiveservices account keys list` ghi thẳng vào `.env` / `.env.production`, không in ra màn
  hình, không làm output. Terraform state vẫn chứa key (thuộc tính của resource), state đã gitignore.

### Backend

Endpoint v1 của Azure OpenAI nhận client OpenAI thường: `base_url = https://<subdomain>.openai.azure.com/openai/v1/`,
`api_key = <key>`, `model = <tên deployment>` (tài liệu Microsoft, memory, chưa kiểm chứng; kiểm bằng một lời gọi
thật sau khi apply).

- `Provider` thêm trường `base_url_env`: provider có base URL theo từng resource đọc nó từ biến môi trường.
- `PROVIDERS["azure"]`: `base_url_env="AZURE_OPENAI_BASE_URL"`, `key_env="AZURE_OPENAI_API_KEY"`,
  `model="gpt-4.1-mini"`, `json_schema=True`, `max_tokens_param="max_completion_tokens"`.
- Provider chỉ hiện trong giao diện khi có cả key lẫn base URL.
- `.env.example`: hai biến mới; `LLM_PROVIDER` ghi thêm `azure`.

### Chuyển local và bản deploy sang Azure

Trong `.env` và `.env.production`: `LLM_PROVIDER=azure`, hai biến `AZURE_OPENAI_*`, **xóa `LLM_MODEL`** (nếu còn
`LLM_MODEL=gemini-...` thì nó đè model của provider mặc định, Azure sẽ báo không có deployment đó). Key Gemini giữ
lại: Gemini vẫn chọn được trong nút cài đặt ở local.

## Kế hoạch commit

| # | Commit | Nội dung | Trạng thái |
|---|---|---|---|
| 1 | `docs(design): LLM on Azure OpenAI` | file này, link trong `docs/README.md` | xong `d97780f` |
| 2 | `feat(infra): Azure OpenAI account and gpt-4.1-mini deployment` | `openai.tf`, biến, output, đăng ký provider. Apply (26/11): 2 resource, endpoint `co5151-g3-openai` | xong `e636dda` |
| 3 | `feat(backend): azure provider` | `base_url_env`, `PROVIDERS["azure"]`, `.env.example`, test (không gọi LLM thật) | xong `4e75a17` |
| 4 | `docs: Azure OpenAI` | README gốc (provider), README infra (lấy key vào `.env`), `deploy.md`. Kiên thử một câu ở local rồi deploy | |

## Chưa quyết

1. ~~Gọi từ Hong Kong~~ → **được** (26/11): `curl` từ VM tới `chat/completions` của deployment trả HTTP 200. Ở local
   gọi qua provider `azure` cũng được (24 token vào, 1 token ra).
2. **Không dùng key** (Entra ID: `az login` ở local, managed identity trên VM) an toàn hơn, nhưng cần thêm thư viện
   `azure-identity`. Chưa làm.
3. **Eval với `gpt-4.1-mini`**: bộ eval mới chạy với Gemini; chạy lại với Azure tốn token, chỉ chạy khi Kiên bảo.
4. **Giới hạn chi tiêu**: trang public, chưa giới hạn số câu mỗi tài khoản. Budget $20/tháng của subscription vẫn gửi
   email cảnh báo; `openai_capacity` giới hạn tốc độ token.
