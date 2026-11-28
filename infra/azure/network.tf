resource "azurerm_virtual_network" "app" {
  name                = "${var.name}-vnet"
  location            = azurerm_resource_group.app.location
  resource_group_name = azurerm_resource_group.app.name
  address_space       = ["10.10.0.0/16"]
  tags                = var.tags
}

resource "azurerm_subnet" "app" {
  name                 = "${var.name}-subnet"
  resource_group_name  = azurerm_resource_group.app.name
  virtual_network_name = azurerm_virtual_network.app.name
  address_prefixes     = ["10.10.1.0/24"]
}

# Firewall. Azure mặc định chặn mọi kết nối vào từ Internet (luật DenyAllInBound, priority 65500); chỉ mở:
# 443 cho trang web (Caddy), 80 để Caddy xin chứng chỉ HTTPS và chuyển sang 443, 22 chỉ từ admin_cidr.
# Các service của app nghe 127.0.0.1 nên dù luật có sai cũng không lộ ra ngoài.
resource "azurerm_network_security_group" "app" {
  name                = "${var.name}-nsg"
  location            = azurerm_resource_group.app.location
  resource_group_name = azurerm_resource_group.app.name
  tags                = var.tags

  security_rule {
    name                       = "allow-https"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_address_prefix      = "Internet"
    source_port_range          = "*"
    destination_address_prefix = "*"
    destination_port_range     = "443"
  }

  security_rule {
    name                       = "allow-http"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_address_prefix      = "Internet"
    source_port_range          = "*"
    destination_address_prefix = "*"
    destination_port_range     = "80"
  }

  security_rule {
    name                       = "allow-ssh-admin"
    priority                   = 120
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_address_prefix      = var.admin_cidr
    source_port_range          = "*"
    destination_address_prefix = "*"
    destination_port_range     = "22"
  }
}

resource "azurerm_subnet_network_security_group_association" "app" {
  subnet_id                 = azurerm_subnet.app.id
  network_security_group_id = azurerm_network_security_group.app.id
}

# IP public cố định (Standard SKU chỉ có Static). Tính phí theo giờ khi resource còn tồn tại, kể cả lúc VM tắt;
# không dùng nữa thì `terraform destroy`.
resource "azurerm_public_ip" "app" {
  name                = "${var.name}-ip"
  location            = azurerm_resource_group.app.location
  resource_group_name = azurerm_resource_group.app.name
  sku                 = "Standard"
  allocation_method   = "Static"
  domain_name_label   = var.dns_label
  tags                = var.tags
}
