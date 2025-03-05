import time
import logging
import requests
from prometheus_client import Gauge, generate_latest, CollectorRegistry
from webob import Request, Response  # type: ignore
import psutil
import threading
import os


class API1:
    def __init__(self):
        # Create a registry and gauge for tracking the API response time
        self.registry = CollectorRegistry()

        # Metric for API response duration
        self.api_response_duration = Gauge(
            'api_response_duration_seconds',
            'Duration of the API response in seconds',
            registry=self.registry
        )

        # Metric for CPU usage (in percentage)
        self.cpu_usage_gauge = Gauge(
            'custom_app_cpu_usage_percent',
            'CPU usage of the custom application (percentage)',
            registry=self.registry
        )

        # Metric for Memory usage (in percentage)
        self.memory_usage_gauge = Gauge(
            'custom_app_memory_usage_percent',
            'Memory usage of the custom application (percentage)',
            registry=self.registry
        )

        # Metrics for Network Bandwidth (in bytes per second)
        self.network_sent_gauge = Gauge(
            'custom_app_network_sent_bytes_per_second',
            'Network bandwidth (bytes sent per second)',
            registry=self.registry
        )
        self.network_recv_gauge = Gauge(
            'custom_app_network_recv_bytes_per_second',
            'Network bandwidth (bytes received per second)',
            registry=self.registry
        )

        # Start background threads to update CPU, memory usage, and network bandwidth
        self.start_cpu_usage_thread()
        self.start_memory_usage_thread()
        self.start_network_bandwidth_thread()

    def __call__(self, environ, start_response):
        request = Request(environ)
        if request.path == "/get_data":
            return self.get_data(environ, start_response)
        elif request.path == "/metrics":
            return self.metrics(environ, start_response)
        elif request.path == "/cputask":
            return self.cpu_intensive_task(environ, start_response)
        elif request.path == "/memorytask":
            return self.memory_intensive_task(environ, start_response)
        elif request.path == "/networktask":
            return self.network_bandwidth_intensive_task(environ, start_response)
        else:
            response = Response()
            response.text = "Invalid endpoint"
            response.status = 404
            return response(environ, start_response)

    def get_data(self, environ, start_response):
        url = 'https://api.spot-hinta.fi/Html/12/1'
        start_time = time.time()

        try:
            # Make the GET request
            response = requests.get(url)
            duration = time.time() - start_time

            # Update the gauge with the response time
            self.api_response_duration.set(duration)

            if response.status_code == 200:
                logging.info("Successfully retrieved HTML data")
                return Response(body=response.text, content_type='text/plain')(environ, start_response)
            else:
                logging.error("Failed to retrieve data: %s", response.status_code)
                return Response(status=response.status_code, text=f"Failed to retrieve data: {response.status_code}")(environ, start_response)
        except requests.RequestException as e:
            logging.error("Error fetching data: %s", e)
            return Response(status=500, text="Error fetching data")(environ, start_response)

    def cpu_intensive_task(self, environ, start_response):
        start_time = time.time()
        duration = 10  # Duration in seconds
        result = 0
        while time.time() - start_time < duration:
            for i in range(1, 100000):
                result += i ** 0.5  # Perform heavy calculations
        response = Response()
        response.text = "CPU-intensive task completed."
        response.status = 200
        return response(environ, start_response)
     
    def memory_intensive_task(self, environ, start_response):
        memory_hog = []
        size_mb = 1000  # Allocate 1 GB in memory
        try:
            for _ in range(size_mb):
                memory_hog.append(bytearray(1024 * 1024))  # Allocate 1 MB chunks
                time.sleep(0.01)  # Slight delay to avoid freezing
        except MemoryError:
            response = Response()
            response.text = "Memory limit exceeded!"
            response.status = 500
            return response(environ, start_response)
        
        response = Response()
        response.text = f"Memory-intensive task completed. Allocated {len(memory_hog)} MB."
        response.status = 200
        return response(environ, start_response)
    
    
    def start_cpu_usage_thread(self):
        def update_cpu_usage():
            while True:
                cpu_usage = psutil.cpu_percent(interval=1)  # Get CPU usage percentage
                self.cpu_usage_gauge.set(cpu_usage)  # Update the metric
                time.sleep(1)  # Update every second

        threading.Thread(target=update_cpu_usage, daemon=True).start()

    def start_memory_usage_thread(self):
        def update_memory_usage():
            while True:
                memory_usage = psutil.virtual_memory().percent  # Get memory usage percentage
                self.memory_usage_gauge.set(memory_usage)  # Update the metric
                time.sleep(1)  # Update every second

        threading.Thread(target=update_memory_usage, daemon=True).start()

    def start_network_bandwidth_thread(self):
        def update_network_bandwidth():
            prev_net_io = psutil.net_io_counters()  # Get initial network I/O counters
            while True:
                time.sleep(1)  # Update every second
                current_net_io = psutil.net_io_counters()

                # Calculate bytes sent and received per second
                sent_per_sec = current_net_io.bytes_sent - prev_net_io.bytes_sent
                recv_per_sec = current_net_io.bytes_recv - prev_net_io.bytes_recv

                # Update the metrics
                self.network_sent_gauge.set(sent_per_sec)
                self.network_recv_gauge.set(recv_per_sec)

                # Update previous counters
                prev_net_io = current_net_io

        threading.Thread(target=update_network_bandwidth, daemon=True).start()

    def network_bandwidth_intensive_task(self, environ, start_response):
        """Simulates high network bandwidth usage by downloading and uploading data."""
        url = "http://localhost:8000/testfile.bin"  # URL of a test file for download
        temp_file = "temp_download.bin"
        data_size =  1024 * 1024  # 50 MB data for upload simulation

        try:
            # Download the file
            download_start = time.time()
            response =  requests.get(url, stream=True, verify=False)  # Disable SSL verification
            with open(temp_file, "wb") as f:
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        f.write(chunk)
            download_duration = time.time() - download_start

            # Generate and upload data
            upload_data = os.urandom(data_size)
            upload_start = time.time()
            upload_response = requests.post(url, data=upload_data, verify=False)
            upload_duration = time.time() - upload_start

            # Clean up the temporary file
            if os.path.exists(temp_file):
                os.remove(temp_file)

            response = Response()
            response.text = (
                f"Network-intensive task completed.\n"
                f"Download duration: {download_duration:.2f} seconds\n"
                f"Upload duration: {upload_duration:.2f} seconds"
            )
            response.status = 200
            return response(environ, start_response)

        except Exception as e:
            logging.error(f"Error during network-intensive task: {e}")
            response = Response()
            response.text = f"Error during network-intensive task: {e}"
            response.status = 500
            return response(environ, start_response)

    def metrics(self, environ, start_response):
        # Generate the metrics in Prometheus format
        metrics_data = generate_latest(self.registry)
        return Response(body=metrics_data, content_type='text/plain')(environ, start_response)


# Example WSGI entry point
def app1(environ, start_response):
    return API1()(environ, start_response)
