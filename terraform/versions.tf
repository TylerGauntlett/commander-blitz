terraform {
  required_version = ">= 1.6"

  required_providers {
    digitalocean = {
      source  = "digitalocean/digitalocean"
      version = "~> 2.43"
    }
  }
}

# The token is read from the DIGITALOCEAN_TOKEN environment variable rather than
# being declared as a variable. A variable would end up in state, in a .tfvars
# file, or in shell history; the environment reaches the provider and stops.
provider "digitalocean" {}
