import requests
from bs4 import BeautifulSoup

# Target URL
url = "https://your-website.com/checkout"

# List of common class names for credit card information
class_names = [
    "credit-card-info",
    "card-info",
    "payment-info",
    "credit-card-details",
    "card-number",
    "card-holder",
    "expiration-date",
    "cvv",
    "card-type",
    "payment-method",
    "billing-details",
    "credit-card-form",
    "payment-form",
]

# Send a GET request to the website
response = requests.get(url)

# Check if the request was successful
if response.status_code == 200:
    # Parse the HTML content
    soup = BeautifulSoup(response.content, "html.parser")

    # Try to find elements with the specified class names
    for class_name in class_names:
        elements = soup.find_all("div", class_=class_name)
        if elements:
            print(f"Found elements with class name: {class_name}")
            for element in elements:
                print("Element:", element.get_text(strip=True))
                print("-" * 30)
else:
    print("Failed to retrieve the webpage. Status code:", response.status_code)
