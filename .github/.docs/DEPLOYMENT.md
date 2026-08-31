# VPS deployment

This deployment runs two containers:

- `suanpan`: FastAPI on `127.0.0.1:8000` on the VPS
- `valkey`: internal-only Valkey with append-only persistence in the
  `suanpan_valkey_data` Docker volume

Caddy runs on the VPS host, terminates HTTPS, and proxies the public hostname to
Suanpan. Valkey has no published host port and must not be opened in the VPS
firewall.

The commands below assume an Ubuntu or Debian VPS. For another distribution,
use the equivalent Docker Engine, Compose plugin, Caddy, user, and firewall
commands.

## 1. DNS

Create an `A` record:

| Field | Value |
|---|---|
| Type | `A` |
| Name | `suanpan` |
| Value | your VPS public IPv4 address |
| Proxy/CDN | DNS-only initially, if your DNS provider offers a proxy |

Wait until `suanpan.example.com` resolves to the VPS. Replace that example
hostname everywhere below with the real hostname. Add an `AAAA` record only if
the VPS has working public IPv6.

## 2. Install Docker on the VPS

Install Docker Engine from Docker's official repository, including these
packages:

```bash
sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker run --rm hello-world
docker compose version
```

Docker documents the repository setup steps for
[Ubuntu](https://docs.docker.com/engine/install/ubuntu/) and
[Debian](https://docs.docker.com/engine/install/debian/). Do not use the legacy
`docker-compose` Python package; this project uses `docker compose` v2.

Create a dedicated deployment user and the deployment directory:

```bash
sudo adduser --disabled-password --gecos "" deploy
sudo usermod -aG docker deploy
sudo install -d -o deploy -g deploy /opt/suanpan /opt/suanpan/releases
```

Adding a user to the `docker` group effectively grants root-level control of
the VPS. Keep this account key-only and dedicated to deployment. Log out and
back in before testing `docker ps` as `deploy`.

## 3. Install and configure Caddy

Use Caddy's official Debian/Ubuntu packages:

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy
```

Edit `/etc/caddy/Caddyfile` to contain:

```caddyfile
suanpan.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

Then validate and reload it:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
sudo systemctl status caddy --no-pager
```

Caddy will obtain and renew the TLS certificate automatically once DNS points
at this server and inbound ports 80 and 443 are reachable.

If UFW is enabled, allow SSH before enabling or changing the firewall:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

Do not allow public ports 6379 or 8000. Port 8000 is deliberately bound to VPS
loopback only, and port 6379 is not published at all.

## 4. Create the deployment SSH key

On a trusted computer, generate a key used only by this GitHub repository:

```bash
ssh-keygen -t ed25519 -C "github-actions-suanpan" -f ./suanpan-deploy
```

Use an empty passphrase for this non-interactive, repository-specific key. Do
not reuse a personal SSH key.

Put the single line from `suanpan-deploy.pub` in
`/home/deploy/.ssh/authorized_keys` on the VPS. On the VPS, enforce the normal
SSH permissions:

```bash
sudo install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
sudo touch /home/deploy/.ssh/authorized_keys
sudo chown deploy:deploy /home/deploy/.ssh/authorized_keys
sudo chmod 600 /home/deploy/.ssh/authorized_keys
```

Test the key from the trusted computer before adding it to GitHub:

```bash
ssh -i ./suanpan-deploy deploy@YOUR_VPS_IP 'docker ps'
```

Capture the VPS host key using the exact hostname or IP that GitHub Actions will
connect to:

```bash
ssh-keyscan -H YOUR_VPS_IP > suanpan-known-hosts
ssh-keygen -lf suanpan-known-hosts
```

If SSH uses a custom port, add `-p YOUR_PORT` to `ssh-keyscan` and use the same
port for the connection test.

Compare that fingerprint with the server's host-key fingerprint from the VPS
provider console before trusting it. For the common ED25519 host key, the server
command is:

```bash
sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

## 5. Configure GitHub Actions

In the GitHub repository, open **Settings → Secrets and variables → Actions**.
Create these repository secrets:

| Secret | Value |
|---|---|
| `VPS_HOST` | The exact IP/hostname used with `ssh-keyscan` |
| `VPS_USER` | `deploy` |
| `VPS_SSH_PRIVATE_KEY` | Entire contents of the private `suanpan-deploy` file |
| `VPS_SSH_KNOWN_HOSTS` | Entire contents of `suanpan-known-hosts` |

If SSH does not listen on port 22, create an Actions repository **variable**
named `VPS_SSH_PORT`. Otherwise the workflow defaults to 22.

The workflow in `.github/workflows/ci-deploy.yml` does the following:

1. On every pull request and push, install pinned dependencies, run all tests,
   validate Compose, and build the production image.
2. After tests pass on a push to `main` (or a manual workflow dispatch), upload
   that commit as a release over SSH.
3. Build and start the two containers, wait for both health checks, update
   `/opt/suanpan/current`, and call the local health endpoint.

Push these files to `main` after the VPS, SSH key, and GitHub secrets are ready.
The first successful run performs the initial deployment.

## 6. Verify and operate

Verify from your computer:

```bash
curl https://suanpan.example.com/healthcheck
curl https://suanpan.example.com/
```

Useful commands on the VPS:

```bash
cd /opt/suanpan/current
docker compose ps
docker compose logs --tail=100 suanpan
docker compose logs --tail=100 valkey
docker compose restart suanpan
```

The Valkey named volume survives container replacement and `docker compose
down`. Do not run `docker compose down --volumes` unless you intend to delete all
counters.

Back up Valkey regularly using your VPS backup system. For a simple manual
snapshot:

```bash
cd /opt/suanpan/current
docker compose exec -T valkey valkey-cli BGSAVE
mkdir -p /opt/suanpan/backups
docker compose cp valkey:/data/dump.rdb "/opt/suanpan/backups/dump-$(date +%F-%H%M%S).rdb"
```

Copy those backups off the VPS and test restoration before relying on them.
Old application releases remain under `/opt/suanpan/releases`; they are small
and may be removed manually after you have retained the releases you want for
rollback. Never remove `suanpan_valkey_data` as part of release cleanup.
