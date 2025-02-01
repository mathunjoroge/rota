from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField,HiddenField
from wtforms.validators import DataRequired

class OrgForm(FlaskForm):
    name = StringField('Organization Name', validators=[DataRequired()])
    department = StringField('Department')
    submit = SubmitField('Add Organization')
class EditRotaForm(FlaskForm):
    id = HiddenField()  # Hidden ID for each row
    week_range = StringField('Week Range', validators=[DataRequired()])
    shift_8_5 = StringField('Day-shift (8 AM - 5 PM)', validators=[DataRequired()])
    shift_5_8 = StringField('Evening shift (5 PM - 8 PM)', validators=[DataRequired()])
    shift_8_8 = StringField('Night-shift (8 PM - 8 AM)', validators=[DataRequired()])
    night_off = StringField('Night Off')  # Optional
    submit = SubmitField('Update')