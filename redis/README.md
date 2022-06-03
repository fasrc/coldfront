# Redis Container Configuration

This directory is meant to be used in the generation of a redis docker 
container that connects with the coldfront docker container.

The docker container can be created ad-hoc with the following command:

`docker run --network coldfront --name coldfront-redis -v /srv/coldfront/coldfront/redis/:/usr/local/etc/redis redis:latest /usr/local/etc/redis/redis.conf`

`redis.conf` has its `bind` setting commented out and `protected-mode` set to `no`.
These settings enable the created container to connect and accept connections.

