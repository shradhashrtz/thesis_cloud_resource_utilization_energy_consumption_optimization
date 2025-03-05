from prometheus_client import Gauge, CollectorRegistry, generate_latest
import time
import threading
import docker
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class DockerMetricsMonitor:
    def __init__(self, docker_url=os.getenv('DOCKER_URL', 'tcp://localhost:2375'), registry=None):
        logging.info("Initializing DockerMetricsMonitor...")

        # Connect to Docker daemon
        try:
            self.client = docker.DockerClient(base_url=docker_url)
            logging.info("Connected to Docker daemon at %s", docker_url)
        except Exception as e:
            logging.error("Failed to connect to Docker daemon: %s", e)
            raise

        # Use the provided registry or create a new one
        self.registry = registry or CollectorRegistry()

        # Define Prometheus Gauges with a "container" label to differentiate containers
        self.cpu_usage = Gauge("docker_container_cpu_usage_percent",
                               "CPU usage percent for Docker containers",
                               ["container"], registry=self.registry)
        self.memory_usage = Gauge("docker_container_memory_usage_percent",
                                  "Memory usage percent for Docker containers",
                                  ["container"], registry=self.registry)
        self.network_sent = Gauge("docker_container_network_sent_bytes",
                                  "Network transmitted bytes per sampling interval",
                                  ["container"], registry=self.registry)
        self.network_recv = Gauge("docker_container_network_recv_bytes",
                                  "Network received bytes per sampling interval",
                                  ["container"], registry=self.registry)
        self.disk_read = Gauge("docker_container_disk_read_bytes",
                               "Disk read bytes per sampling interval",
                               ["container"], registry=self.registry)
        self.disk_write = Gauge("docker_container_disk_write_bytes",
                                "Disk write bytes per sampling interval",
                                ["container"], registry=self.registry)

    def monitor_container(self, container):
        container_name = container.name
        logging.info(f"Starting monitoring for container: {container_name}")
        prev_net_io = prev_blk_io = None

        while True:
            try:
                stats = container.stats(stream=False)

                # Print raw stats for debugging
                logging.debug(f"Raw stats for {container_name}: {stats}")

                # Collect CPU, Memory, Network, and Disk metrics
                self._collect_cpu_metrics(stats, container_name)
                self._collect_memory_metrics(stats, container_name)
                self._collect_network_metrics(stats, prev_net_io, container_name)
                self._collect_disk_metrics(stats, prev_blk_io, container_name)

                prev_net_io = stats.get("networks", {})
                prev_blk_io = stats.get("blkio_stats", {}).get("io_service_bytes_recursive", [])

            except Exception as e:
                logging.error(f"Error monitoring container {container_name}: {e}")

            time.sleep(5)  # Adjust the sample rate

    def _collect_cpu_metrics(self, stats, container_name):
        try:
            cpu_current = stats["cpu_stats"]["cpu_usage"]["total_usage"]
            cpu_previous = stats["precpu_stats"]["cpu_usage"]["total_usage"]
            system_current = stats["cpu_stats"]["system_cpu_usage"]
            system_previous = stats["precpu_stats"]["system_cpu_usage"]

            cpu_delta = cpu_current - cpu_previous
            system_delta = system_current - system_previous

            if system_delta > 0:
                num_cpus = len(stats["cpu_stats"]["cpu_usage"].get("percpu_usage", []))
                cpu_percent = (cpu_delta / system_delta) * num_cpus * 100.0
            else:
                cpu_percent = 0

            logging.info(f"{container_name} - CPU Usage: {cpu_percent:.2f}%")
            self.cpu_usage.labels(container=container_name).set(cpu_percent)
        except KeyError as e:
            logging.error(f"Missing CPU stat for {container_name}: {e}")

    def _collect_memory_metrics(self, stats, container_name):
        try:
            mem_usage = stats["memory_stats"].get("usage", 0)
            mem_limit = stats["memory_stats"].get("limit", 1)  # Avoid division by zero
            mem_percent = (mem_usage / mem_limit) * 100.0

            logging.info(f"{container_name} - Memory Usage: {mem_percent:.2f}%")
            self.memory_usage.labels(container=container_name).set(mem_percent)
        except KeyError as e:
            logging.error(f"Missing Memory stat for {container_name}: {e}")

    def _collect_network_metrics(self, stats, prev_net_io, container_name):
        try:
            net_stats = stats.get("networks", {})
            total_tx = sum(interface.get("tx_bytes", 0) for interface in net_stats.values())
            total_rx = sum(interface.get("rx_bytes", 0) for interface in net_stats.values())

            logging.info(f"{container_name} - Network Sent: {total_tx} bytes, Received: {total_rx} bytes")

            if prev_net_io is not None:
                sent_delta = total_tx - prev_net_io.get("tx_bytes", 0)
                recv_delta = total_rx - prev_net_io.get("rx_bytes", 0)
                self.network_sent.labels(container=container_name).set(sent_delta)
                self.network_recv.labels(container=container_name).set(recv_delta)
        except KeyError as e:
            logging.error(f"Missing Network stat for {container_name}: {e}")

    def _collect_disk_metrics(self, stats, prev_blk_io, container_name):
        try:
            blk_stats = stats.get("blkio_stats", {}).get("io_service_bytes_recursive", [])
            read_bytes = write_bytes = 0
            for entry in blk_stats:
                op = entry.get("op", "").lower()
                value = entry.get("value", 0)
                if op == "read":
                    read_bytes += value
                elif op == "write":
                    write_bytes += value

            logging.info(f"{container_name} - Disk Read: {read_bytes} bytes, Disk Write: {write_bytes} bytes")

            if prev_blk_io is not None:
                read_delta = read_bytes - prev_blk_io.get("read", 0)
                write_delta = write_bytes - prev_blk_io.get("write", 0)
                self.disk_read.labels(container=container_name).set(read_delta)
                self.disk_write.labels(container=container_name).set(write_delta)
        except KeyError as e:
            logging.error(f"Missing Disk stat for {container_name}: {e}")

    def monitor_all_containers(self):

        containers = self.client.containers.list()
        logging.info(f"Started monitoring {containers[0].name}")

        if not containers:
            logging.warning("No running containers found to monitor.")

        for container in containers:
            threading.Thread(target=self.monitor_container, args=(container,), daemon=True).start()
            logging.info(f"Started monitoring thread for {container.name}")

    # def get_metrics(self):
    #     # Return Docker metrics in Prometheus format
    #     return generate_latest(self.registry)  # Pass the registry containing all metrics
    
    def get_metrics(self):
        """
        Collect and return Docker container metrics in Prometheus format.
        """
        prometheus_output = generate_latest(self.registry)
        return prometheus_output.decode('utf-8')

    
    
