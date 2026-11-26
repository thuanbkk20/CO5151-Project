data "azurerm_subscription" "current" {}

# Budget chỉ GỬI EMAIL cảnh báo, không tự dừng resource. Subscription Azure for Students tự bị tắt khi hết credit
# (không trừ tiền thẻ), nên budget là báo sớm để kịp `terraform destroy` trước khi credit cạn.
resource "azurerm_consumption_budget_subscription" "app" {
  name            = "${var.name}-budget"
  subscription_id = data.azurerm_subscription.current.id
  amount          = var.budget_amount
  time_grain      = "Monthly"

  # Ngày bắt đầu phải là ngày 1 của tháng; lấy tháng hiện tại lúc tạo rồi giữ nguyên (không đổi mỗi lần apply).
  time_period {
    start_date = formatdate("YYYY-MM-01'T'00:00:00Z", timestamp())
  }

  lifecycle {
    ignore_changes = [time_period]
  }

  # Đã tiêu 50% budget trong tháng.
  notification {
    enabled        = true
    operator       = "GreaterThanOrEqualTo"
    threshold      = 50
    threshold_type = "Actual"
    contact_emails = var.alert_emails
  }

  # Đã tiêu hết budget trong tháng.
  notification {
    enabled        = true
    operator       = "GreaterThanOrEqualTo"
    threshold      = 100
    threshold_type = "Actual"
    contact_emails = var.alert_emails
  }

  # Dự báo cuối tháng sẽ vượt budget.
  notification {
    enabled        = true
    operator       = "GreaterThan"
    threshold      = 100
    threshold_type = "Forecasted"
    contact_emails = var.alert_emails
  }
}
