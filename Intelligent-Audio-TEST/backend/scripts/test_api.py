
import requests

def test_api():
    url = "http://127.0.0.1:5000/api/v1/audios"
    try:
        response = requests.get(url)
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {response.headers}")
        data = response.json()
        print(f"Success: {data.get('success')}")
        if data.get('success'):
            items = data.get('data', {}).get('items', [])
            print(f"Total items returned: {len(items)}")
            if items:
                print(f"First item: {items[0]}")
        else:
            print(f"Error: {data.get('message')}")
    except Exception as e:
        print(f"Error connecting to API: {e}")

if __name__ == "__main__":
    test_api()
