# -*- coding: utf-8 -*-

"""
discopy error messages.
"""

import warnings


TYPE_ERROR = "Expected {}, got {} instead."
NOT_COMPOSABLE = "{} does not compose with {}: {} != {}."
NOT_PARALLEL = "Expected parallel arrows, got {} and {} instead."
NOT_ATOMIC = "Expected {} of length 1, got length {} instead."
NOT_CONNECTED = "{} is not boundary-connected."
NOT_ADJOINT = "{} and {} are not adjoints."
NOT_RIGID_ADJOINT = "{} is not the left adjoint of {}, maybe you meant to use"\
                    " a pivotal type rather than a rigid one?"
NOT_PREGROUP = "Expected a pregroup diagram of shape `word @ ... @ word "\
               ">> cups_and_swaps`, use diagram.draw() instead."
MISSING_TYPES_FOR_EMPTY_SUM = "Empty sum needs a domain and codomain."


class WarnOnce:
    warned = False

    def __init__(self):
        self.warned = False

    def warn(self, message):
        if not self.warned:
            warnings.warn(message)
        self.warned = True
