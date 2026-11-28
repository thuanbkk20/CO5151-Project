# Nhiều model trên một resource Azure AI Foundry (một endpoint, một key) để nhóm thử app với từng model
# (docs/design/foundry-models.md). Resource loại AIServices deploy được cả model không phải của OpenAI.

resource "azurerm_cognitive_account" "foundry" {
  name                  = "${var.name}-foundry"
  location              = var.openai_location
  resource_group_name   = azurerm_resource_group.app.name
  kind                  = "AIServices"
  sku_name              = "S0"
  custom_subdomain_name = var.foundry_subdomain
  tags                  = var.tags
}

# Tên deployment là tên model: backend gửi tên này làm `model`. Danh sách model của provider `foundry` trong
# backend (PROVIDERS, infrastructure/llm.py) phải khớp các tên này.
resource "azurerm_cognitive_deployment" "foundry" {
  for_each             = var.foundry_models
  name                 = each.key
  cognitive_account_id = azurerm_cognitive_account.foundry.id

  model {
    format  = each.value.format
    name    = each.key
    version = each.value.version
  }

  sku {
    name     = "GlobalStandard"
    capacity = each.value.capacity
  }
}
