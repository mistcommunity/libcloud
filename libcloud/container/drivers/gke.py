# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import os
import base64
import tempfile
from typing import Any, List, Dict, Optional, Union

from libcloud.common.google import GoogleOAuth2Credential
from libcloud.container.base import ContainerCluster, ClusterState
from libcloud.container.providers import Provider
from libcloud.container.drivers.kubernetes import KubernetesContainerDriver
from libcloud.common.google import GoogleResponse
from libcloud.common.google import GoogleBaseConnection
from libcloud.utils.misc import to_memory_str
from libcloud.utils.misc import to_n_bytes

API_VERSION = "v1"


class GKECluster(ContainerCluster):
    def __init__(
        self,
        id,
        name,
        node_count,
        location,
        config,
        status,
        host,
        port,
        token,
        token_expiry,
        ca_cert,
        nodepools,
        extra=None,
        total_cpus=None,
        total_memory=None,
    ):

        self.node_count = node_count
        self.location = location
        self.status = status
        self.config = config
        self.nodepools = nodepools
        self.total_cpus = total_cpus
        self.total_memory = total_memory
        self.credentials = {
            "host": host,
            "port": port,
            "token": token,
            "token_expiry": token_expiry.strftime('%Y-%m-%dT%H:%M:%SZ'),
            "ca_cert": ca_cert,
        }

        # CA Certificate can only be passed as a path to the underlying requests session.
        # The temporary file is accessed every time a request is made, so it must be
        # accessible for the span of the cluster's lifetime.
        cert_file = tempfile.NamedTemporaryFile("w", encoding="utf8", delete=False)
        cert_file.write(ca_cert)
        cert_file.close()
        self._cert_file_path = cert_file.name
        driver = KubernetesContainerDriver(
            host=host,
            port=port,
            key=token,
            ca_cert=self._cert_file_path,
            ex_token_bearer_auth=True,
        )
        super().__init__(id, name, driver, extra)

    def __del__(self):
        try:
            os.remove(self._cert_file_path)
        except FileNotFoundError:
            ...


class GKENodePool:
    """A class representing a GKE nodepool"""

    def __init__(
        self,
        name: str,
        state: str,
        size: str,
        locations: List[str],
        nodes: int,
        min_nodes: Optional[int] = None,
        max_nodes: Optional[int] = None,
        extra: Optional[Dict[str, Any]] = None,
    ):
        self.name = name
        self.state = state
        self.size = size
        self.locations = locations
        self.nodes = nodes
        self.min_nodes = min_nodes
        self.max_nodes = max_nodes
        self.extra = extra or {}

    def __repr__(self):
        return ("<GKENodePool: name=%s, state=%s, node_count=%s ...>") % (
            self.name,
            self.state,
            self.nodes,
        )


class GKEOperation:
    """Represents an operation that may have happened or are happening on the cluster"""

    def __init__(
        self,
        name: str,
        location: str,
        type: str,
        status: str,
    ):
        self.name = name
        self.location = location
        self.type = type
        self.status = status

    def __repr__(self):
        return ("<GKEOperation: name=%s, type=%s, status=%s ...>") % (
            self.name,
            self.type,
            self.status,
        )


class GKEResponse(GoogleResponse):
    pass


class GKEConnection(GoogleBaseConnection):
    """
    Connection class for the GKE driver.

    GKEConnection extends :class:`google.GoogleBaseConnection` for 3 reasons:
      1. modify request_path for GKE URI.
      2. Implement gce_params functionality described below.
      3. Add request_aggregated_items method for making aggregated API calls.

    """

    host = "container.googleapis.com"
    responseCls = GKEResponse

    def __init__(
        self,
        user_id,
        key,
        secure,
        auth_type=None,
        credential_file=None,
        project=None,
        **kwargs,
    ):
        super(GKEConnection, self).__init__(
            user_id,
            key,
            secure=secure,
            auth_type=auth_type,
            credential_file=credential_file,
            **kwargs,
        )
        self.request_path = "/%s/projects/%s" % (API_VERSION, project)
        self.gke_params = None

    def pre_connect_hook(self, params, headers):
        """
        Update URL parameters with values from self.gke_params.

        @inherits: :class:`GoogleBaseConnection.pre_connect_hook`
        """
        params, headers = super(GKEConnection, self).pre_connect_hook(params, headers)
        if self.gke_params:
            params.update(self.gke_params)
        return params, headers

    def request(self, *args, **kwargs):
        """
        Perform request then do GKE-specific processing of URL params.

        @inherits: :class:`GoogleBaseConnection.request`
        """
        response = super(GKEConnection, self).request(*args, **kwargs)

        # If gce_params has been set, then update the pageToken with the
        # nextPageToken so it can be used in the next request.
        if self.gke_params:
            if "nextPageToken" in response.object:
                self.gke_params["pageToken"] = response.object["nextPageToken"]
            elif "pageToken" in self.gke_params:
                del self.gke_params["pageToken"]
            self.gke_params = None

        return response


class GKEContainerDriver(KubernetesContainerDriver):
    """
    GKE Container Driver class.

    This is the primary driver for interacting with Google Container
    Engine. It contains all of the standard libcloud methods,
    plus additional ex_* methods for more features.

    Note that many methods allow either objects or strings (or lists of
    objects/strings).  In most cases, passing strings instead of objects
    will result in additional GKE API calls.
    """

    connectionCls = GKEConnection
    api_name = "google"
    name = "Google Container Engine"
    type = Provider.GKE
    website = "https://container.googleapis.com"
    supports_clusters = True

    AUTH_URL = "https://container.googleapis.com/auth/"

    CLUSTER_STATES = {
        "STATUS_UNSPECIFIED": ClusterState.UNKNOWN,
        "PROVISIONING": ClusterState.PENDING,
        "RUNNING": ClusterState.RUNNING,
        "RECONCILING": ClusterState.UPDATING,
        "STOPPING": ClusterState.STOPPING,
        "ERROR": ClusterState.ERROR,
        "DEGRADED": ClusterState.ERROR,
    }

    def __init__(
        self,
        user_id,
        key=None,
        datacenter=None,
        project=None,
        auth_type=None,
        scopes=None,
        redirect_uri=None,
        credential_file=None,
        host=None,
        port=443,
        **kwargs,
    ):
        """
        :param  user_id: The email address (for service accounts) or Client ID
                         (for installed apps) to be used for authentication.
        :type   user_id: ``str``

        :param  key: The RSA Key (for service accounts) or file path containing
                     key or Client Secret (for installed apps) to be used for
                     authentication.
        :type   key: ``str``

        :keyword  datacenter: The name of the datacenter (zone) used for
                              operations.
        :type     datacenter: ``str``

        :keyword  project: Your GKE project name. (required)
        :type     project: ``str``

        :keyword  auth_type: Accepted values are "SA" or "IA" or "GKE"
                             ("Service Account" or "Installed Application" or
                             "GKE" if libcloud is being used on a GKE instance
                             with service account enabled).
                             If not supplied, auth_type will be guessed based
                             on value of user_id or if the code is being
                             executed in a GKE instance.
        :type     auth_type: ``str``

        :keyword  scopes: List of authorization URLs. Default is empty and
                          grants read/write to Compute, Storage, DNS.
        :type     scopes: ``list``

        :keyword  credential_file: Path to file for caching authentication
                                   information used by GKEConnection.
        :type     credential_file: ``str``
        """
        if not project:
            raise ValueError(
                "Project name must be specified using " '"project" keyword.'
            )
        if host is None:
            host = GKEContainerDriver.website
        self.auth_type = auth_type
        self.project = project
        self.scopes = scopes
        self.redirect_uri = redirect_uri
        self.zone = None
        if datacenter is not None:
            self.zone = datacenter
        self.credential_file = (
            credential_file
            or GoogleOAuth2Credential.default_credential_file + "." + self.project
        )

        super(GKEContainerDriver, self).__init__(
            user_id, key, secure=True, host=None, port=None, **kwargs
        )

        self.base_path = "/%s/projects/%s" % (API_VERSION, self.project)
        self.website = GKEContainerDriver.website

    def _ex_connection_class_kwargs(self):
        return {
            "auth_type": self.auth_type,
            "project": self.project,
            "scopes": self.scopes,
            "redirect_uri": self.redirect_uri,
            "credential_file": self.credential_file,
        }

    def list_clusters(self, ex_zone="-"):
        """
        Return a list of cluster information in the current zone or all zones.

        :keyword  ex_zone:  Optional zone name or '-'
        :type     ex_zone:  ``str`` or :class:`GCEZone` or
                            :class:`NodeLocation` or '-'

        :rtype: ``list`` of :class:`GKECluster`
        """
        request = "/zones/%s/clusters" % (ex_zone)
        data = self.connection.request(request, method="GET").object
        return self._to_clusters(data)

    def ex_get_cluster(self, zone, name):
        """
        Return cluster information in the given zone

        :keyword  zone:  Zone name
        :type     zone:  ``str``

        :keyword  name:  Cluster name
        :type     name:  ``str``

        :rtype: :class:`GKECluster`
        """
        request = "/zones/%s/clusters/%s" % (zone, name)
        data = self.connection.request(request, method="GET").object
        return self._to_cluster(data)

    def create_cluster(
        self,
        zone: str,
        name: str,
        nodepools: List[Dict],
    ):
        """
        Create cluster in the given zone

        :keyword  zone:  Zone name
        :type     zone:  ``str``

        :keyword  name:  Cluster name
        :type     name:  ``str``

        :keyword  nodepools:  The cluster's node pools.
                              The format is a list of dictionaries with the
                              following structure:
                              [{
                                  node_count: int, The number of nodes
                                  size: str, The name of a GCE machine type
                                  disk_size: int, (optional)Size of the disk attached to nodes
                                  disk_type: str, (optional)Type of the disk attached to nodes
                                  preemptible: bool, (optional)preemptible VM instances
                              }]
        :type     nodepools:  ``list`` of ``dict``

        :return:  A GKE operation dictionary
        :rtype: ``dict``
        """
        request = "/zones/%s/clusters" % (zone)
        body = {
            "cluster": {
                "name": name,
                "nodePools": self._build_nodepools_list(nodepools, name),
            }
        }

        response = self.connection.request(request, method="POST", data=body).object

        return response

    def destroy_cluster(self, zone, name):
        """
        Destroy cluster in the given zone

        :keyword  zone:  Zone name
        :type     zone:  ``str``

        :keyword  name:  Cluster name
        :type     name:  ``str``

        :rtype: :class:`GKECluster`
        """
        request = "/zones/%s/clusters/%s" % (zone, name)

        response = self.connection.request(request, method="DELETE")

        return response.success()

    def get_cluster_credentials(self, cluster, zone=None):
        """
        Return cluster kubernetes credentials

        :keyword  zone:  Zone name (required if cluster is ``str``)
        :type     zone:  ``str``

        :keyword  name:  Cluster name or object
        :type     name:  ``str`` or :class:`GKECluster`

        :rtype: ``dict``
        """
        if isinstance(cluster, str):
            cluster = self.ex_get_cluster(zone, cluster)
        return cluster.credentials

    def get_server_config(self, ex_zone):
        """
        Return configuration info about the Container Engine service.

        :keyword  ex_zone:  Zone name
        :type     ex_zone:  ``str``
        """
        request = "/zones/%s/serverconfig" % (ex_zone)
        response = self.connection.request(request, method="GET").object
        return response

    def ex_scale_nodepool(
        self,
        cluster: Union[GKECluster, str],
        nodepool: Union[GKENodePool, str],
        zone: str,
        desired_nodes: int,
    ) -> GKEOperation:
        """Set the node count for a specific nodepool.

        :param cluster: The cluster the nodepool belongs to.
        :type  cluster: :class: `GKECluster` or ``str``

        :param nodepool: The nodepool to scale.
        :type  nodepool: :class: `GKENodePool` or ``str``

        :param zone: The zone in which the cluster resides.
        :type  zone: ``str``

        :param desired_nodes:  The desired node count for the pool.
        :type  desired_nodes: ``int``

        :rtype: :class:`GKEOperation`
        """
        try:
            cluster_name = cluster.name
        except AttributeError:
            cluster_name = cluster

        try:
            nodepool_name = nodepool.name
        except AttributeError:
            nodepool_name = nodepool

        path = (
            f"/zones/{zone}/clusters/{cluster_name}/nodePools/{nodepool_name}/setSize"
        )

        data = {
            "nodeCount": desired_nodes,
        }

        response = self.connection.request(path, method="POST", data=data).object
        return self._to_operation(response)

    def ex_set_nodepool_autoscaling(
        self,
        cluster: Union[GKECluster, str],
        nodepool: Union[GKENodePool, str],
        zone: str,
        autoscaling: bool = True,
        min_nodes: Optional[int] = None,
        max_nodes: Optional[int] = None,
    ):
        """Set the autoscaling settings for the specified node pool.

        :param cluster: The cluster the nodepool belongs to.
        :type  cluster: :class: `GKECluster` or ``str``

        :param nodepool: The nodepool to scale.
        :type  nodepool: :class: `GKENodePool` or ``str``

        :param zone: The zone in which the cluster resides.
        :type  zone: ``str``

        :keyword autoscaling:  Enable/Disable autoscaling
        :type  autoscaling: ``bool``

        :keyword min_nodes:  The desired node count for the pool. Required when enabled is True
        :type  min_nodes: ``int``

        :keyword max_nodes:  The desired node count for the pool. Required when enabled is True
        :type  max_nodes: ``int``

        :rtype: :class:`GKEOperation`
        """
        try:
            cluster_name = cluster.name
        except AttributeError:
            cluster_name = cluster

        try:
            nodepool_name = nodepool.name
        except AttributeError:
            nodepool_name = nodepool

        data = {
            "autoscaling": {
                "enabled": autoscaling,
            }
        }

        if autoscaling:
            data["autoscaling"]["minNodeCount"] = min_nodes
            data["autoscaling"]["maxNodeCount"] = max_nodes

        path = f"/zones/{zone}/clusters/{cluster_name}/nodePools/{nodepool_name}/autoscaling"

        response = self.connection.request(path, method="POST", data=data).object

        return self._to_operation(response)

    def ex_get_operation(self, name: str, zone: str) -> GKEOperation:
        """Return details about a cluster operation.

        :param name: The name of the operation.
        :type  name: ``str``

        :param zone: The zone in which the cluster resides.
        :type  zone: ``str``
        """

        response = self.connection.request(f"/zones/{zone}/operations/{name}").object

        return self._to_operation(response)

    def _to_operation(self, data):
        name = data["name"]
        location = data["zone"]
        status = data["status"]
        type_ = data["operationType"]
        return GKEOperation(name=name, location=location, type=type_, status=status)

    def _to_nodepool(self, data):
        name = data["name"]
        state = data["status"]
        size = data["config"]["machineType"]
        locations = data["locations"]
        nodes = data.get("initialNodeCount", 0)
        try:
            min_nodes = data["autoscaling"]["minNodeCount"]
        except (KeyError, TypeError):
            min_nodes = None
        try:
            max_nodes = data["autoscaling"]["maxNodeCount"]
        except (KeyError, TypeError):
            max_nodes = None
        extra = {
            "config": data.get("config"),
            "network_config": data.get("networkConfig"),
            "upgrade_settings": data.get("upgradeSettings"),
            "version": data.get("version"),
            "instance_group_urls": data.get("instanceGroupUrls"),
            "management": data.get("management"),
            "max_pods_constraint": data.get("maxPodsConstraint"),
            "autoscaling": data.get("autoscaling"),
            "pod_ipv4_cidr_size": data.get("podIpv4CidrSize"),
            "conditions": data.get("conditions"),
        }
        return GKENodePool(
            name=name,
            state=state,
            size=size,
            locations=locations,
            nodes=nodes,
            min_nodes=min_nodes,
            max_nodes=max_nodes,
            extra=extra,
        )

    def _to_clusters(self, data):
        return [self._to_cluster(c) for c in data.get("clusters", [])]

    def _to_cluster(self, data):
        try:
            status = self.CLUSTER_STATES[data.pop("status")]
        except KeyError:
            status = ClusterState.UNKNOWN

        # When the Kubernetes API is not up endpoint might not exist
        host = data.get("endpoint", "")
        port = "443"
        token = self.connection.oauth2_credential.access_token
        token_expiry = self.connection.oauth2_credential.token_expire_utc_datetime
        ca_cert = base64.b64decode(data["masterAuth"]["clusterCaCertificate"]).decode(
            "utf-8"
        )
        nodepools = [self._to_nodepool(item) for item in data.get("nodePools", [])]

        cluster = GKECluster(
            id=data.pop("id"),
            name=data.pop("name"),
            node_count=data.pop("currentNodeCount", 0),
            location=data.pop("location"),
            nodepools=nodepools,
            status=status,
            host=host,
            port=port,
            token=token,
            token_expiry=token_expiry,
            ca_cert=ca_cert,
            config={
                k: data.pop(k)
                for k in list(data)
                if k
                in [
                    "initialNodeCount",
                    "nodeConfig",
                    "addonsConfig",
                    "legacyAbac",
                    "networkPolicy",
                    "ipAllocationPolicy",
                    "masterAuthorizedNetworksConfig",
                    "binaryAuthorization",
                    "autoscaling",
                    "networkConfig",
                    "resourceUsageExportConfig",
                    "authenticatorGroupsConfig",
                    "privateClusterConfig",
                    "databaseEncryption",
                    "verticalPodAutoscaling",
                    "shieldedNodes",
                    "workloadIdentityConfig",
                ]
            },
            extra=data,
            total_cpus=0,
            total_memory=0,
        )

        if cluster.driver:
            try:
                cluster_nodes = cluster.driver.ex_list_nodes()
            except Exception:
                cluster.extra["nodes"] = []
                cluster.total_cpus = 0
                cluster.total_memory = 0
            else:
                cluster.extra["node_ids"] = [
                    node.extra["provider_id"] for node in cluster_nodes
                ]
                for n in cluster_nodes:
                    cluster.total_cpus += int(n.extra["cpu"])
                    cluster.total_memory += int(
                        to_memory_str(to_n_bytes(n.extra["memory"]), unit="G").strip(
                            "G"
                        )
                    )
        return cluster

    def _build_nodepools_list(self, nodepools, cluster_name):
        """Helper method to convert a list of Nodepool dictionaries
        to the format expected by the GKE API.
        """
        gke_nodepools = []
        for index, nodepool in enumerate(nodepools):
            disk_size = nodepool.get("disk_size", 100)
            disk_type = nodepool.get("disk_type", "pd-standard")
            preemptible = nodepool.get("preemptible", False)
            gke_nodepools.append(
                {
                    "name": f"{cluster_name}-pool-{index}",
                    "initialNodeCount": nodepool["node_count"],
                    "config": {
                        "machineType": nodepool["size"],
                        "diskSizeGb": disk_size,
                        "preemptible": preemptible,
                        "diskType": disk_type,
                    },
                }
            )
        return gke_nodepools
