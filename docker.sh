cd ~/autolab
docker compose down

git pull
docker compose up --build -d

docker ps

docker compose logs -f

