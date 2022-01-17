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
from typing import Any, Dict, Optional
from libcloud.utils.py3 import httplib
from libcloud.common.types import InvalidCredsError
from libcloud.common.base import JsonResponse
from libcloud.common.base import ConnectionKey


DEFAULT_API_VERSION = "2"


class MaxihostResponse(JsonResponse):
    valid_response_codes = [
        httplib.OK,
        httplib.ACCEPTED,
        httplib.CREATED,
        httplib.NO_CONTENT,
    ]

    def parse_error(self):
        if self.status == httplib.UNAUTHORIZED:
            body = self.parse_body()
            raise InvalidCredsError(body["message"])
        else:
            body = self.parse_body()
            if "message" in body:
                error = "%s (code: %s)" % (body["message"], self.status)
            else:
                error = body
            return error

    def success(self):
        return self.status in self.valid_response_codes


class MaxihostConnection(ConnectionKey):
    """
    Connection class for the Maxihost driver.
    """

    host = "api.maxihost.com"
    responseCls = MaxihostResponse

    def add_default_headers(self, headers):
        """
        Add headers that are necessary for every request

        This method adds apikey to the request.
        """
        headers["Authorization"] = "Bearer %s" % (self.key)
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/vnd.maxihost.v1.1+json"
        return headers


class MaxihostException(Exception):
    """
    Error originating from the Maxihost API
    """

    def __init__(self, code, message):
        self.code = code
        self.message = message

    def __str__(self):
        return "(%s) %s" % (self.code, self.message)

    def __repr__(self):
        return "MaxihostException code %s '%s'" % (self.code, self.message)


class MaxihostResponseV2(JsonResponse):
    valid_response_codes = [
        httplib.OK,
        httplib.ACCEPTED,
        httplib.CREATED,
        httplib.NO_CONTENT,
    ]

    def parse_error(self):
        """
        Parse the error body and raise the appropriate exception
        """
        status = self.status
        data = self.parse_body()
        error_dict = data["errors"][0]
        error_msg = "%s: %s" % (
            error_dict.get("code", ""),
            error_dict.get("detail", ""),
        )
        raise MaxihostException(code=status, message=error_msg)

    def success(self) -> bool:
        """Check the response for success

        :return: ``bool`` indicating a successful request
        """
        return self.status in self.valid_response_codes


class MaxihostConnectionV2(ConnectionKey):
    """
    Connection class for the Maxihost driver.
    """

    host = "api.maxihost.com"
    responseCls = MaxihostResponseV2

    def add_default_headers(self, headers):
        """
        Add headers that are necessary for every request
        """
        headers["Authorization"] = self.key
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/vnd.maxihost.v2+json"
        return headers

    def add_default_params(self, params):
        params["page[size]"] = 1000
        return params


class MaxihostProject:
    """
    Represents information about a Maxihost project.
    """

    def __init__(
        self,
        id: str,
        name: str,
        environment: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.id = id
        self.name = name
        self.environment = environment
        self.extra = extra or {}

    def __repr__(self):
        return "<MaxihostProject: id=%s name=%s environment=%s" % (
            self.id,
            self.name,
            self.environment,
        )
