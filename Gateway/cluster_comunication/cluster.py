"""Fachada del administrador del clúster."""

from .cluster_core import ClusterCore
from .cluster_membership import MembershipOperations
from .cluster_monitoring import ClusterMonitoring
from .cluster_replication import ReplicationOperations


class ClusterManager(
    MembershipOperations, ReplicationOperations, ClusterMonitoring, ClusterCore
):
    """Combina coordinación, membresía y mantenimiento de réplicas."""

    pass
