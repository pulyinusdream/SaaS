import re

STATUSES = ('New', 'Contacted', 'Appointment booked', 'Closed')
SERVICES = ('HVAC', 'Plumbing', 'Roofing', 'Garage doors', 'Electrical', 'Other home service')


def text(form, key, maximum, errors, required=False, label=None):
    value = form.get(key, '').strip()
    name = label or key.replace('_', ' ').capitalize()
    if required and not value:
        errors[key] = f'Enter {name.lower()}.'
    elif len(value) > maximum:
        errors[key] = f'Keep {name.lower()} under {maximum} characters.'
    elif any(ord(ch) < 32 and ch not in '\n\r\t' for ch in value):
        errors[key] = f'Enter valid {name.lower()}.'
    return value


def email(value):
    return len(value) <= 254 and re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', value) is not None


def lead_values(form, services=SERVICES):
    errors = {}
    values = {key: text(form, key, maximum, errors, required=required) for key, maximum, required in (
        ('customer_name', 100, True), ('email', 254, False), ('phone', 40, False),
        ('service', 60, True), ('location', 200, True), ('message', 2000, False),
    )}
    if values['email'] and not email(values['email']):
        errors['email'] = 'Enter a valid email address.'
    if values['phone'] and not re.fullmatch(r'[+()0-9 .xX-]{7,40}', values['phone']):
        errors['phone'] = 'Enter a valid phone number.'
    if not values['email'] and not values['phone']:
        errors['email'] = 'Add an email address or phone number so the team can reply.'
    if values['service'] not in services:
        errors['service'] = 'Choose a service currently offered by this business.'
    return values, errors
