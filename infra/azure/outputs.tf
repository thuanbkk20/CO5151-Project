output "resource_group" {
  description = "Tên resource group chứa mọi resource của app"
  value       = azurerm_resource_group.app.name
}
