import requests
import time

# Replace with your actual URL
url = 'http://172.27.36.125:8001/get_data'

while True:
    try:
        response = requests.get(url)
        if response.status_code == 200:
            print(f"Data fetched successfully. Response time: {response.elapsed.total_seconds()} seconds")
        else:
            print(f"Failed to fetch data. Status code: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
    
    # Wait before making another request
    time.sleep(0.00001)  # Adjust the interval as needed
