from prometheus_client import start_http_server, Gauge
import random, time

# Define a gauge metric
cpu_utilization = Gauge('aws_ec2_cpu_utilization', 'Simulated CPU utilization for EC2')

# Start the server
start_http_server(8000)
while True:
    # Update metric with random value
    cpu_utilization.set(random.uniform(10, 90))
    time.sleep(5)

    # pip install prometheus-client
