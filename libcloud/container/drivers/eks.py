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
import re
import base64
import tempfile
from typing import List, Optional, Union, Any, Dict

try:
    import simplejson as json
except ImportError:
    import json

from libcloud.container.base import ContainerDriver, ContainerCluster, ClusterState
from libcloud.container.drivers.kubernetes import KubernetesContainerDriver
from libcloud.common.aws import SignedAWSConnection, AWSJsonResponse
from libcloud.common.exceptions import BaseHTTPError
from libcloud.utils.misc import to_memory_str
from libcloud.utils.misc import to_n_bytes

__all__ = ["ElasticKubernetesDriver"]


EKS_VERSION = "2017-11-01"
EKS_HOST = "eks.%s.amazonaws.com"
STS_HOST = "sts.%s.amazonaws.com"
ROOT = "/"
CLUSTERS_ENDPOINT = ROOT + "clusters/"


class EKSCluster(ContainerCluster):
    def __init__(
        self,
        id,
        name,
        location,
        config,
        status,
        host,
        port,
        token,
        ca_cert,
        extra=None,
        total_cpus=None,
        total_memory=None,
    ):
        self.location = location
        self.status = status
        self.config = config
        self.credentials = {
            "host": host,
            "port": port,
            "token": token,
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
        self.total_cpus = total_cpus or 0
        self.total_memory = total_memory or 0

    def __del__(self):
        try:
            os.remove(self._cert_file_path)
        except FileNotFoundError:
            ...


class EKSNodeGroup:
    """A class representing an Amazon EKS managed node group."""

    def __init__(
        self,
        id_: str,
        name: str,
        state: str,
        cluster_name: str,
        sizes: List[str],
        scaling_config: Dict[str, int],
        extra: Optional[Dict[str, Any]] = None,
    ):
        self.id = id_
        self.name = name
        self.state = state
        self.cluster_name = cluster_name
        self.scaling_config = scaling_config
        self.sizes = sizes
        self.extra = extra or {}

    def __repr__(self):
        return ("<EKSNodeGroup: name=%s, state=%s, cluster=%s ...>") % (
            self.name,
            self.state,
            self.cluster_name,
        )


class EKSUpdate:
    """Represent an update against a cluster."""

    def __init__(
        self,
        id: str,
        status: str,
        type: str,
        errors: List[Dict[str, Any]],
        extra: Optional[Dict[Any, Any]] = None,
    ):
        self.id = id
        self.status = status
        self.type = type
        self.errors = errors
        self.extra = extra or {}

    def __repr__(self):
        return ("<EKSUpdate: id=%s, type=%s, status=%s ...>") % (
            self.id,
            self.type,
            self.status,
        )


class EKSJsonConnection(SignedAWSConnection):
    version = EKS_VERSION
    host = EKS_HOST
    responseCls = AWSJsonResponse
    service_name = "eks"


class ElasticKubernetesDriver(ContainerDriver):
    name = "Amazon Elastic Kubernetes Service"
    website = "https://aws.amazon.com/eks/"
    connectionCls = EKSJsonConnection
    supports_clusters = True

    CLUSTER_STATES = {
        "CREATING": ClusterState.STARTING,
        "ACTIVE": ClusterState.RUNNING,
        "DELETING": ClusterState.STOPPING,
        "FAILED": ClusterState.ERROR,
        "UPDATING": ClusterState.UPDATING,
        "PENDING": ClusterState.PENDING,
    }

    def __init__(self, access_id, secret, region):
        super().__init__(access_id, secret, host=EKS_HOST % (region))
        self.region = region
        self.region_name = region

    def _ex_connection_class_kwargs(self):
        return {"signature_version": "4"}

    def list_clusters(self):
        """
        Get a list of clusters

        :rtype: ``list`` of :class:`EKSCluster`
        """
        names = self.connection.request(CLUSTERS_ENDPOINT).object["clusters"]
        clusters = [self.get_cluster(name) for name in names]
        return clusters

    def get_cluster(self, name, fetch_nodes=True):
        """
        Get a cluster description

        :param  name: The name of the cluster
        :type   name: ``str``

        :rtype: :class:`EKSCluster`
        """
        endpoint = "{endpoint}{name}".format(endpoint=CLUSTERS_ENDPOINT, name=name)
        data = self.connection.request(endpoint).object
        return self._to_cluster(data["cluster"], fetch_nodes=fetch_nodes)

    def create_cluster(
        self,
        name: str,
        role_arn: str,
        vpc_id: str,
        subnet_ids: List[str],
        security_group_ids: List[str],
        version: str = "1.21",
        endpoint_public_access: bool = True,
        endpoint_private_access: bool = False,
        ip_family: str = "ipv4",
    ) -> EKSCluster:
        """
        Create a cluster

        :param  name: The name of the cluster
        :type   name: ``str``

        :param role_arn: The Amazon Resource Name (ARN) of the IAM role that
                         provides permissions for the Kubernetes control plane
                         to make calls to AWS API operations on your behalf
        :type role_arn: ``str``

        :param vpc_id: The VPC associated with the cluster
        :type vpc_id: ``str``

        :param subnet_ids: The subnets associated with the cluster
        :type subnet_ids: ``list`` of ``str``

        :param security_group_ids: The security groups associated with the
                                   cross-account elastic network interfaces
                                   that are used to allow communication
                                   between your nodes and the Kubernetes
                                   control plane
        :type security_group_ids: ``list`` of ``str``

        :keyword version: The desired Kubernetes version for the cluster.
        :type version: ``str``

        :keyword endpoint_public_access: Whether the Amazon EKS public API server
                                         endpoint will be enabled.
        :type endpoint_public_access: ``bool``

        :keyword endpoint_private_access: Whether the Amazon EKS private API server
                                          endpoint will be enabled.
        :type endpoint_private_access: ``bool``

        :keyword ip_family: The IP family used to assign Kubernetes pod and service
                            IP addresses (ipv4 | ipv6).
        :type ip_family: ``str``

        :rtype: :class:`EKSCluster`
        """
        request = {
            "name": name,
            "version": version,
            "roleArn": role_arn,
            "resourcesVpcConfig": {
                "vpcId": vpc_id,
                "subnetIds": subnet_ids,
                "securityGroudIds": security_group_ids,
                "endpointPublicAccess": endpoint_public_access,
                "endpointPrivateAccess": endpoint_private_access,
            },
            "kubernetesNetworkConfig": {"ipFamily": ip_family},
        }
        response = self.connection.request(
            CLUSTERS_ENDPOINT, method="POST", data=json.dumps(request)
        ).object
        return self._to_cluster(response["cluster"], fetch_nodes=False)

    def destroy_cluster(self, name) -> bool:
        """
        Destroy a cluster

        :param  name: The name of the cluster
        :type   name: ``str``

        :return: ``True`` if the destroy was successful
        :rtype: ``bool``
        """
        endpoint = "{endpoint}{name}".format(endpoint=CLUSTERS_ENDPOINT, name=name)

        response = self.connection.request(endpoint, method="DELETE")

        return response.success()

    def get_cluster_credentials(self, cluster) -> Dict:
        """
        Return cluster kubernetes credentials

        :param  name:  Cluster name or object
        :type     name:  ``str`` or :class:`EKSCluster`

        :rtype: ``dict``
        """
        if isinstance(cluster, str):
            cluster = self.get_cluster(cluster)
        host, port = cluster.extra["endpoint"], "443"
        token = self._get_cluster_token(cluster.name)
        credentials = dict(host=host, port=port, token=token)
        return credentials

    def ex_list_nodegroups(self, cluster: Union[EKSCluster, str]) -> List[str]:
        """List node groups associated with the specified cluster.

        :param  cluster: The cluster to list node groups for.
        :type   cluster: :class: `EKSCluster` or ``str``

        :return: A list of the nodegroups names
        :rtype: ``list`` of ``str``
        """
        try:
            cluster_name = cluster.name
        except AttributeError:
            cluster_name = cluster

        response = self.connection.request(
            f"{CLUSTERS_ENDPOINT}{cluster_name}/node-groups",
        ).object

        return response["nodegroups"]

    def ex_get_nodegroup(
        self, cluster: Union[EKSCluster, str], name: str
    ) -> EKSNodeGroup:
        """Return detailed information about a node group.

        :param  cluster: The cluster the node group belongs to.
        :type   cluster: :class: `EKSCluster` or ``str``

        :param  name: The name of the nodegroup to describe.
        :type   name: ``str``

        :rtype: :class:`EKSNodeGroup`
        """
        try:
            cluster_name = cluster.name
        except AttributeError:
            cluster_name = cluster

        response = self.connection.request(
            f"{CLUSTERS_ENDPOINT}{cluster_name}/node-groups/{name}",
        ).object

        return self._to_nodegroup(response["nodegroup"])

    def ex_create_node_group(
        self,
        cluster: Union[EKSCluster, str],
        name: str,
        role_arn: str,
        subnet_ids: List[str],
        capacity_type: str = "ON_DEMAND",
        node_group_disk_size: int = 20,
        instance_types: Optional[List[str]] = None,
        ami_type: str = "AL2_x86_64",
        desired_nodes: int = 2,
        max_nodes: int = 2,
        min_nodes: int = 2,
        max_unavailable_nodes: int = 1,
    ) -> EKSNodeGroup:
        """Create a managed node group for a cluster.

        :param  cluster: The cluster to create the node group for.
        :type   cluster: :class: `EKSCluster` or ``str``

        :param  name: The name to give to the node group.
        :type   name: ``str``

        :param  role_arn: The ARN of the IAM role to associate with the node group.
        :type   role_arn: ``str``

        :param  subnet_ids: The subnets to use for the auto scaling group
                            that is created for the node group.
        :type   subnet_ids: ``list`` of ``str``

        :keyword capacity_type: The capacity type of the managed node group (ON_DEMAND | SPOT).
        :type    capacity_type: ``str``

        :keyword node_group_disk_size: The disk size for the node group.
        :type    node_group_disk_size: ``int``

        :keyword instance_types: the instance type that is associated with the node group.
        :type    instance_types: ``list`` of ``str``

        :keyword ami_type: The AMI type for your node group.
        :type    ami_type: ``str``

        :keyword desired_nodes: The current number of nodes that the managed node group
                                should maintain.
        :type    desired_nodes: ``int``

        :keyword max_nodes: The maximum number of nodes that the managed node group
                            can scale out to.
        :type    max_nodes: ``int``

        :keyword min_nodes: The disk size for the node group.
        :type    min_nodes: ``int``

        :keyword max_unavailable_nodes: The maximum number of nodes unavailable at once.
        :type    max_unavailable_nodes: ``int``

        :rtype: :class:`EKSNodeGroup`
        """
        try:
            cluster_name = cluster.name
        except AttributeError:
            cluster_name = cluster

        data = {
            "amiType": ami_type,
            "capacityType": capacity_type,
            "diskSize": node_group_disk_size,
            "nodegroupName": name,
            "nodeRole": role_arn,
            "subnets": subnet_ids,
            "scalingConfig": {
                "desiredSize": desired_nodes,
                "maxSize": max_nodes,
                "minSize": min_nodes,
            },
            "updateConfig": {
                "maxUnavailable": max_unavailable_nodes,
            },
        }

        if instance_types:
            data["instanceTypes"] = list(instance_types)

        response = self.connection.request(
            f"{CLUSTERS_ENDPOINT}{cluster_name}/node-groups",
            method="POST",
            data=json.dumps(data),
        ).object

        return self._to_nodegroup(response["nodegroup"])

    def ex_scale_nodegroup(
        self,
        cluster: Union[EKSCluster, str],
        nodegroup: Union[EKSNodeGroup, str],
        desired_nodes: int,
        min_nodes: Optional[int] = None,
        max_nodes: Optional[int] = None,
    ) -> str:
        """Scale the nodegroup up or down.

        :param  cluster: The cluster the node group belongs to.
        :type   cluster: :class: `EKSCluster` or ``str``

        :param  nodegroup: The name of the nodegroup to scale.
        :type   nodegroup: :class: `EKSNodeGroup` or ``str``

        :param  desired_nodes: The number of nodes that the managed node group should maintain.
        :type   desired_nodes: ``int``

        :keyword  min_nodes: The minimum number of nodes that the managed node group can scale.
                             If left unspecified, the value will be set to `desired_nodes`
        :type     min_nodes: ``int``

        :keyword  max_nodes: The maximum number of nodes that the managed node group can scale.
                             If left unspecified, the value will be set to `desired_nodes`
        :type     max_nodes: ``int``

        :return: An update ID
        :rtype: `str`
        """
        try:
            cluster_name = cluster.name
        except AttributeError:
            cluster_name = cluster

        try:
            nodegroup_name = nodegroup.name
        except AttributeError:
            nodegroup_name = nodegroup

        data = {
            "scalingConfig": {
                "desiredSize": desired_nodes,
                "maxSize": max_nodes or desired_nodes,
                "minSize": min_nodes or desired_nodes,
            },
        }

        response = self.connection.request(
            f"{CLUSTERS_ENDPOINT}{cluster_name}/node-groups/{nodegroup_name}/update-config",
            method="POST",
            data=json.dumps(data),
        ).object

        return response["update"]["id"]

    def ex_get_update(
        self,
        cluster: Union[EKSCluster, str],
        update_id: str,
        addon_name: Optional[str] = None,
        nodegroup: Optional[Union[EKSNodeGroup, str]] = None,
    ) -> EKSUpdate:
        """Returns detailed information about an update against the specified cluster or
        associated managed node group or EKS add-on.

        :param  cluster: The name of the cluster associated with the update.
        :type   cluster: :class: `EKSCluster` or ``str``

        :param  update_id: The ID of the update to describe.
        :type   update_id: ``str``

        :keyword addon_name: The name of the add-on, required if the update is an add-on update.
        :type    addon_name: ``str``

        :keyword nodegroup: The name of the nodegroup associated with the update,
                            required if the update is a node group update.
        :type    nodegroup: :class: `EKSNodeGroup` or ``str``

        :rtype: :class:`EKSUpdate`
        """
        params = {}
        if addon_name:
            params["addonName"] = addon_name

        if nodegroup:
            try:
                params["nodegroupName"] = nodegroup.name
            except AttributeError:
                params["nodegroupName"] = nodegroup

        try:
            name = cluster.name
        except AttributeError:
            name = cluster

        response = self.connection.request(
            f"{CLUSTERS_ENDPOINT}{name}/updates/{update_id}",
            params=params,
        ).object

        return self._to_update(response["update"])

    def ex_list_addons(
        self,
        cluster: Union[EKSCluster, str],
    ) -> List[str]:
        """Lists the available add-ons for the cluster.

        :param  cluster: The name of the cluster.
        :type   cluster: :class: `EKSCluster` or ``str``

        :rtype: ``list`` of ``str``
        """
        try:
            name = cluster.name
        except AttributeError:
            name = cluster

        response = self.connection.request(
            f"{CLUSTERS_ENDPOINT}{name}/addons",
        ).object

        return response["addons"]

    def _to_update(self, data):
        id_ = data["id"]
        status = data["status"]
        type_ = data["type"]
        errors = data["errors"]
        extra = {
            "created_at": data["createdAt"],
            "params": data["params"],
        }
        return EKSUpdate(id=id_, status=status, type=type_, errors=errors, extra=extra)

    def _to_nodegroup(self, data):
        id_ = data["nodegroupArn"]
        name = data["nodegroupName"]
        state = data["status"]
        cluster_name = data["clusterName"]
        sizes = data["instanceTypes"]
        scaling_config = data["scalingConfig"]

        extra = {
            "version": data.get("version"),
            "release_version": data.get("releaseVersion"),
            "created_at": data.get("createdAt"),
            "modified_at": data.get("modified_at"),
            "capacity_type": data.get("capacityType"),
            "subnets": data.get("subnets"),
            "remote_access": data.get("remoteAccess"),
            "ami_type": data.get("amiType"),
            "node_role": data.get("nodeRole"),
            "labels": data.get("labels"),
            "taints": data.get("taints"),
            "resources": data.get("resources"),
            "disk_size": data.get("diskSize"),
            "health": data.get("health"),
            "update_config": data.get("updateConfig"),
            "launch_template": data.get("launchTemplate"),
            "tags": data.get("tags"),
        }

        return EKSNodeGroup(
            id_=id_,
            name=name,
            state=state,
            cluster_name=cluster_name,
            sizes=sizes,
            scaling_config=scaling_config,
            extra=extra,
        )

    def _get_cluster_token(self, cluster_name):
        host = STS_HOST % (self.region)
        url = (
            "https://{host}".format(host=host)
            + "/?Action=GetCallerIdentity&Version=2011-06-15"
        )
        params = {
            "method": "GET",
            "url": url,
            "body": {},
            "headers": {"x-k8s-aws-id": cluster_name},
            "context": {},
        }
        signed_url = self.connection.signer.generate_sts_presigned_url(
            params=params, host=host
        )
        base64_url = base64.urlsafe_b64encode(signed_url.encode("utf-8")).decode(
            "utf-8"
        )
        return "k8s-aws-v1." + re.sub(r"=*", "", base64_url)

    def _to_cluster(self, data, fetch_nodes=True):
        id_ = data["arn"]
        name = data["name"]
        endpoint = data.get("endpoint", "")
        ca_cert = base64.b64decode(data["certificateAuthority"]["data"]).decode("utf-8")
        try:
            status = self.CLUSTER_STATES[data["status"]]
        except KeyError:
            status = ClusterState.UNKNOWN

        config = {
            "resourcesVpcConfig": data.get("resourcesVpcConfig"),
            "kubernetesNetworkConfig": data.get("kubernetesNetworkConfig"),
            "encryptionConfig": data.get("encryptionConfig"),
            "connectorConfig": data.get("connectorConfig"),
        }

        extra = {
            "createdAt": data["createdAt"],
            "version": data["version"],
            "endpoint": endpoint,
            "roleArn": data["roleArn"],
            "logging": data["logging"],
            "identity": data["identity"],
            "certificateAuthority": data["certificateAuthority"],
            "clientRequestToken": data["clientRequestToken"],
            "platformVersion": data["platformVersion"],
            "tags": data["tags"],
        }

        cluster = EKSCluster(
            id=id_,
            name=name,
            location=self.region,
            config=config,
            status=status,
            host=endpoint,
            port="443",
            token=self._get_cluster_token(name),
            ca_cert=ca_cert,
            extra=extra,
        )

        if fetch_nodes:
            try:
                cluster_nodes = cluster.driver.ex_list_nodes()
            except Exception:
                cluster.extra["nodes"] = []
                cluster.total_cpus = 0
                cluster.total_memory = 0
            else:
                cluster.extra["nodes"] = [
                    {
                        "id": node.id,
                        "name": node.name,
                        "provider_id": node.extra["provider_id"],
                    }
                    for node in cluster_nodes
                ]
                for n in cluster_nodes:
                    cluster.total_cpus += int(n.extra["cpu"])
                    cluster.total_memory += int(
                        to_memory_str(to_n_bytes(n.extra["memory"]), unit="G").strip(
                            "G"
                        )
                    )
        return cluster
