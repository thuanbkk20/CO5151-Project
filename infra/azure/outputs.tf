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
