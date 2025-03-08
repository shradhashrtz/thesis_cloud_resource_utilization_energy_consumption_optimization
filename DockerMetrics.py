import logging
import time
import threading
import os
from prometheus_client import Gauge, CollectorRegistry, generate_latest
import docker

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

        # Define Prometheus Gauges with a "service" label to differentiate services
        self.cpu_usage = Gauge("docker_service_cpu_usage_percent", "CPU usage percent for Docker services", ["service"], registry=self.registry)
        self.memory_usage = Gauge("docker_service_memory_usage_percent", "Memory usage percent for Docker services", ["service"], registry=self.registry)
        self.network_sent = Gauge("docker_service_network_sent_bytes", "Network transmitted bytes per sampling interval", ["service"], registry=self.registry)
        self.network_recv = Gauge("docker_service_network_recv_bytes", "Network received bytes per sampling interval", ["service"], registry=self.registry)
        self.disk_read = Gauge("docker_service_disk_read_bytes", "Disk read bytes per sampling interval", ["service"], registry=self.registry)
        self.disk_write = Gauge("docker_service_disk_write_bytes", "Disk write bytes per sampling interval", ["service"], registry=self.registry)

        # Energy gauges
        self.cpu_energy_consumption = Gauge("docker_service_cpu_energy_consumption_watt_hour", "Estimated CPU energy consumption in watt-hours for Docker services", ["service"], registry=self.registry)
        self.memory_energy_consumption = Gauge("docker_service_memory_energy_consumption_watt_hour", "Estimated memory energy consumption in watt-hours for Docker services", ["service"], registry=self.registry)

        self.source = "docker"

    def monitor_service(self, service):
        service_name = service.name
        logging.info(f"Starting monitoring for service: {service_name}")
        
        prev_net_io = {}
        prev_blk_io = {}

        while True:
            try:
                # Get the containers associated with the service
                containers = self.client.containers.list(filters={"label": f"com.docker.swarm.service.name={service_name}"})
                
                # Initialize metrics to aggregate service-level stats
                total_cpu_percent = 0
                total_mem_percent = 0
                total_network_sent = 0
                total_network_recv = 0
                total_disk_read = 0
                total_disk_write = 0
                total_cpu_energy = 0
                total_memory_energy = 0
                num_containers = len(containers)

                if num_containers == 0:
                    logging.warning(f"No containers found for service {service_name}. Skipping.")
                    time.sleep(5)
                    continue

                # Aggregate metrics across containers
                for container in containers:
                    # Get container stats
                    container_stats = container.stats(stream=False)
                    total_cpu_percent += self._collect_cpu_metrics(container_stats)
                    total_mem_percent += self._collect_memory_metrics(container_stats)
                    network_sent, network_recv = self._collect_network_metrics(container_stats, prev_net_io)  # Unpack the tuple
                    total_network_sent += network_sent
                    total_network_recv += network_recv
                    disk_read, disk_write = self._collect_disk_metrics(container_stats, prev_blk_io)  # Unpack the tuple
                    total_disk_read += disk_read
                    total_disk_write += disk_write
                    total_cpu_energy += self._estimate_energy_consumption(container_stats, "cpu")
                    total_memory_energy += self._estimate_energy_consumption(container_stats, "memory")

                # Average the metrics across containers for service-level stats
                self.cpu_usage.labels(service=service_name).set(total_cpu_percent / num_containers)
                self.memory_usage.labels(service=service_name).set(total_mem_percent / num_containers)
                self.network_sent.labels(service=service_name).set(total_network_sent)
                self.network_recv.labels(service=service_name).set(total_network_recv)
                self.disk_read.labels(service=service_name).set(total_disk_read)
                self.disk_write.labels(service=service_name).set(total_disk_write)
                self.cpu_energy_consumption.labels(service=service_name).set(total_cpu_energy / num_containers)
                self.memory_energy_consumption.labels(service=service_name).set(total_memory_energy / num_containers)

                logging.info(f"{service_name} - CPU Usage: {total_cpu_percent / num_containers:.2f}%, "
                             f"Memory Usage: {total_mem_percent / num_containers:.2f}%, "
                             f"Network Sent: {total_network_sent} bytes, "
                             f"Network Recv: {total_network_recv} bytes, "
                             f"Disk Read: {total_disk_read} bytes, "
                             f"Disk Write: {total_disk_write} bytes")

                # Update previous stats
                prev_net_io = container_stats.get("networks", {})
                prev_blk_io = container_stats.get("blkio_stats", {}).get("io_service_bytes_recursive", [])

            except Exception as e:
                logging.error(f"Error monitoring service {service_name}: {e}")

            time.sleep(5)  # Adjust the sample rate

    def monitor_all_services(self):
        services = self.client.services.list()
        logging.info(f"Started monitoring {len(services)} services")

        if not services:
            logging.warning("No running services found to monitor.")

        for service in services:
            threading.Thread(target=self.monitor_service, args=(service,), daemon=True).start()
            logging.info(f"Started monitoring thread for {service.name}")

    def _collect_cpu_metrics(self, stats):
        try:
            cpu_current = stats["cpu_stats"]["cpu_usage"]["total_usage"]
            cpu_previous = stats["precpu_stats"]["cpu_usage"]["total_usage"]
            system_current = stats["cpu_stats"]["system_cpu_usage"]
            system_previous = stats["precpu_stats"]["system_cpu_usage"]
            cpu_delta = cpu_current - cpu_previous
            system_delta = system_current - system_previous
            num_cpus = len(stats["cpu_stats"]["cpu_usage"].get("percpu_usage", []))
            cpu_percent = round((cpu_delta / system_delta) * num_cpus * 100.0, 2) if system_delta > 0 else 0
            return cpu_percent
        except KeyError as e:
            logging.error(f"Missing CPU stat: {e}")
            return 0

    def _collect_memory_metrics(self, stats):
        try:
            mem_usage = stats["memory_stats"].get("usage", 0)
            mem_limit = stats["memory_stats"].get("limit", 1)
            mem_percent = round((mem_usage / mem_limit) * 100.0, 2)
            return mem_percent
        except KeyError as e:
            logging.error(f"Missing Memory stat: {e}")
            return 0

    def _collect_network_metrics(self, stats, prev_net_io):
        try:
            networks = stats.get("networks", {})
            total_sent = 0
            total_recv = 0
            for net_name, net_data in networks.items():
                sent = net_data.get("tx_bytes", 0) - prev_net_io.get(net_name, {}).get("tx_bytes", 0)
                recv = net_data.get("rx_bytes", 0) - prev_net_io.get(net_name, {}).get("rx_bytes", 0)
                total_sent += sent
                total_recv += recv
            return total_sent, total_recv  # Return as a tuple
        except KeyError as e:
            logging.error(f"Missing Network stat: {e}")
            return 0, 0  # Return as a tuple

    def _collect_disk_metrics(self, stats, prev_blk_io):
        try:
            read_bytes = sum(io_stat["value"] for io_stat in stats.get("blkio_stats", {}).get("io_service_bytes_recursive", []) if io_stat["op"] == "Read")
            write_bytes = sum(io_stat["value"] for io_stat in stats.get("blkio_stats", {}).get("io_service_bytes_recursive", []) if io_stat["op"] == "Write")
            return read_bytes, write_bytes  # Return as a tuple
        except KeyError as e:
            logging.error(f"Missing Disk stat: {e}")
            return 0, 0  # Return as a tuple

    def _estimate_energy_consumption(self, stats, metric_type):
        try:
            if metric_type == "cpu":
                cpu_power_per_core = 0.1
                cpu_energy = round(stats["cpu_stats"]["cpu_usage"]["total_usage"] * cpu_power_per_core / 1000, 4)
                return cpu_energy
            elif metric_type == "memory":
                memory_power_per_gb = 0.05
                mem_usage = stats["memory_stats"].get("usage", 0) / (1024 ** 2)
                memory_usage_gb = mem_usage / 1024
                memory_energy = round(memory_usage_gb * memory_power_per_gb, 4)
                return memory_energy
        except KeyError as e:
            logging.error(f"Missing energy stat for {metric_type}: {e}")
            return 0

    def get_metrics(self):
        """
        Collect and return Docker service metrics in Prometheus format.
        """
        prometheus_output = generate_latest(self.registry)
        return prometheus_output.decode('utf-8')
