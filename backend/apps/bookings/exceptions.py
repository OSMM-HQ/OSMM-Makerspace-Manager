from rest_framework.exceptions import APIException


class BookingConflict(Exception):
    pass


class BookingInvalidTransition(Exception):
    pass


class BookerNamesRequiresAvailability(APIException):
    status_code = 400
    default_code = 'booker_names_requires_availability'
    default_detail = 'Booker names require public availability to be enabled.'

    def __init__(self):
        self.detail = {
            'detail': self.default_detail,
            'code': self.default_code,
        }
