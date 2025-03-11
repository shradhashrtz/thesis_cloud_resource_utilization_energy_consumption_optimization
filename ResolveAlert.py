import psutil  # Library to collect system metrics
import subprocess
import docker
import logging
import os
from docker.errors import DockerException

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class ResolveAlert:
    def __init__(self, docker_url=os.getenv('DOCKER_URL', 'tcp://localhost:2375'), registry=None):
        self.client = docker.DockerClient(base_url=docker_url)
        # Connect to Docker daemon
        try:
            self.client = docker.DockerClient(base_url=docker_url)
            logging.info("Connected to Docker daemon at %s", docker_url)
        except Exception as e:
            logging.error("Failed to connect to Docker daemon: %s", e)
            raise


    # Helper function to get a process by name
    def get_process_by_name(self, app_name):
        for process in psutil.process_iter(attrs=['pid', 'name']):
            if process.info['name'] == app_name:
                return process
        return None
    
    def handle_high_cpu_usage(self, service_name, cpu_limit="0.5"):
        """
        Handle high CPU usage for a Docker service by updating the CPU limit.
        """
        print(f"Handling high CPU usage for service: {service_name}")
        try:
            service = self.client.services.get(service_name)
            spec = service.attrs['Spec']

            if 'TaskTemplate' in spec:
                resources = spec['TaskTemplate'].get('Resources', {})
                resources['Limits'] = resources.get('Limits', {})

                # Convert CPU limit to NanoCPUs (Docker expects values in nanoseconds)
                resources['Limits']['NanoCPUs'] = int(float(cpu_limit) * 1e9)

                # Update the service
                service.update(task_template={"Resources": resources})
                logging.info(f"Updated CPU limit for service {service_name} to {cpu_limit} CPUs")
                print(f"CPU usage limited for service {service_name} to {cpu_limit} CPUs.")

                return {"status": "success", "message": f"CPU limit updated for service {service_name} to {cpu_limit} CPUs"}

        except DockerException as e:
            logging.error(f"Docker error while updating CPU for service {service_name}: {e}")
            return {"status": "error", "message": str(e)}
        except Exception as e:
            logging.error(f"Error updating CPU for service {service_name}: {e}")
            return {"status": "error", "message": str(e)}

    def handle_high_memory_usage(self, service_name, mem_limit="256M"):
        """
        Handle high memory usage for a Docker service by updating memory limits.
        """
        print(f"Handling high memory usage for service: {service_name}")
        try:
            service = self.client.services.get(service_name)
            spec = service.attrs['Spec']

            if 'TaskTemplate' in spec:
                resources = spec['TaskTemplate'].get('Resources', {})
                resources['Limits'] = resources.get('Limits', {})

                # Convert memory limit to bytes
                resources['Limits']['MemoryBytes'] = self.convert_to_bytes(mem_limit)

                # Update the service
                service.update(task_template={"Resources": resources})
                logging.info(f"Updated memory limit for service {service_name} to {mem_limit}")
                print(f"Memory limit for service {service_name} updated to {mem_limit}.")

                return {"status": "success", "message": f"Memory limit updated for service {service_name} to {mem_limit}"}

        except DockerException as e:
            logging.error(f"Docker error while updating memory for service {service_name}: {e}")
            return {"status": "error", "message": str(e)}
        except Exception as e:
            logging.error(f"Error updating memory for service {service_name}: {e}")
            return {"status": "error", "message": str(e)}

    def convert_to_bytes(self, mem_limit):
        """
        Convert memory limit (e.g., '128M', '1G') to bytes.
        """
        size, unit = int(mem_limit[:-1]), mem_limit[-1].upper()
        if unit == 'M':
            return size * 1024 * 1024  # Megabytes to bytes
        elif unit == 'G':
            return size * 1024 * 1024 * 1024  # Gigabytes to bytes
        else:
            raise ValueError("Unsupported memory unit. Only 'M' and 'G' are supported.")

          

             # Handle high CPU usage for custom applications
    def handle_app_high_cpu_usage(self, app_name, instance):
        print(f"Handling high CPU usage for application {app_name} (Instance: {instance})")

        process = self.get_process_by_name(app_name)
        if not process:
            print(f"Application {app_name} (Instance: {instance}) is not running. Skipping CPU limit adjustment.")
            return

        try:
            process.nice(psutil.IDLE_PRIORITY_CLASS if os.name == 'nt' else psutil.NICE_LOW_PRIORITY)
            print(f"CPU priority lowered for application {app_name} (Instance: {instance}).")
        except Exception as e:
            print(f"Error limiting CPU usage for application {app_name} (Instance: {instance}): {e}")

    # Handle high memory usage for custom applications
    def handle_app_high_memory_usage(self, app_name, instance):
        print(f"Handling high memory usage for application {app_name} (Instance: {instance})")

        process = self.get_process_by_name(app_name)
        if not process:
            print(f"Application {app_name} (Instance: {instance}) is not running. Skipping memory limit adjustment.")
            return

        try:
            process.rlimit(psutil.RLIMIT_AS, (1024 * 1024 * 1024, 1024 * 1024 * 1024))  # 1GB limit
            print(f"Memory usage limited for application {app_name} (Instance: {instance}) to 1GB.")
        except Exception as e:
            print(f"Error limiting memory usage for application {app_name} (Instance: {instance}): {e}")

    