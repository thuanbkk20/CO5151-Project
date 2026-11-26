output "resource_group" {
  description = "Tên resource group chứa mọi resource của app"
  value       = azurerm_resource_group.app.name
}

output "public_ip" {
  description = "IP public của VM"
  value       = azurerm_public_ip.app.ip_address
}

output "fqdn" {
  description = "Tên miền của IP public, dùng cho URL của app"
  value       = azurerm_public_ip.app.fqdn
}

output "app_url" {
  description = "URL của app (có sau khi chạy deploy.sh)"
  value       = "https://${azurerm_public_ip.app.fqdn}"
}

output "ssh_command" {
  description = "Lệnh SSH vào VM"
  value       = "ssh -i ${trimsuffix(var.ssh_public_key_path, ".pub")} ${var.admin_username}@${azurerm_public_ip.app.fqdn}"
}

output "openai_base_url" {
  description = "AZURE_OPENAI_BASE_URL cho .env (key lấy bằng az, xem README)"
  value       = "${azurerm_cognitive_account.openai.endpoint}openai/v1/"
}
