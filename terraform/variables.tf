variable "region" {
  description = "DigitalOcean region slug. Pick one near you: nyc3, sfo3, lon1, fra1, sgp1."
  type        = string
  default     = "nyc3"
}

variable "droplet_size" {
  description = <<-EOT
    Droplet size slug. Nothing is compiled on the box -- the image is built in
    CI -- so this only has to run one uvicorn worker plus the card index.
    s-1vcpu-2gb (~$12/mo) leaves headroom; s-1vcpu-1gb (~$6/mo) also works.
  EOT
  type        = string
  default     = "s-1vcpu-2gb"
}

variable "droplet_image" {
  description = "Base image. Ubuntu LTS, since cloud-init installs Docker from Docker's own apt repo."
  type        = string
  default     = "ubuntu-24-04-x64"
}

variable "name" {
  description = "Name prefix for the droplet, firewall and SSH key resources."
  type        = string
  default     = "automtg"
}

variable "admin_ssh_public_key" {
  description = <<-EOT
    Your own SSH public key, for administering the box by hand.
    Typically file("~/.ssh/id_ed25519.pub").
  EOT
  type        = string
}

variable "ci_ssh_public_key" {
  description = <<-EOT
    Public half of the dedicated CI deploy key. The private half becomes the
    DROPLET_SSH_KEY Actions secret. Kept separate from the admin key so it can
    be rotated -- or revoked after a leak -- without locking you out.
  EOT
  type        = string
}

variable "ssh_allowed_cidrs" {
  description = <<-EOT
    Who may reach port 22. Defaults to the whole internet because GitHub-hosted
    runners have no stable egress range to allow-list. Narrow it if you ever
    move the deploy job to a self-hosted runner with a fixed address.
  EOT
  type        = list(string)
  default     = ["0.0.0.0/0", "::/0"]
}
