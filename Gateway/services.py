"""Acceso a los servicios compartidos por las rutas HTTP."""

from flask import current_app


def servicios():
    return current_app.extensions["dfsha"]
