import time
import threading
import docker
from prometheus_client import Gauge, start_http_server
import logging

# Configure logging for clarity and debugging.
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

class DockerMetricsMonitor:
    def __init__(self, docker_url="tcp://172.27.36.125:2375"):
        # Connect to the Docker daemon using the provided URL.
        self.client = docker.DockerClient(base_url=docker_url)

        # Define Prometheus Gauges with a "container" label to differentiate containers.
        self.cpu_usage = Gauge("docker_container_cpu_usage_percent",
                               "CPU usage percent for Docker containers",
                               ["container"])
        self.memory_usage = Gauge("docker_container_memory_usage_percent",
                                  "Memory usage percent for Docker containers",
                                  ["container"])
        self.network_sent = Gauge("docker_container_network_sent_bytes",
                                  "Network transmitted bytes per sampling interval",
                                  ["container"])
        self.network_recv = Gauge("docker_container_network_recv_bytes",
                                  "Network received bytes per sampling interval",
                                  ["container"])
        self.disk_read = Gauge("docker_container_disk_read_bytes",
                               "Disk read bytes per sampling interval",
                               ["container"])
        self.disk_write = Gauge("docker_container_disk_write_bytes",
                                "Disk write bytes per sampling interval",
                                ["container"])

    def monitor_container(self, container):
        """
        Monitor a single container for CPU, memory, network, and disk I/O.
        This method continuously collects metrics every 5 seconds.
        """
        container_name = container.name
        logging.info(f"Starting monitoring for container: {container_name}")

        # Initialize previous snapshot variables for delta calculations.
        prev_net_io = None
        prev_blk_io = None

        while True:
            try:
                stats = container.stats(stream=False)
                
                # === CPU Usage Calculation ===
                cpu_current = stats["cpu_stats"]["cpu_usage"]["total_usage"]
                cpu_previous = stats["precpu_stats"]["cpu_usage"]["total_usage"]
                system_current = stats["cpu_stats"]["system_cpu_usage"]
                system_previous = stats["precpu_stats"]["system_cpu_usage"]

                cpu_delta = cpu_current - cpu_previous
                system_delta = system_current - system_previous

                # Calculate percentage usage (handle division by zero)
                if system_delta > 0:
                    num_cpus = len(stats["cpu_stats"]["cpu_usage"].get("percpu_usage", []))
                    cpu_percent = (cpu_delta / system_delta) * num_cpus * 100.0
                else:
                    cpu_percent = 0
                self.cpu_usage.labels(container=container_name).set(cpu_percent)

                # === Memory Usage Calculation ===
                mem_usage = stats["memory_stats"].get("usage", 0)
                mem_limit = stats["memory_stats"].get("limit", 1)  # avoid division by zero
                mem_percent = (mem_usage / mem_limit) * 100.0
                self.memory_usage.labels(container=container_name).set(mem_percent)

                # === Network I/O Calculation ===
                net_stats = stats.get("networks", {})
                total_tx = sum(interface.get("tx_bytes", 0) for interface in net_stats.values())
                total_rx = sum(interface.get("rx_bytes", 0) for interface in net_stats.values())
                if prev_net_io is not None:
                    # Delta calculation for the sampling period
                    sent_delta = total_tx - prev_net_io["tx"]
                    recv_delta = total_rx - prev_net_io["rx"]
                    self.network_sent.labels(container=container_name).set(sent_delta)
                    self.network_recv.labels(container=container_name).set(recv_delta)
                prev_net_io = {"tx": total_tx, "rx": total_rx}

                # === Disk I/O Calculation ===
                blk_stats = stats.get("blkio_stats", {}).get("io_service_bytes_recursive", [])
                read_bytes = 0
                write_bytes = 0
                for entry in blk_stats:
                    op = entry.get("op", "").lower()
                    value = entry.get("value", 0)
                    if op == "read":
                        read_bytes += value
                    elif op == "write":
                        write_bytes += value

                if prev_blk_io is not None:
                    read_delta = read_bytes - prev_blk_io["read"]
                    write_delta = write_bytes - prev_blk_io["write"]
                    self.disk_read.labels(container=container_name).set(read_delta)
                    self.disk_write.labels(container=container_name).set(write_delta)
                prev_blk_io = {"read": read_bytes, "write": write_bytes}

            except Exception as e:
                logging.error(f"Error monitoring container {container_name}: {e}")

            # Sample every 5 seconds (adjust as needed)
            time.sleep(5)

    def monitor_all_containers(self):
        """
        Start monitoring threads for all currently running containers.
        """
        containers = self.client.containers.list()
        for container in containers:
            threading.Thread(target=self.monitor_container, args=(container,), daemon=True).start()

    def auto_detect_new_containers(self):
        """
        Continuously checks for new containers that have started and begins monitoring them.
        """
        monitored_ids = {c.id for c in self.client.containers.list()}
        while True:
            current_containers = self.client.containers.list()
            for container in current_containers:
                if container.id not in monitored_ids:
                    logging.info(f"New container detected: {container.name}")
                    threading.Thread(target=self.monitor_container, args=(container,), daemon=True).start()
                    monitored_ids.add(container.id)
            time.sleep(10)  # Check for new containers every 10 seconds

def main():
    # Start Prometheus metrics HTTP server on port 8001.
    start_http_server(8001)
    logging.info("Prometheus metrics server started on port 8001.")

    # Initialize the Docker metrics monitor with your Docker daemon URL.
    docker_monitor = DockerMetricsMonitor(docker_url="tcp://172.27.36.125:2375")
    
    # Begin monitoring all running containers.
    docker_monitor.monitor_all_containers()

    # Start a background thread to auto-detect and monitor new containers.
    threading.Thread(target=docker_monitor.auto_detect_new_containers, daemon=True).start()

    # Keep the application running indefinitely.
    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()
