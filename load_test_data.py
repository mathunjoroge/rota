from models.models import TemperatureLog, db
from flask import Flask
import requests
from datetime import datetime, timedelta
import os

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI', 'sqlite:///test.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# Weather API configuration
API_KEY = os.getenv('OPENWEATHERMAP_API_KEY', 'your_default_api_key')
LOCATION = 'kisumu'

def fetch_temperature():
    """Fetch current temperature from the weather API."""
    url = f'http://api.openweathermap.org/data/2.5/weather?q={LOCATION}&appid={API_KEY}&units=metric'
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return data['main']['temp']
    else:
        print(f"Failed to fetch temperature: {response.json().get('message', 'Unknown error')}")
        return None

def load_test_data():
    """Load test data into the TemperatureLog table."""
    with app.app_context():
        db.create_all()  # Ensure tables are created

        for i in range(10):  # Create 10 test records
            # Simulate different timestamps
            test_date = datetime.now().date() - timedelta(days=i)
            test_time_period = 'AM' if i % 2 == 0 else 'PM'

            # Fetch temperature data
            temp = fetch_temperature()
            if temp is not None:
                # Determine if temperature is acceptable
                acceptable = 18.0 <= temp <= 24.0

                # Create a new TemperatureLog entry
                temp_log = TemperatureLog(
                    date=test_date,
                    time=test_time_period,
                    recorded_temp=temp,
                    acceptable=acceptable,
                    initials='TEST'
                )

                db.session.add(temp_log)

        db.session.commit()
        print("Test data loaded successfully.")

# Run the script
if __name__ == '__main__':
    load_test_data()
