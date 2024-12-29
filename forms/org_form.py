from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired

class OrgForm(FlaskForm):
    name = StringField('Organization Name', validators=[DataRequired()])
    department = StringField('Department')
    submit = SubmitField('Add Organization')
