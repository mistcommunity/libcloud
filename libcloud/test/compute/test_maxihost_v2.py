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
import sys
import unittest

from libcloud.utils.py3 import httplib
from libcloud.compute.drivers.maxihost import MaxihostNodeDriver
from libcloud.compute.drivers.maxihost import MaxihostNodeDriverV2
from libcloud.common.maxihost import MaxihostException
from libcloud.test import MockHttp
from libcloud.test.file_fixtures import ComputeFileFixtures


class MaxihostTestsV2(unittest.TestCase):
    def setUp(self):
        MaxihostNodeDriver.connectionCls.conn_class = MaxihostMockHttpV2
        MaxihostMockHttpV2.type = None
        self.driver = MaxihostNodeDriver("foo")

    def test_correct_class_is_used(self):
        self.assertIsInstance(self.driver, MaxihostNodeDriverV2)

    def test_unknown_api_version(self):
        self.assertRaises(NotImplementedError, MaxihostNodeDriver, "foo", api_version="3")

    def test_list_sizes(self):
        sizes = self.driver.list_sizes()
        self.assertEqual(len(sizes), 71)
        size = sizes[0]
        self.assertEqual(size.id, "39")
        self.assertEqual(size.name, "c1.large.x86")
        for size in sizes:
            self.assertIsInstance(size.price, float)
            self.assertIsInstance(size.ram, int)
            self.assertIsInstance(size.disk, int)


class MaxihostMockHttpV2(MockHttp):
    fixtures = ComputeFileFixtures("maxihost_v2")

    def _plans(self, method, url, body, headers):
        body = self.fixtures.load("list_sizes.json")
        return (httplib.OK, body, {}, httplib.responses[httplib.OK])

if __name__ == "__main__":
    sys.exit(unittest.main())
