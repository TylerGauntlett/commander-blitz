output "reserved_ip" {
  description = "Stable public address. This is the DROPLET_HOST Actions secret and the app's URL."
  value       = digitalocean_reserved_ip.web.ip_address
}

output "droplet_ipv4" {
  description = "The droplet's own address. Useful for SSH before the reserved IP is assigned."
  value       = digitalocean_droplet.web.ipv4_address
}

output "app_url" {
  description = "Where the app answers once the first deploy has run."
  value       = "http://${digitalocean_reserved_ip.web.ip_address}"
}

output "admin_ssh" {
  description = "Copy-paste command for administering the box."
  value       = "ssh admin@${digitalocean_reserved_ip.web.ip_address}"
}
