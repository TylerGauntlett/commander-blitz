# The whole deployment target: one droplet, a stable address for it, and a
# firewall. CI never touches any of this -- it only ever SSHes in and runs
# `docker compose up -d`. Provisioning is a thing a human does, deliberately.

resource "digitalocean_ssh_key" "admin" {
  name       = "${var.name}-admin"
  public_key = var.admin_ssh_public_key
}

resource "digitalocean_ssh_key" "ci" {
  name       = "${var.name}-ci"
  public_key = var.ci_ssh_public_key
}

resource "digitalocean_droplet" "web" {
  name   = var.name
  image  = var.droplet_image
  region = var.region
  size   = var.droplet_size

  # Registering both keys with DO as well as authorizing them via cloud-init:
  # the DO-side registration is what lets you use the console recovery flow if
  # the cloud-init user setup ever fails.
  ssh_keys = [
    digitalocean_ssh_key.admin.fingerprint,
    digitalocean_ssh_key.ci.fingerprint,
  ]

  user_data = templatefile("${path.module}/cloud-init.yaml.tftpl", {
    admin_ssh_public_key = trimspace(var.admin_ssh_public_key)
    ci_ssh_public_key    = trimspace(var.ci_ssh_public_key)
  })

  monitoring = true
  ipv6       = true

  # The droplet is disposable -- all durable state lives in the two Docker
  # volumes -- but replacing it silently on an unrelated edit is still a
  # surprise worth refusing. Change these deliberately and `taint` instead.
  lifecycle {
    ignore_changes = [user_data, image]
  }
}

# A reserved IP so rebuilding the droplet does not invalidate the DROPLET_HOST
# secret and every bookmark pointing at the app.
resource "digitalocean_reserved_ip" "web" {
  region = var.region
}

resource "digitalocean_reserved_ip_assignment" "web" {
  ip_address = digitalocean_reserved_ip.web.ip_address
  droplet_id = digitalocean_droplet.web.id
}

resource "digitalocean_firewall" "web" {
  name        = "${var.name}-fw"
  droplet_ids = [digitalocean_droplet.web.id]

  inbound_rule {
    protocol         = "tcp"
    port_range       = "22"
    source_addresses = var.ssh_allowed_cidrs
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "80"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  inbound_rule {
    protocol         = "icmp"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  # Unrestricted egress: the box pulls images from ghcr.io, packages from apt,
  # and card art from cards.scryfall.io on demand.
  outbound_rule {
    protocol              = "tcp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "udp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "icmp"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }
}
