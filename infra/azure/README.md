# Hạ tầng Azure (Terraform)

Dựng máy chạy app trên subscription **Azure for Students**. Thiết kế và lý do: [docs/design/deploy.md](../../docs/design/deploy.md).

## Cài công cụ (một lần)

| Công cụ | Cách cài (macOS arm64, không cần Homebrew) | Gỡ |
|---|---|---|
| Terraform ≥ 1.9 | Tải `terraform_<ver>_darwin_arm64.zip` từ releases.hashicorp.com, kiểm `SHA256SUMS`, giải nén vào `~/.local/bin` | `rm ~/.local/bin/terraform` |
| Azure CLI | `uv tool install --python 3.12 azure-cli` (không chính thức; Microsoft hướng dẫn Homebrew) | `uv tool uninstall azure-cli` |

## Chạy

```bash
cd infra/azure
az login                                                     # đăng nhập, chọn subscription "Azure for Students"
export ARM_SUBSCRIPTION_ID=$(az account show --query id -o tsv)
terraform init       # lần đầu, hoặc khi đổi provider: tải provider vào .terraform/ (~300 MB)
terraform plan       # xem sẽ tạo / sửa / xóa gì; chưa đụng vào Azure
terraform apply      # in lại plan, gõ "yes" mới thực hiện
terraform output     # xem output (URL, lệnh SSH...)
terraform destroy    # xóa mọi resource do Terraform tạo
```

Đổi giá trị biến: `cp terraform.tfvars.example terraform.tfvars` rồi sửa (file này gitignore). Không ghi secret vào
biến Terraform.

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
