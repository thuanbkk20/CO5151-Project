# LLM của app: Azure OpenAI ở region khác VM. Gemini từ chối request từ VM ở Hong Kong, còn eastasia không có quota
# Azure OpenAI cho Azure for Students (docs/design/azure-openai.md). Tài khoản không tốn tiền; token trừ vào credit.

resource "azurerm_cognitive_account" "openai" {
  name                  = "${var.name}-openai"
  location              = var.openai_location
  resource_group_name   = azurerm_resource_group.app.name
  kind                  = "OpenAI"
  sku_name              = "S0"
  custom_subdomain_name = var.openai_subdomain
  tags                  = var.tags
}

# Tên deployment là tên model, nên model mặc định của provider `azure` trong backend gọi đúng deployment này.
resource "azurerm_cognitive_deployment" "chat" {
  name                 = var.openai_model
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = var.openai_model
    version = var.openai_model_version
  }

  sku {
    name     = "GlobalStandard"
    capacity = var.openai_capacity
  }
}
