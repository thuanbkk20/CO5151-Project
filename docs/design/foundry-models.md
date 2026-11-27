# Nhiều model trên Azure AI Foundry

Cập nhật: 2026-11-27. Nhánh `feat/foundry-models` (tách từ `feat/azure-openai`). Người làm: Kiên.

## Mục tiêu

- Nhóm và thầy thử app với nhiều model khác nhau ngay trên bản deploy: chọn model trong nút cài đặt cạnh ô nhập,
  hỏi, đánh giá 👍/👎. Không cần key mới, không cần tài khoản ở dịch vụ khác.
- Mọi model nằm trên **một** resource Azure AI Foundry (một endpoint, một key), trừ vào credit Azure for Students,
  khai báo bằng Terraform như phần còn lại của `infra/azure/`.
- Mọi provider có danh sách model chuẩn bị sẵn; người dùng chỉ chọn trong danh sách, không gõ tên (Kiên, 27/11).
  Danh sách nằm một chỗ (`PROVIDERS` trong `infrastructure/llm.py`), Kiên tự cập nhật.

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
| `Phi-4` | Microsoft | 20 | $0.125 / $0.50 (eastus, không thấy giá koreacentral) | $0.002 |

  P02 là 12.264 token vào + 1.675 token ra ([architecture.md](architecture.md)). DeepSeek, Kimi, Qwen, `gpt-5.x` có
  trong catalog nhưng quota bằng 0. `mistral-medium-2505` có quota nhưng ngừng chạy 09/12/2026
  (`az cognitiveservices model list`, `deprecation.inference`), trùng ngày bảo vệ. `mistral-small-2503` bị từ chối khi
  apply (27/11): model của Mistral mua qua Marketplace, `PaidPurchaseWithFreeSubscription: The plan
  'mistral-small-2503-plan' can't be purchased using a free subscription`. Llama, Phi do Azure bán trực tiếp nên được.

- Gọi thử mỗi model một câu (27/11, 8 lần gọi, 245 token vào + 132 ra), `temperature=0` và `response_format`
  json_schema strict:

| Model | `temperature=0` | `json_schema` | Ghi chú |
|---|---|---|---|
| `gpt-5-mini` | 400 `Only the default (1) value is supported` | được | `reasoning_effort=minimal`: 0 token suy nghĩ |
| `gpt-oss-120b` | được | được | `reasoning_effort=low`: 51 token ra cho JSON 1 trường, có token suy nghĩ (API không báo số) |
| `Llama-3.3-70B-Instruct` | được | được | |
| `Phi-4` | được | 422 `response_format.type` không hợp lệ | |

## Thiết kế

### Terraform (`infra/azure/foundry.tf`)

| Resource | Nội dung |
|---|---|
| `azurerm_cognitive_account.foundry` | `kind = "AIServices"`, `sku_name = "S0"`, `location = var.openai_location`, `custom_subdomain_name = var.foundry_subdomain` (`co5151-g3-foundry`) |
| `azurerm_cognitive_deployment.foundry` | `for_each = var.foundry_models`; tên deployment = tên model; `model { format, name, version }`, `sku { GlobalStandard, capacity }` |

- `var.foundry_models`: map tên → `{ format, version, capacity }`. Thêm model = thêm một dòng rồi `apply`.
- Output `foundry_base_url` (`https://<subdomain>.openai.azure.com/openai/v1/`) để chép vào `.env`. Key lấy bằng
  `az ... keys list` như Azure OpenAI. Thêm deployment thì thêm tên vào danh sách của provider `foundry` trong code.
- Resource `OpenAI` cũ giữ nguyên đến khi Foundry chạy ổn (xem "Chưa quyết" 1).
- Model không phải của OpenAI cần resource loại `AIServices`; resource loại `OpenAI` chỉ deploy được model OpenAI
  (memory, chưa kiểm chứng). Endpoint v1 `https://<subdomain>.openai.azure.com/openai/v1/` gọi được cả 4 model
  (gọi thử 27/11).

### Backend

1. **Profile theo model** (`ModelProfile` trong `infrastructure/llm.py`). Model cùng một endpoint nhận tham số khác
   nhau, nên tham số tính theo model, không theo provider:
   - `temperature`: dòng `gpt-5` chỉ nhận giá trị mặc định → không gửi;
   - `json_schema`, `max_tokens_param`, `reasoning_effort` (`gpt-5-mini`: `minimal`, `gpt-oss-120b`: `low`);
   - `reasoning_headroom`: token suy nghĩ tính vào giới hạn token ra; router chỉ cho 32 token, model reasoning sẽ
     trả về rỗng. Cộng thêm phần này vào giới hạn khi gọi model reasoning.
   Không có profile thì dùng mặc định của provider như hiện nay. Giá trị theo bảng gọi thử ở trên.
2. **Provider `foundry`**: `base_url_env = AZURE_FOUNDRY_BASE_URL`, `key_env = AZURE_FOUNDRY_API_KEY`.
3. **Danh sách model trong code**: `Provider.models` (tuple, model đầu là mặc định) thay cho `Provider.model`, cho mọi
   provider. Bỏ `models_env` / `AZURE_FOUNDRY_MODELS` của commit 4: hai chỗ phải cập nhật là thừa. `LLM_MODEL` (cấu
   hình của người vận hành, ví dụ server local) được thêm vào đầu danh sách của provider mặc định.
4. Port `ChatModels.models(provider)`; `GET /llm/providers` trả `models: {provider: [...]}`. `Conversations` từ chối
   model ngoài danh sách (người dùng không gọi được model ngoài ý muốn). Hội thoại cũ lưu model không còn trong danh
   sách thì `AskQuestion` dùng model mặc định của provider, không báo lỗi. Cấu hình của server (`VERIFIER_LLM_MODEL`)
   không bị danh sách chặn.

### Giao diện

Nút cài đặt: một ô `Select` "Model" liệt kê `provider · model` của mọi provider có key (form của Chainlit không đổi
được ô này khi ô kia đổi, nên gộp provider và model làm một); không còn ô gõ tên model. Khung chi tiết của mỗi câu
trả lời đã có dòng "LLM" (`present.py`), người test biết câu nào do model nào trả lời.

### Gửi cho người test

- Kiên gửi qua kênh riêng (Zalo/Messenger), không đưa vào git: link app, tài khoản (`sv001`…`sv008`, `cvht01`),
  mật khẩu `DEPLOY_DEMO_PASSWORD`, và cách thử: nút cài đặt cạnh ô nhập → ô "Model" chọn ví dụ `foundry · gpt-5-mini` →
  hỏi → bấm 👍/👎, ghi nhận xét.
- Kiên so sánh trong console (trace ghi `provider/model` của từng câu, cùng feedback).
- Chặn tiêu tiền: `capacity` từng deployment (tốc độ token), budget $20 gửi email cảnh báo (`budget.tf`).

## Kế hoạch commit

Mỗi bước: `ruff`, `pytest`; bước Terraform thêm `terraform fmt -check`, `validate`.

| # | Commit | Nội dung | Trạng thái |
|---|---|---|---|
| 1 | `docs(design): models on Azure AI Foundry` | file này, link trong `docs/README.md` | xong `7532c86` |
| 2 | `feat(infra): Foundry account and model deployments` | `foundry.tf`, biến, output. Apply; gọi thử mỗi model một câu ngắn có `json_schema` (báo token) | xong `70f4705` |
| 3 | `feat(backend): per-model parameters` | `ModelProfile`, profile cho các model ở bảng trên; test (không gọi LLM thật) | xong `da51f09` |
| 4 | `feat(backend): foundry provider with a fixed model list` | `models_env`, provider `foundry`, `ChatModels.models`, API trả `models`, kiểm tra model; `.env.example`; test | xong `bf00571` |
| 5 | `feat(web): pick the model from a list` | một ô `Select` gộp provider và model (form Chainlit không đổi ô này theo ô kia), ô chữ cho provider không có danh sách; test | xong `c8b1013` |
| 6 | `docs: Foundry models` | README gốc, README infra (lấy key), `architecture.md` | xong `6ff7419` |
| 7 | `docs(design): a prepared model list for every provider` | sửa plan theo yêu cầu của Kiên (27/11) | xong `e942abd` |
| 8 | `feat(backend): a prepared model list for every provider` | `Provider.models`, bỏ `models_env` và output `foundry_models`; hội thoại cũ về model mặc định; `.env.example`; test | xong `a3e7144` |
| 9 | `feat(web): no free-text model` | bỏ ô gõ tên model; test | xong `db9158b` |
| 10 | `docs: model list` | README, README infra, `architecture.md`. Deploy lên VM (cần push nhánh), hỏi thử mỗi model một câu | xong `f6b438c`; deploy 27/11 |

## Chưa quyết

1. **Gộp `gpt-4.1-mini` vào resource Foundry** rồi xóa resource `OpenAI` cũ và provider `azure`: gọn hơn (một
   provider), nhưng đổi cấu hình bản deploy đang chạy. Đề xuất làm sau buổi test, nhánh riêng.
2. ~~Endpoint v1 cho model không phải OpenAI~~ → **được** (gọi thử 27/11).
3. ~~Azure for Students có cho deploy Llama/Mistral không~~ → Llama **được**, Mistral **không** (Marketplace); thay
   bằng `Phi-4`.
4. ~~`json_schema` với model ngoài OpenAI~~ → Llama được, Phi-4 không (tắt cho Phi-4; Advisor vẫn chạy khi không có
   structured output, như provider `kimi`).
5. **Giới hạn số câu mỗi tài khoản mỗi ngày**: chưa có. Làm nếu chi phí buổi test cao hơn dự kiến.
6. **Eval theo từng model**: tốn token, chỉ chạy khi Kiên bảo.
7. **Hỏi thử trên bản deploy** (27/11, `sv001`, "Điều kiện để được xét tốt nghiệp là gì?", 5 câu, tổng 43.606 token
   vào + 7.270 ra, khoảng $0.02 theo giá ở bảng trên):
   - chỉ `gpt-oss-120b` trả lời (44 s); `gpt-4.1-mini`, `Llama-3.3-70B-Instruct`, `Phi-4` bị Verifier từ chối
     (`outcome=refuse`, 2 vòng). `gpt-4.1-mini` gửi tham số như trước nhánh này, nên từ chối nhiều khả năng không do
     nhánh này (đoán); cần xem trace trong console.
   - `gpt-5-mini`: bước soạn câu trả lời trả rỗng (`answer LLM call failed, falling back: empty reply`), chưa rõ vì
     sao (log không ghi `finish_reason`).

## Sửa sau khi test (27/11)

Kiên test trên bản deploy: gần như câu nào cũng ra câu từ chối. Trace (bảng `traces`, `trace_spans` trên VM):

- Verifier trả `revise` 2 vòng rồi từ chối vì những lỗi không có thật: "Bản nháp nêu rằng 'Đồ án chuyên ngành' chưa
  đạt, nhưng hồ sơ chỉ nêu 'capstone_project_passed': false" (Phi-4); đòi bằng chứng cho mọi điều kiện dù bản nháp
  đã kết luận "chưa đủ điều kiện" vì thiếu tín chỉ (gpt-5-mini làm judge); tự mâu thuẫn "FACT_MISMATCH: ... đúng với
  dữ liệu" (gpt-4.1-mini).
- Judge dùng chính model của hội thoại: model yếu chấm yếu, và so sánh model không công bằng (đổi cả người viết lẫn
  người chấm).
- `gpt-5-mini`: bước soạn trả rỗng, không biết lý do (lỗi không ghi `finish_reason`).
- `gemini-2.5-flash`: 404 "no longer available to new users". Gemini lại không gọi được từ VM ở Hong Kong
  ([azure-openai.md](azure-openai.md)), nên bản deploy không nên có Gemini.
- Dòng "✓ Verifier đã kiểm" vẫn hiện khi Verifier đã từ chối.

| # | Commit | Nội dung | Trạng thái |
|---|---|---|---|
| 11 | `docs(design): fixes after the first test` | mục này | xong `c411494` |
| 12 | `feat(backend): Verifier judge on its own provider` | `VERIFIER_LLM_PROVIDER` (+ `VERIFIER_LLM_MODEL` có sẵn): judge cố định, không theo model hội thoại; bản deploy dùng `foundry/gpt-oss-120b` (xem dưới) | xong `2371989` |
| 13 | `fix(backend): judge flags only errors that make the answer wrong` | prompt judge: diễn đạt lại một trường hồ sơ không phải lỗi; một điều kiện không đạt đủ để kết luận chưa đủ điều kiện; thông tin bản nháp nói rõ là chưa có không phải lỗi; không liệt kê điều đúng | xong `276ffb5` |
| 13b | `fix(backend): the judge's missing evidence asks for a rewrite` | judge vẫn báo `MISSING_EVIDENCE` cho một ý phụ, từ chối ngay cả câu trả lời; từ judge nó thành viết lại (luật trích dẫn khi không tra được gì vẫn từ chối); ý bản nháp tự nói là chưa chắc không phải khẳng định | xong `9e9f2dc` |
| 14 | `fix(backend): say why a reply is empty` | `LLMError` ghi `finish_reason`; gọi thử `gpt-5-mini` 1 câu để biết lý do rồi sửa profile | xong `60bff72`: `finish_reason=length`, hết 1280 token cho suy nghĩ dù `minimal`; `reasoning_headroom` 2048 |
| 15 | `fix(backend): drop gemini-2.5-flash` | bỏ khỏi danh sách; `.env.production` bỏ key Gemini | xong `2829d5f` |
| 16 | `fix(web): a refused answer is not shown as verified` | dòng dưới câu trả lời ghi "Verifier không cho qua" khi `outcome=refuse` | xong `4366c2c` |
| 17 | `fix(backend): the Advisor does not invent conditions or thresholds` | sau khi đổi judge, lỗi còn lại là thật: model coi Đồ án chuyên ngành là điều kiện, tự đặt ngưỡng CGPA 2.0 / TOEIC 450, ghi sai GDQP. Prompt: chỉ nêu điều kiện, ngưỡng có trong quy chế; quy chế không nêu ngưỡng thì nói rõ; viết lại thì bỏ hẳn ý không có căn cứ. Chạy thử 3 model (24.0k + 4.4k token): cả 3 qua | |

Chọn judge (chạy trong process như eval, `sv001`, "Điều kiện để được xét tốt nghiệp là gì?", 27/11): judge
`azure/gpt-4.1-mini` sau các sửa trên cho `gpt-4.1-mini` qua (viết lại 1 lần) nhưng vẫn từ chối `gpt-5-mini` vì coi
câu "có thể chưa đạt" về ngưỡng CGPA/TOEIC là khẳng định. Judge `foundry/gpt-oss-120b`: cả hai qua, lỗi nó bắt ở vòng
1 là lỗi thật (quy chế không nêu mức TOEIC; đồ án không phải điều kiện tốt nghiệp), và rẻ nhất. Bản deploy:
`VERIFIER_LLM_PROVIDER=foundry`, `VERIFIER_LLM_MODEL=gpt-oss-120b`. Các lần chạy thử khi sửa tốn khoảng 100 nghìn
token (đoán theo số in ra, dưới $0.1).

Sau đó deploy và hỏi lại 5 câu như lần trước (báo token).
