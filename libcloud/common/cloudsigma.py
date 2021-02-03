# -*- coding: utf-8 -*-
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

__all__ = [
    'API_ENDPOINTS_1_0',
    'API_ENDPOINTS_2_0',
    'API_VERSIONS',
    'INSTANCE_TYPES',
    'MAX_VIRTIO_CONTROLLERS',
    'MAX_VIRTIO_UNITS'
]

# API end-points
API_ENDPOINTS_1_0 = {
    'zrh': {
        'name': 'Zurich',
        'country': 'Switzerland',
        'host': 'api.zrh.cloudsigma.com'
    },
    'lvs': {
        'name': 'Las Vegas',
        'country': 'United States',
        'host': 'api.lvs.cloudsigma.com'
    }
}

API_ENDPOINTS_2_0 = {
    'zrh': {
        'name': 'Zurich',
        'country': 'Switzerland',
        'host': 'zrh.cloudsigma.com'
    },
    'sjc': {
        'name': 'San Jose, CA',
        'country': 'United States',
        'host': 'sjc.cloudsigma.com'
    },
    'mia': {
        'name': 'Miami, FL',
        'country': 'United States',
        'host': 'mia.cloudsigma.com'
    },
    'wdc': {
        'name': 'Washington, DC',
        'country': 'United States',
        'host': 'wdc.cloudsigma.com'
    },
    'hnl': {
        'name': 'Honolulu, HI',
        'country': 'United States',
        'host': 'hnl.cloudsigma.com'
    },
    'per': {
        'name': 'Perth, Australia',
        'country': 'Australia',
        'host': 'per.cloudsigma.com'
    },
    'mnl': {
        'name': 'Manila, Philippines',
        'country': 'Philippines',
        'host': 'mnl.cloudsigma.com'
    },
    'waw': {
        'name': 'Warsaw, Poland',
        'country': 'Poland',
        'host': 'waw.cloudsigma.com'
    }
}

DEFAULT_REGION = 'zrh'

# Supported API versions.
API_VERSIONS = [
    '1.0'  # old and deprecated
    '2.0'
]

DEFAULT_API_VERSION = '2.0'

# CloudSigma doesn't specify special instance types.
# Basically for CPU any value between 0.5 GHz and 20.0 GHz should work,
# 500 MB to 32000 MB for ram
# and 1 GB to 1024 GB for hard drive size.
# Plans in this file are based on examples listed on https://cloudsigma
# .com/pricing/
INSTANCE_TYPES = [
    {
        'id': 'small-1',
        'name': 'small-1, 1 CPUs, 512MB RAM, 50GB disk',
        'cpu': 1,
        'memory': 512,
        'disk': 50,
        'bandwidth': None,
    },
    {
        'id': 'small-2',
        'name': 'small-2, 1 CPUs, 1024MB RAM, 50GB disk',
        'cpu': 1,
        'memory': 1024,
        'disk': 50,
        'bandwidth': None,
    },
    {
        'id': 'small-3',
        'name': 'small-3, 1 CPUs, 2048MB RAM, 50GB disk',
        'cpu': 1,
        'memory': 2048,
        'disk': 50,
        'bandwidth': None,
    },
    {
        'id': 'medium-1',
        'name': 'medium-1, 2 CPUs, 2048MB RAM, 50GB disk',
        'cpu': 2,
        'memory': 2048,
        'disk': 50,
        'bandwidth': None,
    },
    {
        'id': 'medium-2',
        'name': 'medium-2, 2 CPUs, 4096MB RAM, 60GB disk',
        'cpu': 2,
        'memory': 4096,
        'disk': 60,
        'bandwidth': None,
    },
    {
        'id': 'medium-3',
        'name': 'medium-3, 4 CPUs, 8192MB RAM, 80GB disk',
        'cpu': 4,
        'memory': 8192,
        'disk': 80,
        'bandwidth': None,
    },
    {
        'id': 'large-1',
        'name': 'large-1, 8 CPUs, 16384MB RAM, 160GB disk',
        'cpu': 8,
        'memory': 16384,
        'disk': 160,
        'bandwidth': None,
    },
    {
        'id': 'large-2',
        'name': 'large-2, 12 CPUs, 32768MB RAM, 320GB disk',
        'cpu': 12,
        'memory': 32768,
        'disk': 320,
        'bandwidth': None,
    },
    {
        'id': 'large-3',
        'name': 'large-3, 16 CPUs, 49152MB RAM, 480GB disk',
        'cpu': 16,
        'memory': 49152,
        'disk': 480,
        'bandwidth': None,
    },
    {
        'id': 'xlarge',
        'name': 'xlarge, 20 CPUs, 65536MB RAM, 640GB disk',
        'cpu': 20,
        'memory': 65536,
        'disk': 640,
        'bandwidth': None,
    },
]


MAX_VIRTIO_CONTROLLERS = 203
MAX_VIRTIO_UNITS = 4
