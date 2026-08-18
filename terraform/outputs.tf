output "reserved_ip" {
  description = "Stable public address. This is the DROPLET_HOST Actions secret and what the apex A record points at."
  value       = digitalocean_reserved_ip.web.ip_address
}

output "droplet_ipv4" {
  description = "The droplet's own address. Useful for SSH before the reserved IP is assigned."
  value       = digitalocean_droplet.web.ipv4_address
}

# The apex A record for this domain points at reserved_ip. It is managed at the
# registrar, not here -- the zone is not hosted at DigitalOcean -- so changing
# the reserved IP means editing that record by hand.
output "app_url" {
  description = "Where the app answers once the first deploy has run. Caddy serves this name only; the bare IP 404s."
  value       = "https://commanderblitz.com"
}

output "admin_ssh" {
  description = "Copy-paste command for administering the box."
  value       = "ssh admin@${digitalocean_reserved_ip.web.ip_address}"
}
