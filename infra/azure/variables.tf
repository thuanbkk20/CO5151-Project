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

variable "vm_size" {
  description = "Cỡ VM. Standard_B2ats_v2 (2 vCPU, 1 GB) nằm trong 750 giờ miễn phí của Azure for Students"
  type        = string
  default     = "Standard_B2ats_v2"
}

variable "admin_username" {
  description = "User SSH vào VM (có sudo)"
  type        = string
  default     = "azureuser"
}

variable "ssh_public_key_path" {
  description = "Đường dẫn SSH public key được đăng nhập VM (đăng nhập bằng mật khẩu bị tắt)"
  type        = string
  default     = "~/.ssh/co5151_azure.pub"
}

variable "os_disk_type" {
  description = "Loại OS disk: Premium_LRS 64 GB là cỡ P6 (theo ưu đãi miễn phí, chưa kiểm chứng), Standard_LRS rẻ nhất"
  type        = string
  default     = "Premium_LRS"
}

variable "os_disk_size_gb" {
  description = "Dung lượng OS disk (GB)"
  type        = number
  default     = 64
}

variable "repo_url" {
  description = "Repo git cloud-init clone về VM (repo public, không cần key)"
  type        = string
  default     = "https://github.com/thuanbkk20/CO5151-Project.git"
}

variable "uv_version" {
  description = "Phiên bản uv cài trên VM"
  type        = string
  default     = "0.13.7"
}

variable "budget_amount" {
  description = "Budget mỗi tháng (USD, trừ vào credit) để gửi email cảnh báo ở 50%, 100% và khi dự báo vượt"
  type        = number
  default     = 20
}

variable "alert_emails" {
  description = "Email nhận cảnh báo budget; đặt trong terraform.tfvars, không commit"
  type        = list(string)

  validation {
    condition     = length(var.alert_emails) > 0
    error_message = "Cần ít nhất một email nhận cảnh báo budget."
  }
}
