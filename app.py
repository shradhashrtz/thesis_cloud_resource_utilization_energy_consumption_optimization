import threading
from flask import Flask, Response, jsonify, render_template, request
import logging
import os

from CustomAppMetrics import CustomAppMetricsMonitor
from ResolveAlert import ResolveAlert
from DockerMetrics import DockerMetricsMonitor
from prometheus_client.parser import text_fd_to_metric_families
from io import StringIO
import psutil
import requests
import docker



# Set logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')


# Initialize the Flask app with the custom templates folder
app = Flask(__name__, template_folder='View')

# Initialize CustomAppMetrics
app_names = ["custom_app"]
custom_app_metrics = CustomAppMetricsMonitor(app_names)
resolve_alerts = ResolveAlert()

# Initialize DockerMetrics
docker_metrics = DockerMetricsMonitor()

@app.route('/metrics', methods=['GET'])
def metrics():
    """
    Expose the /metrics endpoint to Prometheus for scraping.
    Collects both custom app and Docker container metrics.
    """
    try:
        custom_metrics_data = custom_app_metrics.get_metrics()
        docker_metrics_data = docker_metrics.get_metrics()

        # Combine both custom app and Docker container metrics
        combined_metrics = custom_metrics_data + docker_metrics_data
        
        return Response(combined_metrics, content_type='text/plain')
    except Exception as e:
        logging.error(f"Error fetching metrics: {e}")
        return Response(f"Error fetching metrics: {str(e)}", status=500, content_type='text/plain')
    


def parse_metrics(prometheus_text):
    """
    Parses Prometheus metrics text output and converts it into a dictionary.
    """
    parsed_metrics = {}
    try:
        for family in text_fd_to_metric_families(StringIO(prometheus_text)):
            for sample in family.samples:
                labels = tuple(sample.labels.items())
                parsed_metrics[(family.name, labels)] = sample.value
    except Exception as e:
        logging.error(f"Error parsing metrics: {e}")
    
    return parsed_metrics


def start_docker_monitoring():
    """
    Starts Docker monitoring in a separate thread.
    """
    docker_metrics.monitor_all_containers()


@app.route('/grafana_dashboard')
def grafana_dashboard():
    return render_template('metrics_dashboard.html')

@app.route('/metrics_status', methods=['GET'])
def metrics_status():
    try:

        logging.info("Starting metrics and alerts from prometheus.. ")
        # Get recommendations and evaluate utilization
        status_messages = evaluate_utilization()

        # Fetch Prometheus alerts
        alerts = fetch_prometheus_alerts()

        # If no status messages or alerts, show success message
        if not status_messages and not alerts:
            return render_template("status.html", message="✅ All applications, services, and alerts are optimal.")

        # Combine status messages and alerts into a single data structure
        return render_template("metrics_status.html", status_messages=status_messages, alerts=alerts)

    except Exception as e:
        logging.error(f"Error evaluating metrics: {e}")
        return render_template("error.html", error_message=str(e))


# Flask routes for alert handling
@app.route('/resolve_alert', methods=['POST'])
def resolve_alert():
    # Get the data sent by the frontend
    data = request.get_json()  # Get the JSON data
    alert_name = data.get("alertname")
    service_name = data.get("service")
    source = data.get("source")  # Fetch source
    stack_name = "my_thesis_"

    if not alert_name or not service_name or not source:
        return jsonify({"status": "error", "message": "Missing alertname, container_name, or source"}), 400

    service_name = stack_name + service_name
    # Perform resolution based on the alertname and source
    if source == "docker":
        if alert_name == "HighCPUUsage":
            resolve_alerts.handle_high_cpu_usage(service_name)
        elif alert_name == "HighMemoryUsage":
            resolve_alerts.handle_high_memory_usage(service_name)
    elif source == "custom_app":
        if alert_name == "HighAppCpuUsage":
            resolve_alerts.handle_app_high_cpu_usage(service_name)
        elif alert_name == "HighAppMemoryUsage":
            resolve_alerts.handle_app_high_memory_usage(source,service_name)
        

    return jsonify({"status": "success", "message": f"Alert {alert_name} for {service_name} from {source} resolved."})

@app.route('/scale_up', methods=['POST'])
def scale_up():
    try:
        data = request.json
        stack_name = "my_thesis_"
        service_name = data['service']
        scale_factor = int(data.get('scale_factor', 1))  # Default to increasing by 1

        docker_url = os.getenv('DOCKER_URL', 'tcp://localhost:2375')
        dockerClient = docker.DockerClient(base_url=docker_url)

        service = next((s for s in dockerClient.services.list() if s.name == stack_name + service_name), None)
        if service is None:
            return jsonify({"error": "Service not found"}), 404

        current_replicas = service.attrs['Spec']['Mode'].get('Replicated', {}).get('Replicas', 1)
        new_replicas = current_replicas + scale_factor

        service.update(mode={"Replicated": {"Replicas": new_replicas}})
        return jsonify({"status": "success", "message": f"Scaled up {service_name} to {new_replicas} replicas"})
    except Exception as e:
        return jsonify({"status": "failed","error": str(e)}), 500


@app.route('/scale_down', methods=['POST'])
def scale_down():
    try:
        data = request.json
        service_name = data['service']
        stack_name = "my_thesis_"
        scale_factor = int(data.get('scale_factor', 1))  # Default to decreasing by 1

        docker_url = os.getenv('DOCKER_URL', 'tcp://localhost:2375')
        dockerClient = docker.DockerClient(base_url=docker_url)

        service = next((s for s in dockerClient.services.list() if s.name == stack_name + service_name), None)
        if service is None:
            return jsonify({"error": "Service not found"}), 404

        current_replicas = service.attrs['Spec']['Mode'].get('Replicated', {}).get('Replicas', 1)
        new_replicas = max(0, current_replicas - scale_factor)  # Ensure replicas don't go negative

        service.update(mode={"Replicated": {"Replicas": new_replicas}})
        return jsonify({"status": "success", "message": f"Scaled down {service_name} to {new_replicas} replicas"})
    except Exception as e:
        return jsonify({"status": "failed","error": str(e)}), 500


def fetch_prometheus_alerts():
    """Fetch active alerts from Prometheus /alerts endpoint."""
    try:
        response = requests.get(f"{os.getenv('ALERTMANAGER_URL', 'http://172.27.36.125:9093')}/api/v2/alerts")
        response.raise_for_status()
        alerts_data = response.json()

        # Loop through each alert and extract necessary data
        alerts = []
        for alert in alerts_data:
            # Extract source from the labels section
            source = alert['labels'].get('source', 'No source provided')
             # Extract the instance (service) information
            instance = alert['labels'].get('instance', 'No instance provided')

            # Extract service name (ignore port if present)
            service = instance.split(':')[0]  # Get the part before the colon (service name)

            alert_data = {
                "alertname": alert['labels'].get('alertname', 'No alertname provided'),
                "severity": alert['labels'].get('severity', 'No severity provided'),
                "service": service,
                "description": alert['annotations'].get('description', 'No description provided'),
                "state": alert['status'].get('state', 'No state provided'),
                "source": source  # Add source here
            }
            alerts.append(alert_data)

        return alerts

    except Exception as e:
        logging.error(f"Error fetching alerts from Alertmanager: {e}")
        return []
    

def evaluate_utilization():
    status_messages = []

    # Loop through app names for custom metrics
    for app_name in app_names:
        # Fetch the custom application metrics from Prometheus
        cpu_usage = get_metrics_from_prometheus(f"cpu_usage{{app='{app_name}'}}")
        memory_usage = get_metrics_from_prometheus(f"memory_usage{{app='{app_name}'}}")
        energy_usage = get_metrics_from_prometheus(f"energy_used_joules{{app='{app_name}'}}")

        # Fallback to 0 if metrics are None
        cpu_usage = cpu_usage if cpu_usage is not None else 0
        memory_usage = memory_usage if memory_usage is not None else 0
        energy_usage = energy_usage if energy_usage is not None else 0

        if cpu_usage == 0 or memory_usage == 0 or energy_usage == 0:
            print(f"Metrics for app '{app_name}' are missing or 0. Using default values.")

        # Check if app already exists in the list
        app_entry = next((entry for entry in status_messages if entry['name'] == app_name), None)
        if app_entry is None:
            app_entry = {
                'name': app_name,
                'cpu': cpu_usage,
                'memory': memory_usage,
                'energy': energy_usage,
                'cpu_recommendation': "✅ CPU usage is optimal.",
                'memory_recommendation': "✅ Memory usage is optimal.",
                'energy_recommendation': "✅ Energy consumption is low."
            }
            status_messages.append(app_entry)

        # Recommendation based on CPU usage
        if cpu_usage < 70:
            app_entry['cpu_recommendation'] = "✅ CPU usage is optimal."
        elif 70 <= cpu_usage < 85:
            app_entry['cpu_recommendation'] = "⚠️ High CPU usage. Consider scaling or optimizing."
        else:
            app_entry['cpu_recommendation'] = "❌ Critical CPU usage. Immediate scaling needed."

        # Recommendation based on memory usage
        if memory_usage < 70:
            app_entry['memory_recommendation'] = "✅ Memory usage is optimal."
        elif 70 <= memory_usage < 85:
            app_entry['memory_recommendation'] = "⚠️ High memory usage. Consider optimizing memory consumption."
        else:
            app_entry['memory_recommendation'] = "❌ Critical memory usage. Scaling or optimization required."

        # Recommendation based on energy usage (if relevant)
        if energy_usage < 50:
            app_entry['energy_recommendation'] = "✅ Energy consumption is low."
        elif 50 <= energy_usage < 75:
            app_entry['energy_recommendation'] = "⚠️ Moderate energy consumption. Monitor usage."
        else:
            app_entry['energy_recommendation'] = "❌ High energy consumption. Consider optimizing."

    # Now evaluate Docker service metrics
    docker_url = os.getenv('DOCKER_URL', 'tcp://localhost:2375')
    dockerClient = docker.DockerClient(base_url=docker_url)
    services = dockerClient.services.list()  # Get a list of all running services

    for service in services:
        service_name = service.name
        # Fetch Docker service metrics from Prometheus (you might need to adjust the metric names to match those for services)
        cpu_usage = get_metrics_from_prometheus(f"docker_service_cpu_usage_percent{{service='{service_name}'}}")
        memory_usage = get_metrics_from_prometheus(f"docker_service_memory_usage_mb{{service='{service_name}'}}")
        cpu_energy = get_metrics_from_prometheus(f"docker_service_cpu_energy_consumption_watt_hour{{service='{service_name}'}}")
        memory_energy = get_metrics_from_prometheus(f"docker_service_memory_energy_consumption_watt_hour{{service='{service_name}'}}")

        # Fallback to 0 if any metric is None
        cpu_usage = cpu_usage if cpu_usage is not None else 0
        memory_usage = memory_usage if memory_usage is not None else 0
        cpu_energy = cpu_energy if cpu_energy is not None else 0
        memory_energy = memory_energy if memory_energy is not None else 0

        if cpu_usage == 0 or memory_usage == 0 or (cpu_energy + memory_energy) == 0:
            print(f"Metrics for service '{service_name}' are missing or 0. Using default values.")

        # Check if service already exists in the list
        service_entry = next((entry for entry in status_messages if entry['name'] == service_name), None)
        if service_entry is None:
            service_entry = {
                'name': service_name,
                'cpu': cpu_usage,
                'memory': memory_usage,
                'energy': cpu_energy + memory_energy,
                'cpu_recommendation': "✅ CPU usage is optimal.",
                'memory_recommendation': "✅ Memory usage is optimal.",
                'energy_recommendation': "✅ Energy consumption is low."
            }
            status_messages.append(service_entry)

        # Recommendation based on CPU usage for Docker service
        if cpu_usage < 70:
            service_entry['cpu_recommendation'] = "✅ CPU usage is optimal."
        elif 70 <= cpu_usage < 85:
            service_entry['cpu_recommendation'] = "⚠️ High CPU usage. Consider scaling or optimizing workload."
        else:
            service_entry['cpu_recommendation'] = "❌ Critical CPU usage. Immediate scaling needed."

        # Recommendation based on memory usage for Docker service
        if memory_usage < 70:
            service_entry['memory_recommendation'] = "✅ Memory usage is optimal."
        elif 70 <= memory_usage < 85:
            service_entry['memory_recommendation'] = "⚠️ High memory usage. Consider optimizing memory usage."
        else:
            service_entry['memory_recommendation'] = "❌ Critical memory usage. Scaling required."

        # Recommendation based on energy usage for Docker service
        if (cpu_energy + memory_energy) < 50:
            service_entry['energy_recommendation'] = "✅ Energy consumption is low."
        elif 50 <= (cpu_energy + memory_energy) < 75:
            service_entry['energy_recommendation'] = "⚠️ Moderate energy consumption. Monitor usage."
        else:
            service_entry['energy_recommendation'] = "❌ High energy consumption. Consider optimizing."

    return status_messages





def get_total_cpu_capacity(app_name=None):
    # Get the total number of physical CPU cores
    total_cpu_cores = psutil.cpu_count(logical=False)
    
    # Assuming each CPU core contributes 100% of the total CPU capacity
    total_cpu_capacity = total_cpu_cores * 100
    
    return total_cpu_capacity  # Return the total CPU capacity in percentage


def get_total_memory_capacity(app_name=None):
    # Get total system memory in bytes
    total_memory = psutil.virtual_memory().total
    
    # Convert bytes to MB
    total_memory_mb = total_memory / (1024 ** 2)
    
    return total_memory_mb  # Return the system's total memory in MB

    
def get_metrics_from_prometheus(query):
    try:
        prometheus_url=os.getenv('PROMETHEUS_URL', 'http://localhost:9090')
        # prometheus_url = "http://localhost:9090"

        response = requests.get(f"{prometheus_url}/api/v1/query?query={query}")
        data = response.json()
        
        if data['status'] == 'success' and data['data']['result']:
            return float(data['data']['result'][0]['value'][1])  # return the value of the metric
        else:
            return None
    except Exception as e:
        print(f"Error querying Prometheus: {e}")
        return None

def start_docker_monitoring():
    """
    Starts Docker monitoring in a separate thread.
    """
    docker_metrics.monitor_all_services()

monitoring_thread = threading.Thread(target=start_docker_monitoring)
monitoring_thread.start()

if __name__ == "__main__":
    # Start monitoring in separate threads
    # monitoring_thread = threading.Thread(target=start_docker_monitoring)
    # monitoring_thread.start()

    # Start Flask application
    app.run(host='0.0.0.0', port=5000, debug=True)



# python -m venv venv
# venv/Scripts/activate  --windows

# python3 -m venv venvpy
# source venvpy/bin/activate  --linux
#  or
# . venvpy/bin/activate

# pip install -r requirements.txt






