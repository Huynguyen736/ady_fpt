Diabetes API - Deploy with Docker on Proxmox

Overview

This project is a FastAPI service for diabetes prediction. The deployment below runs:
- API container on port 8000
- PostgreSQL container on internal port 5432 (host port configurable with `DB_HOST_PORT`)

The setup is designed for a Proxmox VM or LXC where Docker is installed.

1. Prepare Proxmox Host

Recommended: create an Ubuntu VM (or Docker-enabled LXC) in Proxmox.

Minimum recommendation:
- 2 vCPU
- 2 GB RAM
- 15 GB disk

2. Install Docker on Ubuntu

Run on your Proxmox guest:

sudo apt update
sudo apt install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER

Log out and log in again after adding your user to docker group.

3. Copy Project to Server

Option A: git clone on server.
Option B: upload folder via SCP/WinSCP.

Then go to project folder:

cd production-ady

4. Configure Environment

Copy the template and set a strong DB password:

cp .env.example .env
nano .env

Example values:

DB_HOST=db
DB_NAME=mydb
DB_USER=admin
DB_PASSWORD=your_strong_password_here
DB_PORT=5432
DB_HOST_PORT=5432

5. Build and Run

docker compose up -d --build

Check status:

docker compose ps
docker compose logs -f api

6. Verify API

Health check:

curl http://SERVER_IP:8000/

Test prediction:

curl -X POST http://SERVER_IP:8000/predict \
	-H "Content-Type: application/json" \
	-d '{
		"Pregnancies": 2,
		"Glucose": 120,
		"BloodPressure": 70,
		"BMI": 28.5,
		"DiabetesPedigreeFunction": 0.45,
		"Age": 33
	}'

7. Auto-start on reboot

Containers already use restart policy unless-stopped.
Ensure Docker service is enabled:

sudo systemctl enable docker

8. Update deployment after code changes

git pull
docker compose up -d --build

9. Useful commands

Stop stack:
docker compose down

Stop and remove DB volume (danger: data loss):
docker compose down -v

See API logs:
docker compose logs -f api

Files added for deployment

- docker-compose.yml
- .env.example
- docker/init.sql

