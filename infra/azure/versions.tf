terraform {
  required_version = ">= 1.9"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 5.15"
    }
  }
}

# Đăng nhập bằng phiên `az login`; subscription là subscription mặc định của az, hoặc ARM_SUBSCRIPTION_ID nếu đặt.
provider "azurerm" {
  features {}

  # Subscription mới chưa đăng ký namespace nào; chỉ đăng ký đúng những gì app dùng (provider v5 không tự đăng ký).
  resource_provider_registrations = "none"
  resource_providers_to_register  = ["Microsoft.Compute", "Microsoft.Network"]
}
