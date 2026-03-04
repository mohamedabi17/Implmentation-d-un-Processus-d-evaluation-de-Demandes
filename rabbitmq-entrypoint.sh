#!/bin/bash
set -e

# Create .erlang.cookie with proper permissions
if [ ! -f /var/lib/rabbitmq/.erlang.cookie ]; then
    echo "RABBITMQCOOKIE" > /var/lib/rabbitmq/.erlang.cookie
fi

chmod 600 /var/lib/rabbitmq/.erlang.cookie
chown rabbitmq:rabbitmq /var/lib/rabbitmq/.erlang.cookie

# Start RabbitMQ
exec docker-entrypoint.sh rabbitmq-server
