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

    # Helper function to check if Docker container is running
    def is_container_running(self, container_name):
        try:
            result = subprocess.run(
                ["docker", "ps", "-q", "-f", f"name={container_name}"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                return True
            return False
        except Exception as e:
            print(f"Error checking container status for {container_name}: {e}")
            return False


 # Helper function to get a process by name
    def get_process_by_name(self, app_name):
        for process in psutil.process_iter(attrs=['pid', 'name']):
            if process.info['name'] == app_name:
                return process
        return None
    
    def handle_high_cpu_usage(self, container_name):
        """
        Handle high CPU usage for a Docker container.
        """
        print(f"Handling high CPU usage for Docker container: {container_name}")
        try:
            # Get the container
            container = self.client.containers.get(container_name)

            # Update CPU limits (0.5 CPUs = 50% of one CPU core)
            # container.update(cpu_quota=int(0.5 * 100000))  # Docker expects CPU quota in microseconds
            container.update(cpu_quota=int(0.1 * 100000))  # Docker expects CPU quota in microseconds
            print(f"CPU usage limited for container {container_name} to 50%.")
        
        except DockerException as e:
            print(f"Docker error occurred while limiting CPU usage for {container_name}: {e}")
        except Exception as e:
            print(f"An error occurred while limiting CPU usage for {container_name}: {e}")


 

    def handle_high_memory_usage(self, container_name):
        """
        Handle high memory usage for a Docker container by updating memory and memory swap limits.
        """
        print(f"Handling high memory usage for Docker container: {container_name}")
        try:
            # Get the container
            container = self.client.containers.get(container_name)
            mem_limit = '10m'  # You can adjust this limit as needed

            # Check current memoryswap setting
            current_memoryswap = container.attrs['HostConfig'].get('MemorySwap', -1)

            # Convert the mem_limit to bytes
            mem_limit_bytes = self.convert_to_bytes(mem_limit)

            # If current memoryswap is less than the memory limit, update memoryswap too
            if current_memoryswap != -1 and current_memoryswap < mem_limit_bytes:
                # Set both memory_limit and memswap_limit
                container.update(mem_limit=mem_limit, memswap_limit=mem_limit)
                print(f"Memory limit and memoryswap for container {container_name} updated to {mem_limit}.")
            else:
                # Only set memory_limit, leave memswap_limit to -1
                container.update(mem_limit=mem_limit, memswap_limit='-1')
                print(f"Memory limit for container {container_name} updated to {mem_limit}.")

        except DockerException as e:
            # Catch any errors related to Docker
            print(f"Docker error occurred: {e}")
        except Exception as e:
            # Catch any other general errors
            print(f"An error occurred: {e}")

    def convert_to_bytes(self, mem_limit):
        """
        Convert memory limit (e.g., '128m', '1g') to bytes.
        """
        size, unit = int(mem_limit[:-1]), mem_limit[-1].lower()
        if unit == 'm':
            return size * 1024 * 1024  # Megabytes to bytes
        elif unit == 'g':
            return size * 1024 * 1024 * 1024  # Gigabytes to bytes
        else:
            raise ValueError("Unsupported memory unit. Only 'm' and 'g' are supported.")
      

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

    