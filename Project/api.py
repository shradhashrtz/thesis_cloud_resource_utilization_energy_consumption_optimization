import time
import logging
import requests
from prometheus_client import Gauge, generate_latest, CollectorRegistry
from webob import Request, Response  # type: ignore
import psutil
import time
import start_http_server


class API:
    def __init__(self):
        # Create a registry and gauge for tracking the API response time
        self.registry = CollectorRegistry()
        # Define a metric for CPU usage
        self.api_response_duration = Gauge(
            'api_response_duration_seconds',
            'Duration of the API response in seconds',
            registry=self.registry
        )

    def __call__(self, environ, start_response):
        request = Request(environ)
        if request.path == "/get_data":
            return self.get_data()(environ, start_response)
        elif request.path == "/metrics":
            return self.metrics()(environ, start_response)
        else:
            # response = Response()
            # response.text = "Invalid endpoint"
            # response.status = 404
            # return response(environ, start_response)
            return self.get_data()(environ, start_response)

    def get_data(self):
        url = 'https://api.spot-hinta.fi/Html/12/1'
        start_time = time.time()

        # Make the GET request
        response = requests.get(url)
        duration = time.time() - start_time

        # Update the gauge with the response time
        self.api_response_duration.set(duration)

        if response.status_code == 200:
            logging.info("Successfully retrieved HTML data")
            return Response(body=response.text, content_type='text/plain')
        else:
            logging.error("Failed to retrieve data: %s", response.status_code)
            return Response(status=response.status_code, text=f"Failed to retrieve data: {response.status_code}")

    def metrics(self):
        metrics_data = generate_latest(self.registry)
        start_http_server(8000)  # Exposes metrics on http://localhost:8000/metrics
        monitor_cpu()
        return Response(body=metrics_data, content_type='text/plain')


# Example WSGI entry point
def app(environ, start_response):
    return API()(environ, start_response)

def monitor_cpu():
    cpu_usage = Gauge('custom_app_cpu_usage', 'CPU usage of the custom application')

    while True:
        # Update CPU usage metric
        cpu_usage.set(psutil.cpu_percent(interval=1))
        time.sleep(1)
