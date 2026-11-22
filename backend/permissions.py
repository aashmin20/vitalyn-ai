"""
Who may do what. The single place that defines the role matrix; routes import these sets.

| action                                   | admin | doctor | nurse | receptionist |
| staff approval, audit log                | yes   |        |       |              |
| register / edit / admit patients         | yes   | yes    |       | yes          |
| transfer, bed status                     | yes   | yes    | yes   |              |
| discharge                                | yes   | yes    |       |              |
| delete patient record, create rooms/beds | yes   |        |       |              |
| live monitoring, camera registration     | yes   | yes    | yes   |              |
| fall alerts: view, acknowledge, resolve  | yes   | yes    | yes   |              |
| appointments: book, check in             | yes   | yes    |       | yes          |
| consultation: start / complete           | yes   | yes    |       |              |
"""
from auth import ROLES

ADMIN = ("admin",)
DOCTORS = ("admin", "doctor")
CLINICAL = ("admin", "doctor", "nurse")                  # sees patients' video, alerts, monitoring
REGISTRARS = ("admin", "doctor", "receptionist")         # registers / admits patients
FRONT_DESK = ("admin", "doctor", "receptionist")         # appointments
ANY_STAFF = ROLES
