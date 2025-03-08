import psutil
import logging
import time
from prometheus_client import CollectorRegistry, Gauge, generate_latest

class CustomAppMetricsMonitor:
    def __init__(self, app_names):
        self.registry = CollectorRegistry()
        self.cpu_usage = Gauge('cpu_usage', 'CPU usage percentage', ['app'], registry=self.registry)
        self.memory_usage = Gauge('memory_usage', 'Memory usage in MB', ['app'], registry=self.registry)
        self.disk_usage = Gauge('disk_usage', 'Disk usage in MB', ['app'], registry=self.registry)
        self.network_sent = Gauge('network_sent_bytes', 'Network sent bytes (MB)', ['app'], registry=self.registry)
        self.network_recv = Gauge('network_recv_bytes', 'Network received bytes (MB)', ['app'], registry=self.registry)
        self.energy_usage = Gauge('energy_used_joules', 'Estimated energy consumption in Joules', ['app'], registry=self.registry)
        
        self.app_names = app_names
        self.last_time = time.time()  # Store the last timestamp for energy calculation

    def collect_app_metrics(self):
        """
        Collect metrics for each app, including estimated energy consumption.
        """
        current_time = time.time()
        elapsed_time = current_time - self.last_time  # Time interval in seconds

        for app in self.app_names:
            # CPU Usage
            cpu_value = round(psutil.cpu_percent(interval=0), 2)  # Non-blocking call
            cpu_power = round(cpu_value * 0.5, 2)  # 0.5W per 1% CPU usage
            
            # Memory Usage
            mem_value = round(psutil.virtual_memory().used / (1024 * 1024), 2)  # Convert bytes to MB
            mem_power = round((mem_value / 1024) * 0.3, 2)  # 0.3W per 1GB RAM usage

            # Disk Usage
            disk_io = psutil.disk_io_counters()
            disk_usage = round((disk_io.read_bytes + disk_io.write_bytes) / (1024 * 1024), 2)  # Convert to MB
            disk_power = round(disk_usage * 0.2, 2)  # 0.2W per MB read/write

            # Network Usage
            net_io = psutil.net_io_counters()
            net_sent = round(net_io.bytes_sent / (1024 * 1024), 2)  # Convert to MB
            net_recv = round(net_io.bytes_recv / (1024 * 1024), 2)  # Convert to MB
            net_power = round((net_sent + net_recv) * 0.1, 2)  # 0.1W per MB sent/received

            # Calculate estimated energy in Joules
            total_power = cpu_power + mem_power + disk_power + net_power
            energy_used = round(total_power * elapsed_time, 2)  # Energy = Power * Time
            
            # Log and update Prometheus metrics
            logging.info(f"Metrics for {app}: CPU {cpu_value}%, Memory {mem_value}MB, Disk {disk_usage}MB, Network Sent {net_sent}MB, Network Recv {net_recv}MB, Energy {energy_used}J")
            
            self.cpu_usage.labels(app=app).set(cpu_value)
            self.memory_usage.labels(app=app).set(mem_value)
            self.disk_usage.labels(app=app).set(disk_usage)
            self.network_sent.labels(app=app).set(net_sent)
            self.network_recv.labels(app=app).set(net_recv)
            self.energy_usage.labels(app=app).set(energy_used)

        self.last_time = current_time  # Update last timestamp

    def get_metrics(self):
        """
        Collect and return application metrics in Prometheus format.
        """
        self.collect_app_metrics()
        prometheus_output = generate_latest(self.registry)
        return prometheus_output.decode('utf-8')
