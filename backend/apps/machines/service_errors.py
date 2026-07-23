"""Typed failures for the machine-service workflow."""


class ServiceInvalidTransition(Exception):
    pass


class ServiceMachineUnavailable(Exception):
    pass


class ServiceInsufficientStock(Exception):
    pass


class ServiceConsumptionInvalid(Exception):
    pass
