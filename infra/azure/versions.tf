terraform {
  required_version = ">= 1.9"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 5.15"
    }
  }
}

# Subscription lấy từ biến môi trường ARM_SUBSCRIPTION_ID (xem README), đăng nhập bằng phiên `az login`.
provider "azurerm" {
  features {}
}
