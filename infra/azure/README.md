# Hạ tầng Azure (Terraform)

Dựng máy chạy app trên subscription **Azure for Students** ($100 credit, không cắm thẻ; hết credit thì subscription bị
tắt chứ không trừ tiền), để nhóm và thầy dùng thử và demo bảo vệ.

## Thiết kế

```
Internet ──443──> Caddy (HTTPS) ──> Chainlit 127.0.0.1:8000 ──> backend :8100 ──> MCP :8102, :8103
                   VM Ubuntu B2ats v2 ở eastasia, NSG chỉ mở 80/443 (+22 từ IP của Kiên)
```

- **Vì sao Azure for Students:** Cloudflare Workers không chạy được Chainlit (WebAssembly, không thread, không giữ
  file); Cloudflare Containers cần gói trả phí; Cloudflare Tunnel cần domain riêng; GCP phải cắm thẻ. B2ats v2 (2
  vCPU, 1 GB, thêm swap 2 GB) miễn phí 750 giờ, nhưng chỉ có ở `eastasia`. 5 process đo được khoảng 425 MB RAM.
- **Hạ tầng tách khỏi cập nhật app:** cloud-init chỉ dựng máy một lần (đổi `custom_data` là Terraform tạo lại VM và
  mất SQLite); cập nhật code bằng `deploy.sh`. State Terraform để local (một người apply).
- **Bảo mật:** mọi service nghe `127.0.0.1`, chỉ Caddy nghe 80/443. Secret (`.env`, mật khẩu) không nằm trong git hay
  biến Terraform (state ghi giá trị rõ); `deploy.sh` chép `.env` bằng `scp`, `chmod 600`. Bản deploy tắt `khach`
  (`GUEST_LOGIN=off`) và thay mật khẩu `demo` bằng `DEPLOY_DEMO_PASSWORD` (`accounts.py`, file chỉ lưu hash), vì mỗi
  câu hỏi tốn tiền key LLM. Console tắt mặc định.
- **LLM:** Gemini từ chối request từ VM ở Hong Kong (`400 User location is not supported`, 26/11), nên bản deploy dùng
  Azure OpenAI / AI Foundry ở `koreacentral` (có quota, token trừ vào credit). Model và judge: xem
  [architecture.md](../../docs/design/architecture.md), mục "Model LLM".
- **Chi phí:** VM $0 (trong mức miễn phí); public IP Standard khoảng $3.6/tháng (chưa kiểm chứng); budget $20 có
  email cảnh báo 50%, 100% (`budget.tf`).

## Cài công cụ (một lần)

| Công cụ | Cách cài (macOS arm64, không cần Homebrew) | Gỡ |
|---|---|---|
| Terraform ≥ 1.9 | Tải `terraform_<ver>_darwin_arm64.zip` từ releases.hashicorp.com, kiểm `SHA256SUMS`, giải nén vào `~/.local/bin` | `rm ~/.local/bin/terraform` |
| Azure CLI | `uv tool install --python 3.12 azure-cli` (không chính thức; Microsoft hướng dẫn Homebrew) | `uv tool uninstall azure-cli` |

## Chạy

```bash
cd infra/azure
az login             # đăng nhập; Terraform dùng subscription mặc định của az ("Azure for Students")
terraform init       # lần đầu, hoặc khi đổi provider: tải provider vào .terraform/ (~300 MB)
terraform plan       # xem sẽ tạo / sửa / xóa gì; chưa đụng vào Azure
terraform apply      # in lại plan, gõ "yes" mới thực hiện
terraform output     # xem output (URL, lệnh SSH...)
terraform destroy    # xóa mọi resource do Terraform tạo
```

Đổi giá trị biến: `cp terraform.tfvars.example terraform.tfvars` rồi sửa (file này gitignore). Không ghi secret vào
biến Terraform.

Tài khoản có nhiều subscription thì chỉ định rõ, kẻo Terraform tạo resource vào subscription mặc định đang chọn của
`az`: `export ARM_SUBSCRIPTION_ID=$(az account show --name "Azure for Students" --query id -o tsv)`. Trên CI
(không có `az login`) biến này là bắt buộc.

## Đưa app lên và cập nhật app

Terraform chỉ dựng máy (cloud-init chạy một lần). Đưa code và cấu hình lên bằng `deploy.sh`, chạy lại mỗi khi muốn
cập nhật:

```bash
cp .env .env.production         # ở gốc repo; gitignore. Sửa: secret mới (khác máy local), key LLM, và
                                # DEPLOY_DEMO_PASSWORD (mật khẩu chung của tài khoản demo, ≥ 12 ký tự)
infra/azure/deploy.sh main      # hoặc tên nhánh/tag/commit khác trên origin (phải push trước)
```

Script đẩy `.env` (bỏ dòng `DEPLOY_*`, thêm `GUEST_LOGIN=off` và `DEMO_ACCOUNTS_FILE`, quyền 600) và Caddyfile qua
SSH; checkout ref, `uv sync --locked --no-dev`; ghi `/opt/co5151/accounts.json` (tài khoản demo, hash của
`DEPLOY_DEMO_PASSWORD`, bằng `accounts.py`); khởi động lại `co5151.target` và Caddy; kiểm tra `khach` và mật khẩu
`demo` bị từ chối, trang trả 200. Code trên server chỉ lấy từ `origin`, nên commit chưa push thì không deploy được.
Ref phải có `GUEST_LOGIN` (từ `ffae96f`), nếu không bước kiểm tra `khach` sẽ báo lỗi.

## Azure OpenAI

`openai.tf` tạo resource Azure OpenAI ở `koreacentral` và deployment `gpt-4.1-mini` (lý do: mục "Thiết kế" ở trên). Để app (local hoặc bản deploy) dùng nó, ghi vào
`.env` / `.env.production`, key đi thẳng vào file, không in ra màn hình:

```bash
# ở gốc repo; đổi .env thành .env.production cho bản deploy. Xóa LLM_MODEL nếu đang đặt model của provider khác.
{ echo "AZURE_OPENAI_BASE_URL=$(terraform -chdir=infra/azure output -raw openai_base_url)"
  echo "AZURE_OPENAI_API_KEY=$(az cognitiveservices account keys list -n co5151-openai -g co5151-rg --query key1 -o tsv)"
} >> .env
# rồi đặt LLM_PROVIDER=azure
```

Đổi key (khi lộ): `az cognitiveservices account keys regenerate -n co5151-openai -g co5151-rg --key-name key1`, ghi
lại vào `.env` và chạy `deploy.sh`.

## Azure AI Foundry

`foundry.tf` tạo resource `AIServices` ở `koreacentral` và một deployment cho mỗi model trong `foundry_models`
(`variables.tf`; model nào, vì sao: [architecture.md](../../docs/design/architecture.md), mục "Model LLM").
Thêm model: thêm một dòng vào `foundry_models` (tên, format, phiên bản, capacity), `terraform apply`, thêm tên vào
danh sách của provider `foundry` trong `PROVIDERS` (`backend/src/co5151_backend/infrastructure/llm.py`); model gửi
tham số khác mặc định thì thêm vào `MODEL_PROFILES` cùng file. Model bán qua Marketplace (Mistral...) không deploy
được trên subscription miễn phí.

```bash
# ở gốc repo; đổi .env thành .env.production cho bản deploy
{ echo "AZURE_FOUNDRY_BASE_URL=$(terraform -chdir=infra/azure output -raw foundry_base_url)"
  echo "AZURE_FOUNDRY_API_KEY=$(az cognitiveservices account keys list -n co5151-foundry -g co5151-rg --query key1 -o tsv)"
} >> .env
```

Đổi key: như Azure OpenAI, thay `co5151-openai` bằng `co5151-foundry`.

## Vận hành trên VM

Trên VM (`terraform output ssh_command`):

```bash
systemctl status 'co5151-*' caddy          # trạng thái
journalctl -u co5151-api -f                 # log backend (tương tự co5151-web, co5151-student, ...)
sudo systemctl start co5151-console         # console vận hành; xem từ máy bạn qua tunnel:
                                            # ssh -i ~/.ssh/co5151_azure -L 8200:127.0.0.1:8200 azureuser@<fqdn>
```

## Terraform hoạt động thế nào

- **Code `.tf` khai báo trạng thái muốn có** ("có một resource group tên `co5151-rg` ở `eastasia`"), không phải các
  bước tạo. Terraform đọc mọi file `.tf` trong thư mục như một khối (root module); tên file chỉ để dễ đọc.
- **Provider** (`azurerm`) là plugin gọi API của Azure. `init` tải nó và ghi phiên bản cùng checksum vào
  `.terraform.lock.hcl` (commit file này để mọi người, cả CI, dùng đúng một bản).
- **State** (`terraform.tfstate`) ghi lại resource Terraform đã tạo và id của chúng trên Azure. `plan` so sánh code,
  state và Azure thật để tính phần chênh. Mất state thì Terraform "quên" resource (vẫn còn trên Azure, phải
  `terraform import` hoặc xóa tay). State chứa mọi thuộc tính resource ở dạng rõ, nên không commit và không đưa
  secret vào biến.
- **Ở đây state để local** vì chỉ một người apply. Nhóm hoặc công ty để state ở **remote backend** (Azure Storage, S3,
  GCS) có khóa, để nhiều người và CI dùng chung mà không ghi đè nhau:

  ```hcl
  terraform {
    backend "azurerm" {
      resource_group_name  = "tfstate-rg"
      storage_account_name = "<tên>"
      container_name       = "tfstate"
      key                  = "co5151.tfstate"
    }
  }
  ```

## CI ở công ty chạy Terraform thế nào

Cách phổ biến (GitHub Actions, GitLab CI, Atlantis đều theo ý này):

1. **Mở PR**: CI chạy `terraform fmt -check`, `init`, `validate`, `plan`, rồi đăng kết quả `plan` vào PR để
   người review thấy hạ tầng sẽ đổi gì.
2. **Merge vào nhánh chính**: CI chạy `terraform apply` (thường dùng đúng file plan đã lưu,
   `terraform plan -out=tfplan` rồi `terraform apply tfplan`), hay có bước duyệt tay (GitHub Environments).
3. **Đăng nhập cloud không cần key lưu sẵn**: CI dùng OIDC. GitHub cấp token ngắn hạn cho job, cloud (Azure/GCP/AWS)
   được cấu hình tin token đó và đổi thành quyền của một service principal / service account. Biến
   `ARM_USE_OIDC`, `ARM_CLIENT_ID`, `ARM_TENANT_ID`, `ARM_SUBSCRIPTION_ID` thay cho `az login`.
4. **State** đọc từ remote backend, nên máy CI và máy người dùng thấy cùng một trạng thái.

Repo này chỉ chạy bước kiểm tra (`fmt`, `validate`) trong CI; `apply` chạy tay từ máy Kiên.
