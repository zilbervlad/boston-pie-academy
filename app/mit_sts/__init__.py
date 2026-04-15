from .routes_shared import mit_sts_bp

from . import user_routes  # noqa: F401
from . import dashboard_routes  # noqa: F401
from . import template_routes  # noqa: F401
from . import mit_profile_routes  # noqa: F401
from . import level_routes  # noqa: F401
from . import task_routes  # noqa: F401
from . import promotion_routes  # noqa: F401
from . import export_routes  # noqa: F401
from . import binder_routes  # noqa: F401

__all__ = ["mit_sts_bp"]