# Mọi resource của app nằm trong một resource group: xóa group là xóa sạch.
resource "azurerm_resource_group" "app" {
  name     = "${var.name}-rg"
  location = var.location
  tags     = var.tags
}
