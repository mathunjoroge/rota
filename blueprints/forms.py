from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField, HiddenField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError
from models.models import User  # Import your User model


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

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=2, max=20)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    level = SelectField('Level', choices=[('', 'Select Level'), ('0', 'Normal User'), ('1', 'Admin')], validators=[DataRequired()])
    submit = SubmitField('Sign Up')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('That username is taken. Please choose a different one.')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('That email is taken. Please choose a different one.')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')
    
class EditProfileForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=2, max=20)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[Length(min=6, max=20)])
    submit = SubmitField('Save Changes')    