variable "name" {
  description = "Tiền tố tên mọi resource"
  type        = string
  default     = "co5151"
}

variable "location" {
  description = "Region. Policy của subscription Azure for Students chỉ cho phép một số region; eastasia có B2ats v2"
  type        = string
  default     = "eastasia"
}

variable "tags" {
  description = "Tag gắn vào mọi resource, để lọc chi phí trong Cost Management"
  type        = map(string)
  default = {
    project    = "co5151-g3"
    managed_by = "terraform"
  }
}

variable "admin_cidr" {
  description = "Dải IP được SSH vào VM (cổng 22), thường là IP public hiện tại của máy bạn: \"<ip>/32\""
  type        = string

  validation {
    condition     = can(cidrhost(var.admin_cidr, 0)) && var.admin_cidr != "0.0.0.0/0"
    error_message = "admin_cidr phải là một dải CIDR, ví dụ 203.0.113.7/32, và không được mở cho mọi nơi."
  }
}

variable "dns_label" {
  description = "Nhãn DNS của IP public: <dns_label>.<location>.cloudapp.azure.com (phải chưa ai dùng trong region)"
  type        = string
  default     = "co5151-g3"
}
