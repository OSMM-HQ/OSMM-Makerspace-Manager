HARDWARE_REQUESTER_DEFAULTS = {
    "request_received": {
        "subject": "{{ makerspace.name }} request received",
        "text": (
            "Your makerspace request #{{ request.id }} was received.\n\n"
            "Status: {{ request.status }}\n"
            "Use your email or phone on the public request page to check status."
        ),
    },
    "request_accepted": {
        "subject": "{{ makerspace.name }} request approved",
        "text": (
            "Your makerspace request #{{ request.id }} has been approved."
            "{% if request.return_due_at %}\n\nReturn by: {{ request.return_due_at }}{% endif %}"
        ),
    },
    "request_rejected": {
        "subject": "{{ makerspace.name }} request rejected",
        "text": (
            "Your makerspace request #{{ request.id }} was rejected."
            "{% if request.rejection_reason %}\n\nReason: {{ request.rejection_reason }}{% endif %}"
        ),
    },
    "request_issued": {
        "subject": "{{ makerspace.name }} request issued",
        "text": (
            "Your approved makerspace request #{{ request.id }} has been handed out."
            "{% if request.return_due_at %}\n\nReturn by: {{ request.return_due_at }}{% endif %}"
        ),
    },
    "request_returned": {
        "subject": "{{ makerspace.name }} request returned",
        "text": "Your makerspace request #{{ request.id }} has been returned and closed.",
    },
    "return_reminder": {
        "subject": "{{ makerspace.name }} return reminder",
        "text": (
            "Your makerspace request #{{ request.id }} is due for return."
            "{% if request.return_due_at %}\n\nReturn due: {{ request.return_due_at }}{% endif %}"
        ),
    },
}

HARDWARE_STAFF_DEFAULTS = {
    "submitted": {
        "subject": "{{ makerspace.name }} hardware request #{{ request.id }} submitted",
        "text": "A new hardware request needs review.\n\n{{ staff_summary }}",
    },
    "accepted": {
        "subject": "{{ makerspace.name }} hardware request #{{ request.id }} accepted",
        "text": "Hardware request #{{ request.id }} was accepted.\n\n{{ staff_summary }}",
    },
    "rejected": {
        "subject": "{{ makerspace.name }} hardware request #{{ request.id }} rejected",
        "text": "Hardware request #{{ request.id }} was rejected.\n\n{{ staff_summary }}",
    },
    "issued": {
        "subject": "{{ makerspace.name }} hardware request #{{ request.id }} issued",
        "text": "Hardware request #{{ request.id }} was issued.\n\n{{ staff_summary }}",
    },
    "partially_returned": {
        "subject": "{{ makerspace.name }} hardware request #{{ request.id }} partially returned",
        "text": "Hardware request #{{ request.id }} was partially returned.\n\n{{ staff_summary }}",
    },
    "returned": {
        "subject": "{{ makerspace.name }} hardware request #{{ request.id }} returned",
        "text": "Hardware request #{{ request.id }} was fully returned and closed.\n\n{{ staff_summary }}",
    },
    "closed_with_issue": {
        "subject": "{{ makerspace.name }} hardware request #{{ request.id }} closed with issue",
        "text": "Hardware request #{{ request.id }} was closed with damaged or missing items.\n\n{{ staff_summary }}",
    },
    "return_reminder": {
        "subject": "{{ makerspace.name }} hardware request #{{ request.id }} return reminder",
        "text": "Hardware request #{{ request.id }} is due for return.\n\n{{ staff_summary }}",
    },
}

PRINTING_REQUESTER_SUBJECTS = {
    "submitted": "We received your makerspace print request",
    "accepted": "Your makerspace print request was accepted",
    "started": "Your makerspace print request is now printing",
    "rejected": "Your makerspace print request was rejected",
    "completed": "Your makerspace print request is ready to collect",
}

PRINTING_REQUESTER_TEXT = {
    "submitted": """Hello,

We've received your print request "{{ print_request.title }}".

Bucket: {{ print_request.bucket.name }}
Makerspace: {{ print_request.bucket.makerspace.name }}

We'll email you again when its status changes. You can also track it with your request link.
{% if status_url %}
Track your request: {{ status_url }}
{% endif %}
Tracking token: {{ public_token }}
""",
    "accepted": """Hello {{ print_request.requester.username }},

Your print request "{{ print_request.title }}" has been accepted.

Bucket: {{ print_request.bucket.name }}
Makerspace: {{ print_request.bucket.makerspace.name }}
{% if status_url %}
Track your request: {{ status_url }}
{% endif %}
Tracking token: {{ public_token }}
""",
    "started": """Hello,

Your print request "{{ print_request.title }}" is now printing.

Bucket: {{ print_request.bucket.name }}
Makerspace: {{ print_request.bucket.makerspace.name }}

We'll let you know when it's ready to collect.
{% if status_url %}
Track your request: {{ status_url }}
{% endif %}
Tracking token: {{ public_token }}
""",
    "rejected": """Hello {{ print_request.requester.username }},

Your print request "{{ print_request.title }}" has been rejected.

Reason: {{ print_request.reason }}

Bucket: {{ print_request.bucket.name }}
Makerspace: {{ print_request.bucket.makerspace.name }}
{% if status_url %}
Track your request: {{ status_url }}
{% endif %}
Tracking token: {{ public_token }}
""",
    "completed": """Hello {{ print_request.requester.username }},

Your print request "{{ print_request.title }}" is complete.

Bucket: {{ print_request.bucket.name }}
Makerspace: {{ print_request.bucket.makerspace.name }}
{% if status_url %}
Track your request: {{ status_url }}
{% endif %}
Tracking token: {{ public_token }}
""",
}

PRINTING_REQUESTER_HTML = {
    "submitted": """{% extends "email/base.html" %}

{% block body %}
  <p>Hello,</p>
  <p>We've received your print request <strong>{{ print_request.title }}</strong>.</p>
  <p>Bucket: {{ print_request.bucket.name }}<br>
  Makerspace: {{ print_request.bucket.makerspace.name }}</p>
  <p>We'll email you again when its status changes. You can also track it with your request link.</p>
  {% if status_url %}
    <p>Track your request: <a href="{{ status_url }}">{{ status_url }}</a></p>
  {% endif %}
  <p>Tracking token: <strong>{{ public_token }}</strong></p>
{% endblock %}
""",
    "accepted": """{% extends "email/base.html" %}

{% block body %}
  <p>Hello {{ print_request.requester.username }},</p>
  <p>Your print request <strong>{{ print_request.title }}</strong> has been accepted.</p>
  <p>Bucket: {{ print_request.bucket.name }}<br>
  Makerspace: {{ print_request.bucket.makerspace.name }}</p>
  {% if status_url %}
    <p>Track your request: <a href="{{ status_url }}">{{ status_url }}</a></p>
  {% endif %}
  <p>Tracking token: <strong>{{ public_token }}</strong></p>
{% endblock %}
""",
    "started": """{% extends "email/base.html" %}

{% block body %}
  <p>Hello,</p>
  <p>Your print request <strong>{{ print_request.title }}</strong> is now printing.</p>
  <p>Bucket: {{ print_request.bucket.name }}<br>
  Makerspace: {{ print_request.bucket.makerspace.name }}</p>
  <p>We'll let you know when it's ready to collect.</p>
  {% if status_url %}
    <p>Track your request: <a href="{{ status_url }}">{{ status_url }}</a></p>
  {% endif %}
  <p>Tracking token: <strong>{{ public_token }}</strong></p>
{% endblock %}
""",
    "rejected": """{% extends "email/base.html" %}

{% block body %}
  <p>Hello {{ print_request.requester.username }},</p>
  <p>Your print request <strong>{{ print_request.title }}</strong> has been rejected.</p>
  <p>Reason: {{ print_request.reason }}</p>
  <p>Bucket: {{ print_request.bucket.name }}<br>
  Makerspace: {{ print_request.bucket.makerspace.name }}</p>
  {% if status_url %}
    <p>Track your request: <a href="{{ status_url }}">{{ status_url }}</a></p>
  {% endif %}
  <p>Tracking token: <strong>{{ public_token }}</strong></p>
{% endblock %}
""",
    "completed": """{% extends "email/base.html" %}

{% block body %}
  <p>Hello {{ print_request.requester.username }},</p>
  <p>Your print request <strong>{{ print_request.title }}</strong> is complete.</p>
  <p>Bucket: {{ print_request.bucket.name }}<br>
  Makerspace: {{ print_request.bucket.makerspace.name }}</p>
  {% if status_url %}
    <p>Track your request: <a href="{{ status_url }}">{{ status_url }}</a></p>
  {% endif %}
  <p>Tracking token: <strong>{{ public_token }}</strong></p>
{% endblock %}
""",
}

PRINTING_STAFF_SUBJECTS = {
    "submitted": "{{ makerspace.name }} print request #{{ print_request.id }} submitted",
    "accepted": "{{ makerspace.name }} print request #{{ print_request.id }} accepted",
    "started": "{{ makerspace.name }} print request #{{ print_request.id }} started",
    "completed": "{{ makerspace.name }} print request #{{ print_request.id }} completed",
    "rejected": "{{ makerspace.name }} print request #{{ print_request.id }} rejected",
    "failed": "{{ makerspace.name }} print request #{{ print_request.id }} failed",
    "collected": "{{ makerspace.name }} print request #{{ print_request.id }} collected",
    "reprinted": "{{ makerspace.name }} reprint request #{{ print_request.id }} accepted",
}

PRINTING_STAFF_TEXT = """Print request #{{ print_request.id }} {{ event }}.

Status: {{ print_request.status }}
Title: {{ print_request.title }}
Requester: {% firstof print_request.requester_name print_request.requester.username %}{% if print_request.contact_email %}
Email: {{ print_request.contact_email }}{% elif print_request.requester.email %}
Email: {{ print_request.requester.email }}{% endif %}{% if print_request.contact_phone %}
Phone: {{ print_request.contact_phone }}{% endif %}{% if print_request.material %}
Material: {{ print_request.material }}{% endif %}{% if print_request.color %}
Color: {{ print_request.color }}{% endif %}
Quantity: {{ print_request.quantity }}{% if print_request.reason %}
Reason: {{ print_request.reason }}{% endif %}{% if print_request.reprint_of_id %}
Reprint of: #{{ print_request.reprint_of_id }}{% endif %}"""
