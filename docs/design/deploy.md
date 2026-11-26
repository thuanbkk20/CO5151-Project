# Triển khai lên Azure bằng Terraform

Cập nhật: 2026-11-26. Nhánh `feat/deploy`. Người làm: Kiên.

## Mục tiêu

- Có một bản chạy thật trên internet để nhóm và thầy dùng thử, demo bảo vệ vòng 2 (09/12/2026).
- Không tốn tiền thật: chạy trên subscription **Azure for Students** ($100 credit, không cắm thẻ; hết credit thì
  subscription bị tắt chứ không trừ tiền).
- An toàn: người lạ không hỏi được (mỗi câu hỏi tốn tiền key LLM): bản deploy tắt tài khoản `khach` và đổi mật khẩu
  `demo` (công khai trong README) thành mật khẩu riêng; chỉ Caddy nghe cổng ngoài, các service của app chỉ nghe
  `127.0.0.1`; secret không nằm trong git và không nằm trong Terraform state.
- Toàn bộ hạ tầng khai báo bằng Terraform: dựng lại, đổi cỡ máy, xóa sạch chỉ bằng một lệnh.

Ngoài phạm vi: Kubernetes, container, nhiều máy, database server riêng (vẫn dùng SQLite trên đĩa VM).

## Căn cứ chọn

| Lựa chọn | Lý do bỏ |
|---|---|
| Cloudflare Workers | Python Workers chạy trên WebAssembly: `threading` không chạy, filesystem mất khi isolate tắt; Chainlit cần server websocket chạy liên tục |
| Cloudflare Containers | Phải có gói Workers Paid $5/tháng |
| Cloudflare Tunnel + Access | Hostname công khai phải thuộc một domain trong account Cloudflare; nhóm chưa có domain |
| GCP e2-micro | Phải cắm thẻ; IP public khoảng $3.65/tháng trừ vào thẻ; credit $300 của Kiên đã dùng |

Đo RAM trên máy Kiên (26/11, macOS, không gọi LLM): 5 process khoảng 425 MB (api 121, web 116, console 69,
student 60, regulation 59). VM 1 GB đủ nếu thêm swap.

## Thiết kế

```
Internet ──443──> Caddy (HTTPS) ──> Chainlit 127.0.0.1:8000 ──> backend :8100 ──> MCP :8102, :8103
                   VM Ubuntu trên Azure, NSG chỉ mở 80/443 (+22 từ IP của Kiên)
```

### Thư mục `infra/azure/`

Terraform root module, không phải package Python (không thêm vào uv workspace). State để **local**
(`terraform.tfstate`, gitignore). Một người (Kiên) apply nên chưa cần remote state.

| File | Nội dung |
|---|---|
| `versions.tf` | Phiên bản Terraform, provider `azurerm` |
| `variables.tf`, `terraform.tfvars.example` | Region, cỡ máy, IP được SSH, SSH public key, nhánh git, email nhận cảnh báo |
| `network.tf` | VNet, subnet, NSG, public IP có DNS label (`<label>.<region>.cloudapp.azure.com`) |
| `vm.tf` | NIC, VM Ubuntu LTS, SSH key (tắt đăng nhập bằng mật khẩu), cloud-init |
| `cloud-init.yaml` | User `co5151`, swap 2 GB, cài `uv` và Caddy, clone repo, systemd unit cho từng process |
| `budget.tf` | Budget cho subscription, email cảnh báo khi chạm ngưỡng |
| `outputs.tf` | URL của app, lệnh SSH |
| `deploy.sh` | Cập nhật app: đẩy `.env` và Caddyfile, `git checkout`, `uv sync`, ghi file tài khoản có mật khẩu riêng, restart |
| `accounts.py` | Chạy trên VM: chép tài khoản demo của student-server, thay hash mật khẩu `demo` bằng hash mật khẩu riêng |
| `README.md` | Cách cài công cụ, chạy `init/plan/apply/destroy`, cập nhật app, Terraform state, cách CI chạy Terraform |

### Hạ tầng (Terraform) tách khỏi cập nhật app (`deploy.sh`)

- Đổi `custom_data` (cloud-init) làm Terraform **tạo lại VM** và mất SQLite. Vì vậy cloud-init chỉ dựng máy một lần;
  cập nhật code dùng `deploy.sh` (SSH vào, `git fetch`, `uv sync --locked --no-dev`, `systemctl restart`).
- Secret (`.env`, mật khẩu tài khoản) không đưa vào biến Terraform vì Terraform ghi giá trị biến vào state ở dạng
  rõ. `deploy.sh` chép `.env` lên bằng `scp`, `chmod 600`.

### Service trên VM

- 4 process: `student-mcp serve`, `regulation-mcp`, `co5151-api`, `co5151-web`, mỗi process một systemd unit chạy
  thẳng `.venv/bin/<lệnh>` (không qua `uv run`, đỡ khoảng 20–30 MB mỗi process), `Restart=on-failure`.
  Console tắt mặc định (bật bằng biến), vì dành cho nhóm vận hành.
- Mọi service nghe `127.0.0.1` (mặc định của `.env.example`). Chỉ Caddy nghe 80/443.
- Caddy: tự lấy chứng chỉ HTTPS cho tên miền `cloudapp.azure.com`; chuyển websocket của Chainlit. Không có basic
  auth (xem "Chưa quyết" 8).
- Đăng nhập: trang đăng nhập của Chainlit, như khi chạy local, nhưng
  - `GUEST_LOGIN=off`: backend từ chối `khach` (local vẫn bật);
  - `DEMO_ACCOUNTS_FILE=/opt/co5151/accounts.json`: cùng tài khoản `sv001` … `sv008`, `cvht01`, mật khẩu chung là
    `DEPLOY_DEMO_PASSWORD` trong `.env.production` (tối thiểu 12 ký tự). File chỉ lưu hash, quyền 600.
  - Kiên gửi mật khẩu cho nhóm và thầy qua kênh riêng; trang đăng nhập không ghi tài khoản (`c055328`).
- `.env` trên VM: `ADVISOR_VERIFIER=rules` để bớt lời gọi LLM (có thể đổi).

### Chi phí (trừ vào credit)

| Khoản | Ước tính | Căn cứ |
|---|---|---|
| VM B2ats v2 | $0 | Azure for Students: 750 giờ mỗi cỡ B1s, B2pts v2, B2ats v2 |
| Public IP Standard | khoảng $3.6/tháng | chưa kiểm chứng, xem trong Cost Management sau khi apply |
| OS disk Premium SSD 64 GB (P6) | $0 nếu nằm trong mức miễn phí | chưa kiểm chứng; nếu bị tính tiền thì đổi `os_disk_type = "Standard_LRS"` (tạo lại VM) |
| Budget, NSG, VNet | $0 | — |

## Kế hoạch commit

Mỗi bước: `terraform fmt -check` và `terraform validate` (không cần đăng nhập Azure); chạy thêm `ruff` và
`pytest` vì CI chạy chúng. Kiên chạy `plan`/`apply` thật ở các bước có ghi "apply".

| # | Commit | Nội dung | Trạng thái |
|---|---|---|---|
| 1 | `docs(design): deployment plan` | file này, link trong `docs/README.md` | xong `ca5b4bc` |
| 2 | `feat(infra): Terraform skeleton for Azure` | `versions.tf`, provider, biến, resource group, `.gitignore` cho state/tfvars, `README.md` (cài công cụ, init/plan/apply, state). Apply: chỉ tạo resource group | xong `d0ef3bc`, `f9f0ed3` |
| 3 | `feat(infra): network and firewall` | VNet, subnet, NSG (80/443 mọi nơi, 22 từ `admin_cidr`), public IP có DNS label. Apply | xong `e5c6336` |
| 4 | `feat(infra): VM with cloud-init` | VM, SSH key, cloud-init: user, swap, `uv`, Caddy, clone repo, systemd unit; output URL và lệnh SSH. Apply, SSH thử | xong `f7a5e92` |
| 5 | `feat(infra): deploy script` | `deploy.sh`: đẩy `.env` và Caddyfile, checkout nhánh, `uv sync`, restart, kiểm tra `/healthz`. Chạy thật: app lên HTTPS có basic auth | xong `8f49f13` |
| 6 | `feat(infra): budget alert` | `budget.tf`: 50%, 100% và dự báo vượt budget ($20), email | xong `b9f9984` |
| 7 | `docs(design): private accounts instead of basic auth` | sửa plan: bỏ basic auth, tắt `khach`, mật khẩu riêng | xong `9a1bacc` |
| 8 | `feat(backend): GUEST_LOGIN turns guest sign-in off` | biến `GUEST_LOGIN` (mặc định `on`), `SignIn` từ chối `khach` khi tắt; test | xong `ffae96f` |
| 9 | `feat(infra): open site with a private demo password` | bỏ `basic_auth` khỏi Caddyfile và `deploy.sh`; `accounts.py`; `deploy.sh` ghi `DEMO_ACCOUNTS_FILE`, `GUEST_LOGIN=off` và kiểm tra `khach`, mật khẩu `demo` bị từ chối. Chạy thật | |
| 10 | `ci: check Terraform format and config` | job `terraform fmt -check` + `init -backend=false` + `validate` trong `ci.yml` | |
| 11 | `docs: deployment` | README gốc (mục "Triển khai"), `architecture.md`, README của infra: cách CI ở công ty chạy plan/apply | |

## Chưa quyết

1. ~~Cỡ máy~~ → **B2ats v2** (2 vCPU, 1 GB, x64). `az vm list-skus` (26/11): B1s `NotAvailableForSubscription` ở
   cả `malaysiawest`, `indonesiacentral`, `eastasia`; B2ats v2 chỉ dùng được ở `eastasia`.
2. ~~Region~~ → **`eastasia`** (Hong Kong). Policy "Allowed resource deployment regions" của subscription (tenant
   `hcmut.edu.vn`) chỉ cho `uaenorth`, `koreacentral`, `malaysiawest`, `eastasia`, `indonesiacentral`; không có
   `southeastasia`.
3. **Chứng chỉ HTTPS cho `*.cloudapp.azure.com`**: Caddy (Let's Encrypt) cấp được không chưa kiểm chứng. Không được thì
   dùng `<IP>.sslip.io`.
4. **Cài `az` CLI** (để `az login` cho Terraform): máy không có Homebrew; dự kiến `uv tool install azure-cli`
   (nặng, khoảng vài trăm MB, chưa đo).
5. **CI chạy apply** (GitHub Actions + OIDC + remote state trong Storage Account): chưa làm trong nhánh này; README
   chỉ giải thích cách hoạt động. Làm thêm nếu Kiên muốn thực hành.
6. **LLM**: Gemini từ chối request từ VM ở Hong Kong; app dùng Azure OpenAI ở `koreacentral`, xem
   [azure-openai.md](azure-openai.md).
7. **Nhánh git trên VM**: mặc định `main`; trước khi được merge thì deploy `feat/deploy` (đã chứa `feat/chat-ui`).
8. ~~Basic auth trước toàn trang~~ → **bỏ** (26/11). Chrome hỏi lại mật khẩu basic auth liên tục: khi cookie của
   Chainlit hết hạn hoặc chưa có, `/user` trả 401 (`{"detail":"Invalid authentication token"}`, không có
   `WWW-Authenticate`), sau đó Chrome gửi request không kèm basic auth, Caddy trả 401 Basic và Chrome hỏi lại (đoán
   từ log Caddy, chưa thấy tài liệu xác nhận). Thay bằng tắt `khach` và mật khẩu riêng. Đổi lại: trang đăng nhập
   công khai, bot dò được (log đã có request `/.env`, `/wp-config.php`); chỉ chặn bằng mật khẩu ≥ 12 ký tự, chưa giới
   hạn số lần thử.
