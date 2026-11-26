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
