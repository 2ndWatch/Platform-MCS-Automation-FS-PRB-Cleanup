import requests

url = 'https://2ndwatchhelpdesk.freshservice.com/api/v2/problems'
api_key = 'NmoxMjl2THVwMU9tTjBrUG5oRA=='
headers = {
    'Content-Type': 'application/json',
    'Authorization': f'Basic {api_key}',
    'page': '1'
}
page = 1

while True:
    try:
        # Sending GET request with headers
        response = requests.get(url, headers=headers)

        # Checking if the request was successful (status code 200)
        if response.status_code == 200:
            # Parsing the JSON response
            data = response.json()
            print(f'Page {page}, {len(data["problems"])} results.')

            # print(response.headers)
            if 'Link' in response.headers:
                print('   Link exists, there is another page...')
                headers['page'] += str(int(headers['page']) + 1)
                page += 1
            print()

        else:
            print(f"Request failed with status code: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
