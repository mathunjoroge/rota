# Rota Management System

A web-based application for managing organizational rotas, team members, shifts, and leaves. This application is built using Flask and is structured using blueprints for modularity and ease of maintenance.

## Features

- **Organization Management**: Add, edit, and delete organizational details.
- **Team Member Management**: Add, edit, and delete team members.
- **Shift Management**: Add, edit, and delete shifts.
- **Leave Management**: Manage leaves for team members.
- **Rota Generation**: Automatically generate and manage rotas.
- **PDF Export**: Export rotas to PDF format.

## Project Structure
app structure.
rota/
│
├── app.py
├── models/
│   └── models.py
├── blueprints/
│   ├── org.py
│   ├── members.py
│   ├── shifts.py
│   ├── leave.py
│   ├── rota.py
│   └── pdf.py
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── org_details.html
│   ├── members.html
│   ├── edit_member.html
│   ├── shifts.html
│   ├── on_leave.html
│   ├── rota.html
│   └── export_pdf.html
├── static/
│   ├── css/
│   │   └── styles.css
│   ├── js/
│   │   └── scripts.js
│   └── images/
│       └── logo.png
└── forms/
│   ├── forms.py
## Getting Started

### Prerequisites

- Python 3.8+
- Flask
- Flask-WTF
- Flask-SQLAlchemy
- xhtml2pdf

### Installation

1. Clone the repository:
    ```sh
    git clone https://github.com/yourusername/rota-management-system.git
    cd rota-management-system
    ```

2. Create and activate a virtual environment:
    ```sh
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3. Install the dependencies:
    ```sh
    pip install -r requirements.txt
    ```

4. Set up the database:
    ```sh
    flask db init
    flask db migrate
    flask db upgrade
    ```

### Running the Application

1. Start the Flask application:
    ```sh
    flask run
    ```

2. Open a web browser and navigate to `http://127.0.0.1:5000/`.

## Usage

The application provides the following routes:

- `/`: Home page.
- `/add_org`: Add a new organization.
- `/org_details`: View and manage organization details.
- `/members`: View and manage team members.
- `/shifts`: View and manage shifts.
- `/on_leave`: View leaves for today.
- `/generate_rota`: Generate and manage rotas.
- `/export_pdf`: Export rotas to PDF.

## Contributing

Contributions are welcome! Please follow these steps to contribute:

1. Fork the repository.
2. Create a new branch (`git checkout -b feature/your-feature`).
3. Commit your changes (`git commit -am 'Add some feature'`).
4. Push to the branch (`git push origin feature/your-feature`).
5. Create a new Pull Request.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Acknowledgements

- [Flask](https://flask.palletsprojects.com/)
- [Flask-WTF](https://flask-wtf.readthedocs.io/)
- [Flask-SQLAlchemy](https://flask-sqlalchemy.palletsprojects.com/)
- [xhtml2pdf](https://github.com/xhtml2pdf/xhtml2pdf)
- 
