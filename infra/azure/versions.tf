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
}
