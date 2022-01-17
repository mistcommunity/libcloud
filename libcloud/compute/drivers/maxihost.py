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

import json
import re
from typing import Optional, List, Dict, Union, Any

from libcloud.compute.base import Node, NodeDriver, NodeLocation
from libcloud.compute.base import NodeSize, NodeImage
from libcloud.compute.base import KeyPair
from libcloud.compute.types import Provider, NodeState
from libcloud.common.exceptions import BaseHTTPError
from libcloud.utils.py3 import httplib
from libcloud.common.maxihost import MaxihostConnection
from libcloud.common.maxihost import DEFAULT_API_VERSION
from libcloud.common.maxihost import MaxihostConnectionV2
from libcloud.common.maxihost import MaxihostProject

__all__ = ["MaxihostNodeDriver"]


class MaxihostNodeDriver(NodeDriver):
    """
    Base Maxihost node driver.
    """

    type = Provider.MAXIHOST
    name = "Maxihost"
    website = "https://www.maxihost.com/"

    def __new__(
        cls,
        key,
        secret=None,
        secure=True,
        host=None,
        port=None,
        api_version=DEFAULT_API_VERSION,
        region=None,
        **kwargs,
    ):
        if cls is MaxihostNodeDriver:
            if api_version == "1":
                cls = MaxihostNodeDriverV1
            elif api_version == "2":
                cls = MaxihostNodeDriverV2
            else:
                raise NotImplementedError(
                    "No Vultr driver found for API version: %s" % (api_version)
                )
        return super().__new__(cls)


class MaxihostNodeDriverV1(MaxihostNodeDriver):
    connectionCls = MaxihostConnection

    def create_node(self, name, size, image, location, ex_ssh_key_ids=None):
        """
        Create a node.

        :return: The newly created node.
        :rtype: :class:`Node`
        """
        attr = {
            "hostname": name,
            "plan": size.id,
            "operating_system": image.id,
            "facility": location.id.lower(),
            "billing_cycle": "monthly",
        }

        if ex_ssh_key_ids:
            attr["ssh_keys"] = ex_ssh_key_ids

        try:
            res = self.connection.request("/devices", params=attr, method="POST")
        except BaseHTTPError as exc:
            error_message = exc.message.get("error_messages", "")
            raise ValueError("Failed to create node: %s" % (error_message))

        return self._to_node(res.object["devices"][0])

    def start_node(self, node):
        """
        Start a node.
        """
        params = {"type": "power_on"}
        res = self.connection.request(
            "/devices/%s/actions" % node.id, params=params, method="PUT"
        )

        return res.status in [httplib.OK, httplib.CREATED, httplib.ACCEPTED]

    def stop_node(self, node):
        """
        Stop a node.
        """
        params = {"type": "power_off"}
        res = self.connection.request(
            "/devices/%s/actions" % node.id, params=params, method="PUT"
        )

        return res.status in [httplib.OK, httplib.CREATED, httplib.ACCEPTED]

    def destroy_node(self, node):
        """
        Destroy a node.
        """
        res = self.connection.request("/devices/%s" % node.id, method="DELETE")

        return res.status in [httplib.OK, httplib.CREATED, httplib.ACCEPTED]

    def reboot_node(self, node):
        """
        Reboot a node.
        """
        params = {"type": "power_cycle"}
        res = self.connection.request(
            "/devices/%s/actions" % node.id, params=params, method="PUT"
        )

        return res.status in [httplib.OK, httplib.CREATED, httplib.ACCEPTED]

    def list_nodes(self):
        """
        List nodes

        :rtype: ``list`` of :class:`MaxihostNode`
        """
        response = self.connection.request("/devices")
        nodes = [self._to_node(host) for host in response.object["devices"]]
        return nodes

    def _to_node(self, data):
        extra = {}
        private_ips = []
        public_ips = []
        for ip in data["ips"]:
            if "Private" in ip["ip_description"]:
                private_ips.append(ip["ip_address"])
            else:
                public_ips.append(ip["ip_address"])

        if data["power_status"]:
            state = NodeState.RUNNING
        else:
            state = NodeState.STOPPED

        for key in data:
            extra[key] = data[key]

        node = Node(
            id=data["id"],
            name=data["description"],
            state=state,
            private_ips=private_ips,
            public_ips=public_ips,
            driver=self,
            extra=extra,
        )
        return node

    def list_locations(self, ex_available=True):
        """
        List locations

        If ex_available is True, show only locations which are available
        """
        locations = []
        data = self.connection.request("/regions")
        for location in data.object["regions"]:
            if ex_available:
                if location.get("available"):
                    locations.append(self._to_location(location))
            else:
                locations.append(self._to_location(location))
        return locations

    def _to_location(self, data):
        name = data.get("location").get("city", "")
        country = data.get("location").get("country", "")
        return NodeLocation(id=data["slug"], name=name, country=country, driver=self)

    def list_sizes(self):
        """
        List sizes
        """
        sizes = []
        data = self.connection.request("/plans")
        for size in data.object["servers"]:
            sizes.append(self._to_size(size))
        return sizes

    def _to_size(self, data):
        extra = {
            "specs": data["specs"],
            "regions": data["regions"],
            "pricing": data["pricing"],
        }
        ram = data["specs"]["memory"]["total"]
        ram = re.sub("[^0-9]", "", ram)
        return NodeSize(
            id=data["slug"],
            name=data["name"],
            ram=int(ram),
            disk=None,
            bandwidth=None,
            price=data["pricing"]["usd_month"],
            driver=self,
            extra=extra,
        )

    def list_images(self):
        """
        List images
        """
        images = []
        data = self.connection.request("/plans/operating-systems")
        for image in data.object["operating-systems"]:
            images.append(self._to_image(image))
        return images

    def _to_image(self, data):
        extra = {
            "operating_system": data["operating_system"],
            "distro": data["distro"],
            "version": data["version"],
            "pricing": data["pricing"],
        }
        return NodeImage(id=data["slug"], name=data["name"], driver=self, extra=extra)

    def list_key_pairs(self):
        """
        List all the available SSH keys.

        :return: Available SSH keys.
        :rtype: ``list`` of :class:`KeyPair`
        """
        data = self.connection.request("/account/keys")
        return list(map(self._to_key_pair, data.object["ssh_keys"]))

    def create_key_pair(self, name, public_key):
        """
        Create a new SSH key.

        :param      name: Key name (required)
        :type       name: ``str``

        :param      public_key: base64 encoded public key string (required)
        :type       public_key: ``str``
        """
        attr = {"name": name, "public_key": public_key}
        res = self.connection.request(
            "/account/keys", method="POST", data=json.dumps(attr)
        )

        data = res.object["ssh_key"]

        return self._to_key_pair(data=data)

    def _to_key_pair(self, data):
        extra = {"id": data["id"]}
        return KeyPair(
            name=data["name"],
            fingerprint=data["fingerprint"],
            public_key=data["public_key"],
            private_key=None,
            driver=self,
            extra=extra,
        )

    def ex_start_node(self, node):
        # NOTE: This method is here for backward compatibility reasons after
        # this method was promoted to be part of the standard compute API in
        # Libcloud v2.7.0
        return self.start_node(node=node)

    def ex_stop_node(self, node):
        # NOTE: This method is here for backward compatibility reasons after
        # this method was promoted to be part of the standard compute API in
        # Libcloud v2.7.0
        return self.stop_node(node=node)


class MaxihostNodeDriverV2(MaxihostNodeDriver):
    connectionCls = MaxihostConnectionV2

    def list_sizes(self) -> List[NodeSize]:
        """List available node sizes.

        :rtype: ``list`` of :class: `NodeSize`
        """
        data = self.connection.request("/plans").object
        return [self._to_size(item) for item in data["data"]]

    def list_images(self) -> List[NodeImage]:
        """List available node images.

        :rtype: ``list`` of :class: `NodeImage`
        """
        data = self.connection.request("/plans/operating_systems").object
        return [self._to_image(item) for item in data["data"]]

    def list_locations(self) -> List[NodeLocation]:
        """List available node locations.

        :rtype: ``list`` of :class: `NodeLocation`
        """
        data = self.connection.request("/regions").object
        return [self._to_location(item) for item in data["data"]]

    def list_key_pairs(
        self, ex_project: Union[MaxihostProject, str, None] = None
    ) -> List[KeyPair]:
        """
        List all the  key pair objects for a project or all projects.

        :keyword ex_project: The project to list key pairs for, if not provided key pairs
                             for all projects will be listed
        :type    ex_project: :class: `MaxihostProject` or ``str`` or ``None``

        :rtype: ``list`` of :class:`.KeyPair` objects
        """
        if ex_project:
            try:
                projects = [ex_project.id]
            except AttributeError:
                projects = [ex_project]
        else:
            projects = [project.id for project in self.ex_list_projects()]

        key_pairs = []
        for project in projects:
            data = self.connection.request("/projects/%s/ssh_keys" % project).object
            key_pairs += [self._to_key_pair(item, project) for item in data["data"]]
        return key_pairs

    def import_key_pair_from_string(
        self, name: str, key_material: str, ex_project: Union[MaxihostProject, str]
    ) -> KeyPair:
        """
        Import a new public key from string.

        :param name: Key pair name.
        :type name: ``str``

        :param key_material: Public key material.
        :type key_material: ``str``

        :param ex_project: The key pair will be created under this project.
        :type ex_project: :class: `MaxihostProject` or ``str``

        :rtype: :class:`.KeyPair` object
        """
        try:
            project = ex_project.id
        except AttributeError:
            project = ex_project

        data = {
            "data": {
                "attributes": {"name": name, "public_key": key_material},
                "type": "ssh_keys",
            }
        }
        response = self.connection.request(
            "/projects/%s/ssh_keys" % project, data=json.dumps(data), method="POST"
        )

        return self._to_key_pair(response.object["data"], project)

    def delete_key_pair(self, key_pair: KeyPair) -> bool:
        """
        Delete an existing key pair.

        :param key_pair: Key pair object.
        :type key_pair: :class:`.KeyPair`

        :param ex_project: The project the key pair belongs.
        :type ex_project: :class: `MaxihostProject` or ``str``

        :rtype: ``bool``
        """

        response = self.connection.request(
            "/projects/%s/ssh_keys/%s"
            % (key_pair.extra["project_id"], key_pair.extra["id"]),
            method="DELETE",
        )
        return response.success()

    def ex_list_projects(self) -> List[MaxihostProject]:
        """List all available Maxihost projects

        :rtype: ``list`` of :class:`MaxihostProject` objects
        """
        data = self.connection.request("/projects").object
        return [self._to_project(item) for item in data["data"]]

    def _to_key_pair(self, data: Dict[str, Any], project_id: str) -> KeyPair:
        name = data["attributes"]["name"]
        public_key = data["attributes"]["name"]
        fingerprint = data["attributes"]["fingerprint"]
        extra = {
            "id": data["id"],
            "created_at": data["attributes"]["created_at"],
            "updated_at": data["attributes"]["updated_at"],
            "project_id": project_id,
        }

        return KeyPair(
            name=name,
            public_key=public_key,
            fingerprint=fingerprint,
            driver=self,
            extra=extra,
        )

    def _to_project(self, data: Dict[str, Any]) -> MaxihostProject:
        id_ = data["id"]
        name = data["attributes"]["name"]
        environment = data["attributes"]["environment"]
        extra = {
            "slug": data["attributes"]["slug"],
            "description": data["attributes"]["description"],
            "billing_type": data["attributes"]["billing_type"],
            "billing_method": data["attributes"]["billing_method"],
            "stats": data["attributes"]["stats"],
            "created_at": data["attributes"]["created_at"],
            "updated_at": data["attributes"]["updated_at"],
            "relationships": data["relationships"],
        }
        return MaxihostProject(id=id_, name=name, environment=environment, extra=extra)

    def _to_location(self, data: Dict[str, Any]) -> NodeLocation:
        id_ = data["id"]
        name = data["attributes"]["name"]
        country = data["attributes"]["country"]["name"]
        extra = {
            "slug": data["attributes"]["slug"],
            "facility": data["attributes"]["facility"],
            "type": data["attributes"]["type"],
        }
        return NodeLocation(
            id=id_, name=name, country=country, driver=self, extra=extra
        )

    def _to_image(self, data: Dict[str, Any]) -> NodeImage:

        id_ = data["id"]
        name = data["attributes"]["name"]
        extra = {
            "slug": data["attributes"]["slug"],
            "version": data["attributes"]["version"],
            "user": data["attributes"]["user"],
            "features": data["attributes"]["features"],
        }
        return NodeImage(id=id_, name=name, driver=self, extra=extra)

    def _to_size(self, data: Dict[str, Any]) -> NodeSize:
        id_ = data["id"]
        name = data["attributes"]["name"]
        ram = int(data["attributes"]["specs"]["memory"]["total"])
        disk = self._disk_list_to_gbs(data["attributes"]["specs"]["drives"])
        bandwidth = None

        # Maxihost prices differ per region, get the first one available
        price = next(
            (
                region["pricing"]["USD"]["month"]
                for region in data["attributes"]["available_in"]
                if region["pricing"]["USD"].get("month")
            ),
            0,
        )
        extra = {
            "slug": data["attributes"]["slug"],
            "line": data["attributes"]["line"],
            "features": data["attributes"]["features"],
            "available_in": data["attributes"]["available_in"],
            "specs": data["attributes"]["specs"],
        }
        return NodeSize(
            id=id_,
            name=name,
            ram=ram,
            disk=disk,
            bandwidth=bandwidth,
            price=price,
            driver=self,
            extra=extra,
        )

    def _disk_list_to_gbs(self, disk_list: List[Dict[str, Any]]) -> int:
        """Convert a list of dictionaries containing disk information to an integer
        that denotes the total disk space available in GBs.
        """
        size_map_multiplier = {
            "gb": 1,
            "tb": 1024,
        }
        total_disk_size = 0
        for disk in disk_list:
            count = disk["count"]
            # Disk size is a notation e.g "100GB"
            size_str = disk["size"]
            for suffix, multiplier in size_map_multiplier.items():
                try:
                    size = int(size_str.lower().split(suffix)[0])
                except ValueError:
                    continue
                else:
                    total_disk_size += size * multiplier * count
        return total_disk_size

    def _to_json_file(self, data, output_file):
        import json

        json_object = json.dumps(data, indent=4)
        with open(output_file, "w") as outfile:
            outfile.write(json_object)
