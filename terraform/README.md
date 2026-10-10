# terraform/

Provisions the hosting for the site: one DigitalOcean droplet, a reserved IP, a
firewall, and two SSH keys. Run by hand, never by CI. The walkthrough, including
the GitHub secrets the deploy job needs afterwards, is in
[../docs/deployment.md](../docs/deployment.md); this is the short version.

```bash
# DIGITALOCEAN_TOKEN in the environment (see ../.env.example), then:
cd terraform
cp terraform.tfvars.example terraform.tfvars   # fill in the two public keys
terraform init
terraform apply
terraform output -raw reserved_ip
```

State is local and gitignored (`*.tfstate`, `*.tfvars`, saved plans), so the copy
of this directory that ran `apply` is the only record of what exists: back it up.
`terraform destroy` tears the whole thing down, including the Docker volume that
holds imported decks.

You do not need any of this to run the game. `docker compose up` with the
[`docker-compose.yml`](../docker-compose.yml) at the root runs the same image
anywhere, and `docs/deployment.md` has the self-hosting notes.
