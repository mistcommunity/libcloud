from libcloud.common.openshift import OpenShiftBasicAuthConnection
from libcloud.container.drivers.kubernetes import KubernetesContainerDriver


class OpenShiftContainerDriver(KubernetesContainerDriver):
    connectionCls = OpenShiftBasicAuthConnection
