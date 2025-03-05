import psutil  # Library to collect system metrics
import logging
from prometheus_client import CollectorRegistry, Gauge, generate_latest

class CustomAppMetricsMonitor:
    def __init__(self, app_names):
        self.registry = CollectorRegistry()
        self.cpu_usage = Gauge('cpu_usage', 'CPU usage percentage', ['app'], registry=self.registry)
        self.memory_usage = Gauge('memory_usage', 'Memory usage in MB', ['app'], registry=self.registry)
        self.app_names = app_names

    def collect_app_metrics(self):
        """
        Collect metrics for each app.
        """
        for app in self.app_names:
            # Simulate collecting metrics for each app
            # In a real application, you may need a way to get per-app stats, 
            # but here we collect system-wide stats
            cpu_value = psutil.cpu_percent(interval=1)  # Get CPU usage as a percentage over 1 second
            mem_value = psutil.virtual_memory().used / (1024 * 1024)  # Get used memory in MB

            logging.info(f"Collecting metrics for {app}: CPU {cpu_value}%, Memory {mem_value}MB")
            self.cpu_usage.labels(app=app).set(cpu_value)
            self.memory_usage.labels(app=app).set(mem_value)

    def get_metrics(self):
        """
        Collect and return application metrics in Prometheus format.
        """
        self.collect_app_metrics()
        prometheus_output = generate_latest(self.registry)

        return prometheus_output.decode('utf-8')
