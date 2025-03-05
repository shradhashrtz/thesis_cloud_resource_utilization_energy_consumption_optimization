import requests

# Prometheus server URL
PROMETHEUS_URL = "http://localhost:9090/api/v1/query"

# Function to query Prometheus
def query_prometheus(query):
    response = requests.get(PROMETHEUS_URL, params={'query': query})
    if response.status_code == 200:
        result = response.json()
        return result['data']['result']
    else:
        print(f"Error querying Prometheus: {response.status_code}")
        return None

# Example query: CPU utilization
cpu_query = 'avg(rate(node_cpu_seconds_total{mode!="idle"}[5m]))'
cpu_data = query_prometheus(cpu_query)

# Print the CPU utilization
# if cpu_data:
#     print("CPU Utilization (Average):")
#     for metric in cpu_data:
#         print(f"Instance: {metric['metric']['instance']}, Value: {metric['value'][1]}")

# Example query: Memory utilization (percentage used)
# memory_query = '100 * (1 - (node_memory_MemFree_bytes / node_memory_MemTotal_bytes))'
memory_query = 'custom_app_memory_usage_percent'
memory_data = query_prometheus(memory_query)

# Print the memory utilization
if memory_data:
    print("\nMemory Utilization (Percentage):")
    for metric in memory_data:
        print(f"Instance: {metric['metric']['instance']}, Value: {metric['value'][1]}%")
