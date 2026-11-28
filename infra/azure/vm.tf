resource "azurerm_network_interface" "app" {
  name                = "${var.name}-nic"
  location            = azurerm_resource_group.app.location
  resource_group_name = azurerm_resource_group.app.name
  tags                = var.tags

  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.app.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.app.id
  }
}

resource "azurerm_linux_virtual_machine" "app" {
  name                  = "${var.name}-vm"
  location              = azurerm_resource_group.app.location
  resource_group_name   = azurerm_resource_group.app.name
  size                  = var.vm_size
  network_interface_ids = [azurerm_network_interface.app.id]
  tags                  = var.tags

  admin_username                  = var.admin_username
  disable_password_authentication = true

  admin_ssh_key {
    username   = var.admin_username
    public_key = file(pathexpand(var.ssh_public_key_path))
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = var.os_disk_type
    disk_size_gb         = var.os_disk_size_gb
  }

  # Ubuntu 24.04 LTS bản minimal (x64, gen2): ít package, ít RAM hơn bản server.
  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "minimal"
    version   = "latest"
  }

  # cloud-init chạy một lần lúc tạo máy. Đổi nội dung này thì Terraform phải TẠO LẠI VM (mất dữ liệu trên đĩa,
  # gồm lịch sử chat); cập nhật app dùng deploy.sh, không sửa ở đây.
  custom_data = base64encode(templatefile("${path.module}/cloud-init.yaml", {
    repo_url   = var.repo_url
    uv_version = var.uv_version
  }))
}
