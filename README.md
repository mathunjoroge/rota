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
