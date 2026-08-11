# terraform/

Provisions the deployment target: one droplet, a reserved IP, a firewall, and
two SSH keys. Run by hand, never by CI. The full walkthrough is in
[../docs/deployment.md](../docs/deployment.md); this is the short version.

```powershell
# From the repo root, with .env filled in:
Get-Content .env | Where-Object { $_ -match '^\s*[^#].*=' } | ForEach-Object {
  $k, $v = $_ -split '=', 2; Set-Item "env:$($k.Trim())" $v.Trim()
}

cd terraform
Copy-Item terraform.tfvars.example terraform.tfvars   # then fill it in
terraform init
terraform apply
terraform output -raw reserved_ip
```

State is local and gitignored, so this directory on this machine is the only
record of what exists. `terraform destroy` tears the whole thing down; the two
Docker volumes holding fetched art and imported decks go with it.
