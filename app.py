import threading
from flask import Flask, Response, jsonify, render_template
import logging
import os

from CustomAppMetrics import CustomAppMetricsMonitor
from DockerMetrics import DockerMetricsMonitor
from prometheus_client.parser import text_fd_to_metric_families
from io import StringIO
import docker
import psutil
import requests



# Set logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')


# Initialize the Flask app with the custom templates folder
app = Flask(__name__, template_folder='View')

# Initialize CustomAppMetrics
app_names = ["custom_app"]
custom_app_metrics = CustomAppMetricsMonitor(app_names)

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
    """
    Show utilization status for each Docker container and application with HTML formatting.
    """
    try:
        custom_metrics_data = custom_app_metrics.get_metrics()
        docker_metrics_data = docker_metrics.get_metrics()

        # Get recommendations and evaluate utilization
        status_messages = evaluate_utilization(custom_metrics_data, docker_metrics_data)

        if not status_messages:
            return render_template("status.html", message="✅ All applications and containers are running optimally.")

        # Format the output with HTML for better styling using Bootstrap
        return render_template("metrics_status.html", status_messages=status_messages)

    except Exception as e:
        logging.error(f"Error evaluating metrics: {e}")
        return render_template("error.html", error_message=str(e))
    
@app.route('/prometheus_alerts', methods=['GET'])
def prometheus_alerts():
    """
    Fetch and display active Prometheus alerts on a separate route.
    """
    try:
        # Fetch active alerts from Prometheus
        alerts = fetch_prometheus_alerts()

        # Return the alerts to the template
        return render_template("prometheus_alerts.html", alerts=alerts)
    except Exception as e:
        logging.error(f"Error fetching alerts from Prometheus: {e}")
        return render_template("error.html", error_message=str(e))

def fetch_prometheus_alerts():
    """
    Fetch active alerts from Prometheus /alerts endpoint.
    """
    try:
        response = requests.get(f"{os.getenv('PROMETHEUS_URL', '')}/api/v1/alerts")
        response.raise_for_status()
        alerts_data = response.json()

        active_alerts = []
        for alert in alerts_data['data']['alerts']:
            alert_info = {
                "alertname": alert['labels']['alertname'],
                "severity": alert['labels']['severity'],
                "instance": alert['labels']['instance'],
                "description": alert['annotations'].get('description', 'No description provided'),
                "state": alert['state'],
            }
            active_alerts.append(alert_info)

        return active_alerts
    except Exception as e:
        logging.error(f"Error fetching alerts from Prometheus: {e}")
        return []

def evaluate_utilization(custom_metrics, docker_metrics):
    status_messages = []

    # Parse custom metrics and evaluate utilization
    custom_metrics_parsed = parse_metrics(custom_metrics)

    for (metric_name, labels), value in custom_metrics_parsed.items():
        # Extract the application name
        app_name = labels[0][1] if isinstance(labels, tuple) and len(labels) > 0 and isinstance(labels[0], tuple) else labels[0]
        
        # Get the total CPU and memory (replace these with your actual metrics retrieval logic)
        total_cpu = get_total_cpu_capacity(app_name)  # This should fetch the actual CPU capacity
        total_memory = get_total_memory_capacity(app_name)  # This should fetch the actual memory capacity

        # Check if the app already exists in the list
        app_entry = next((entry for entry in status_messages if entry['name'] == app_name), None)
        
        if app_entry is None:
            # If the app does not exist, create a new entry
            app_entry = {'name': app_name, 'cpu': None, 'memory': None, 'cpu_total': total_cpu, 'memory_total': total_memory, 'recommendation': ""}
            status_messages.append(app_entry)

        if metric_name == 'cpu_usage':
            recommendation = ""
            if value < 70:
                recommendation = "✅ Usage is optimal."
            elif 70 <= value < 85:
                recommendation = "⚠️ High CPU usage. Consider scaling or optimizing."
            else:
                recommendation = "❌ Critical CPU usage. Immediate scaling needed."
            app_entry['cpu'] = value
            app_entry['recommendation'] = recommendation
        
        elif metric_name == 'memory_usage':
            recommendation = ""
            if value < 70:
                recommendation = "✅ Usage is optimal."
            elif 70 <= value < 85:
                recommendation = "⚠️ High memory usage. Consider optimizing memory consumption."
            else:
                recommendation = "❌ Critical memory usage. Scaling or optimization required."
            app_entry['memory'] = value
            app_entry['recommendation'] = recommendation

    # Parse Docker metrics and evaluate utilization
    docker_metrics_parsed = parse_metrics(docker_metrics)

    for (metric_name, labels), value in docker_metrics_parsed.items():
        # Extract the container name
        container_name = labels[0][1] if isinstance(labels, tuple) and len(labels) > 0 and isinstance(labels[0], tuple) else labels[0]

        # Get the total CPU and memory for the container (replace these with actual fetching logic)
        total_cpu = get_container_cpu_capacity(container_name)  # This should fetch the actual CPU capacity for the container
        total_memory = get_container_memory_capacity(container_name)  # This should fetch the actual memory capacity for the container

        # Check if the container already exists in the list
        container_entry = next((entry for entry in status_messages if entry['name'] == container_name), None)
        
        if container_entry is None:
            # If the container does not exist, create a new entry
            container_entry = {'name': container_name, 'cpu': None, 'memory': None, 'cpu_total': total_cpu, 'memory_total': total_memory, 'recommendation': ""}
            status_messages.append(container_entry)

        if metric_name == 'docker_container_cpu_usage_percent':
            recommendation = ""
            if value < 70:
                recommendation = "✅ Usage is optimal."
            elif 70 <= value < 85:
                recommendation = "⚠️ High CPU usage. Consider scaling or optimizing workload."
            else:
                recommendation = "❌ Critical CPU usage. Immediate scaling needed."
            container_entry['cpu'] = value
            container_entry['recommendation'] = recommendation
        
        elif metric_name == 'docker_container_memory_usage_percent':
            recommendation = ""
            if value < 70:
                recommendation = "✅ Usage is optimal."
            elif 70 <= value < 85:
                recommendation = "⚠️ High memory usage. Consider optimizing memory usage."
            else:
                recommendation = "❌ Critical memory usage. Scaling required."
            container_entry['memory'] = value
            container_entry['recommendation'] = recommendation
    
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


def get_container_cpu_capacity(container_name):
    docker_url=os.getenv('DOCKER_URL', 'tcp://localhost:2375')
    client =  docker.DockerClient(base_url=docker_url)  # Connect to the Docker daemon
    container = client.containers.get(container_name)
    
    # Get container stats (CPU, memory, etc.)
    stats = container.stats(stream=False)
    
    # Retrieve the CPU count or limit; here we assume 'cpu_percent' or 'cpu_quota'
    cpu_limit = stats['cpu_stats']['cpu_usage']['total_usage']  # Total CPU time used by the container
    
    # If you want to get the number of CPUs allocated to the container:
    cpus = stats['cpu_stats']['online_cpus']  # Number of online CPUs for the container
    
    return cpus * 100  # Example: return total allocated CPU as percentage (multiply by 100 for percentage)



def get_container_memory_capacity(container_name):
    docker_url=os.getenv('DOCKER_URL', 'tcp://localhost:2375')
    client =  docker.DockerClient(base_url=docker_url)  # Connect to the Docker daemon
    container = client.containers.get(container_name)
    
    # Get container stats (including memory usage)
    stats = container.stats(stream=False)
    
    # Retrieve memory limit from the stats
    memory_limit = stats['memory_stats']['limit']  # Total memory allocated for the container (in bytes)
    
    # Convert bytes to MB or GB, for example
    memory_limit_mb = memory_limit / (1024 ** 2)  # Convert bytes to MB
    
    return memory_limit_mb  # Return the memory limit in MB






def start_docker_monitoring():
    """
    Starts Docker monitoring in a separate thread.
    """
    docker_metrics.monitor_all_containers()

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