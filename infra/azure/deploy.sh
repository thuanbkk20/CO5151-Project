#!/usr/bin/env bash
# Cập nhật app trên VM Azure: đẩy .env và cấu hình Caddy, checkout mã nguồn, cài thư viện, khởi động lại, kiểm tra.
# Chạy từ máy của bạn sau khi đã `terraform apply` trong infra/azure:
#
#   infra/azure/deploy.sh [git-ref]      # git-ref: nhánh, tag hoặc commit trên origin; mặc định main
#
# Cấu hình lấy từ .env.production ở gốc repo (gitignore). Secret không đi qua Terraform (state lưu dạng rõ) mà
# được đẩy thẳng qua SSH. Bản deploy tắt tài khoản khach; mọi tài khoản demo dùng mật khẩu DEPLOY_DEMO_PASSWORD.
# Biến tùy chọn: DEPLOY_ENV_FILE, DEPLOY_SSH_KEY, DEPLOY_SSH_USER, DEPLOY_HOST.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TF_DIR="$ROOT/infra/azure"
REF="${1:-main}"
ENV_FILE="${DEPLOY_ENV_FILE:-$ROOT/.env.production}"
SSH_KEY="${DEPLOY_SSH_KEY:-$HOME/.ssh/co5151_azure}"
SSH_USER="${DEPLOY_SSH_USER:-azureuser}"
HOST="${DEPLOY_HOST:-$(terraform -chdir="$TF_DIR" output -raw fqdn)}"
APP=/opt/co5151/app
ACCOUNTS=/opt/co5151/accounts.json

die() {
  echo "deploy: $*" >&2
  exit 1
}
get() { grep -E "^$1=" "$ENV_FILE" | tail -n 1 | cut -d= -f2- || true; }
on_vm() { ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new "$SSH_USER@$HOST" "$@"; }

# 1. Kiểm tra cấu hình trước khi đụng vào server.
[[ -f "$ENV_FILE" ]] || die "không thấy $ENV_FILE (xem infra/azure/README.md)"
for key in BACKEND_TOKEN_SECRET STUDENT_MCP_TOKEN_SECRET CHAINLIT_AUTH_SECRET DEPLOY_DEMO_PASSWORD; do
  value="$(get "$key")"
  [[ -n "$value" && "$value" != change-me* ]] || die "$key trống hoặc còn giá trị mẫu trong $ENV_FILE"
done
password="$(get DEPLOY_DEMO_PASSWORD)"
((${#password} >= 12)) || die "DEPLOY_DEMO_PASSWORD cần ít nhất 12 ký tự"
for key in STUDENT_MCP_HOST REGULATION_MCP_HOST BACKEND_HOST CONSOLE_HOST CHAINLIT_HOST; do
  value="$(get "$key")"
  [[ -z "$value" || "$value" == 127.0.0.1 ]] || die "$key=$value: service phải nghe 127.0.0.1, chỉ Caddy ra Internet"
done

echo "==> $HOST: .env (bỏ các dòng DEPLOY_*; tắt khách, dùng file tài khoản riêng)"
{
  grep -vE '^(DEPLOY_|GUEST_LOGIN=|DEMO_ACCOUNTS_FILE=)' "$ENV_FILE"
  printf 'GUEST_LOGIN=off\nDEMO_ACCOUNTS_FILE=%s\n' "$ACCOUNTS"
} | on_vm "sudo install -m 600 -o co5151 -g co5151 /dev/stdin $APP/.env"

echo "==> Caddy: Caddyfile, tên miền"
on_vm "sudo install -m 644 /dev/stdin /etc/caddy/Caddyfile" <"$TF_DIR/Caddyfile"
printf 'APP_DOMAIN=%s\n' "$HOST" | on_vm "sudo install -m 640 -o root -g caddy /dev/stdin /etc/caddy/caddy.env"
printf '[Service]\nEnvironmentFile=/etc/caddy/caddy.env\n' |
  on_vm "sudo install -D -m 644 /dev/stdin /etc/systemd/system/caddy.service.d/env.conf"

echo "==> Mã nguồn $REF, thư viện"
on_vm bash -s -- "$REF" <<'REMOTE'
set -euo pipefail
REF="$1"
APP=/opt/co5151/app
as_app() { sudo -u co5151 -H "$@"; }

as_app git -C "$APP" fetch --prune --tags origin
if as_app git -C "$APP" rev-parse -q --verify "origin/$REF^{commit}" >/dev/null; then target="origin/$REF"; else target="$REF"; fi
# Mã nguồn trên server không sửa tay: --force bỏ thay đổi ở file được git theo dõi; .env, .venv, .data giữ nguyên.
as_app git -C "$APP" checkout -q --detach --force "$target"
as_app git -C "$APP" log --oneline -1
cd "$APP"
as_app uv sync --locked --all-packages --no-dev --quiet
REMOTE

echo "==> Tài khoản: mật khẩu DEPLOY_DEMO_PASSWORD (lưu hash) vào $ACCOUNTS"
# Mật khẩu đi qua stdin, không nằm trên dòng lệnh; script gửi kèm nên không phụ thuộc ref đang deploy.
get DEPLOY_DEMO_PASSWORD |
  on_vm "sudo -u co5151 -H $APP/.venv/bin/python -c $(printf '%q' "$(cat "$TF_DIR/accounts.py")") $ACCOUNTS"

echo "==> Khởi động lại, kiểm tra"
on_vm bash -s <<'REMOTE'
set -euo pipefail
sudo systemctl daemon-reload
sudo systemctl restart co5151.target
sudo systemctl restart caddy

wait_for() {
  for _ in $(seq 1 60); do
    curl -fsS -o /dev/null "$1" && return 0
    sleep 2
  done
  echo "không lên: $1 (xem: journalctl -u 'co5151-*' -n 50)" >&2
  return 1
}
wait_for http://127.0.0.1:8100/healthz
wait_for http://127.0.0.1:8000/
systemctl is-active co5151-student co5151-regulation co5151-api co5151-web caddy | paste -sd ' ' -
free -h | sed -n 1,3p

# Bản public: khách và mật khẩu demo (công khai trong README) phải bị từ chối.
login() {
  curl -s -o /dev/null -w '%{http_code}' -H 'Content-Type: application/json' \
    -d "{\"username\": \"$1\", \"password\": \"$2\"}" http://127.0.0.1:8100/auth/login
}
for user in khach sv001; do
  status="$(login "$user" demo)"
  [[ "$status" == 401 ]] || { echo "đăng nhập $user/demo phải bị từ chối: mong 401, nhận $status" >&2; exit 1; }
done
echo "khach và mật khẩu demo: bị từ chối"
REMOTE

echo "==> Kiểm tra từ Internet: https://$HOST"
status="$(curl -s -o /dev/null -w '%{http_code}' --retry 10 --retry-delay 3 --retry-all-errors "https://$HOST/")"
[[ "$status" == 200 ]] || die "https://$HOST/: mong 200, nhận $status"
echo "Xong: https://$HOST"
