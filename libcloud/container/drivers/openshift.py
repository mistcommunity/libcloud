from libcloud.common.openshift import OpenShiftBasicAuthConnection
from libcloud.container.kubernetes import KubernetesContainerDriver


class OpenShiftContainerDriver(KubernetesContainerDriver):
    connectionCls = OpenShiftBasicAuthConnection
