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

from __future__ import with_statement

from typing import Dict

"""
A class which handles loading the pricing files.
"""

import os.path
from os.path import join as pjoin

try:
    import simplejson as json

    try:
        JSONDecodeError = json.JSONDecodeError
    except AttributeError:
        # simplejson < 2.1.0 does not have the JSONDecodeError exception class
        JSONDecodeError = ValueError  # type: ignore
except ImportError:
    import json  # type: ignore

    JSONDecodeError = ValueError  # type: ignore

__all__ = [
    "get_pricing",
    "get_size_price",
    "get_gce_image_price",
    "set_pricing",
    "clear_pricing_data",
    "download_pricing_file",
]

# Default URL to the pricing file in a git repo
DEFAULT_FILE_URL_GIT = "https://git-wip-us.apache.org/repos/asf?p=libcloud.git;a=blob_plain;f=libcloud/data/pricing.json"  # NOQA

DEFAULT_FILE_URL_S3_BUCKET = (
    "https://libcloud-pricing-data.s3.amazonaws.com/pricing.json"  # NOQA
)

CURRENT_DIRECTORY = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PRICING_FILE_PATH = pjoin(CURRENT_DIRECTORY, "data/pricing.json")
CUSTOM_PRICING_FILE_PATH = os.path.expanduser("~/.libcloud/pricing.json")

# Pricing data cache
PRICING_DATA = {"compute": {}, "storage": {}}  # type: Dict[str, Dict]

VALID_PRICING_DRIVER_TYPES = ["compute", "storage"]


def get_pricing_file_path(file_path=None):
    if os.path.exists(CUSTOM_PRICING_FILE_PATH) and os.path.isfile(
        CUSTOM_PRICING_FILE_PATH
    ):
        # Custom pricing file is available, use it
        return CUSTOM_PRICING_FILE_PATH

    return DEFAULT_PRICING_FILE_PATH


def get_pricing(driver_type, driver_name, pricing_file_path=None):
    """
    Return pricing for the provided driver.

    :type driver_type: ``str``
    :param driver_type: Driver type ('compute' or 'storage')

    :type driver_name: ``str``
    :param driver_name: Driver name

    :type pricing_file_path: ``str``
    :param pricing_file_path: Custom path to a price file. If not provided
                              it uses a default path.

    :rtype: ``dict``
    :return: Dictionary with pricing where a key name is size ID and
             the value is a price.
    """
    if driver_type not in VALID_PRICING_DRIVER_TYPES:
        raise AttributeError("Invalid driver type: %s", driver_type)

    if driver_name in PRICING_DATA[driver_type]:
        return PRICING_DATA[driver_type][driver_name]

    if not pricing_file_path:
        pricing_file_path = get_pricing_file_path(file_path=pricing_file_path)

    with open(pricing_file_path) as fp:
        content = fp.read()

    pricing_data = json.loads(content)
    # google asia region prices dont include the postfix number in the pricing
    # data: e.g. we have data for google_asia-east instead of google_asia-east1
    if (
        driver_name not in pricing_data[driver_type]
        and driver_name[:-1] in pricing_data[driver_type]
    ):
        size_pricing = pricing_data[driver_type][driver_name[:-1]]
    elif (
        driver_name not in pricing_data[driver_type]
        and driver_name[:-2] in pricing_data[driver_type]
    ):
        size_pricing = pricing_data[driver_type][driver_name[:-2]]
    else:
        size_pricing = pricing_data[driver_type][driver_name]

    for driver_type in VALID_PRICING_DRIVER_TYPES:
        # pylint: disable=maybe-no-member
        pricing = pricing_data.get(driver_type, None)
        if pricing:
            PRICING_DATA[driver_type] = pricing

    return size_pricing


def set_pricing(driver_type, driver_name, pricing):
    """
    Populate the driver pricing dictionary.

    :type driver_type: ``str``
    :param driver_type: Driver type ('compute' or 'storage')

    :type driver_name: ``str``
    :param driver_name: Driver name

    :type pricing: ``dict``
    :param pricing: Dictionary where a key is a size ID and a value is a price.
    """

    PRICING_DATA[driver_type][driver_name] = pricing


def get_size_price(driver_type, driver_name, size_id, region=None):
    """
    Return price for the provided size.

    :type driver_type: ``str``
    :param driver_type: Driver type ('compute' or 'storage')

    :type driver_name: ``str``
    :param driver_name: Driver name

    :type size_id: ``str`` or ``int``
    :param size_id: Unique size ID (can be an integer or a string - depends on
                    the driver)

    :rtype: ``float``
    :return: Size price.
    """
    pricing = get_pricing(driver_type=driver_type, driver_name=driver_name)

    try:
        if region is None:
            price = float(pricing[size_id])
        else:
            price = float(pricing[size_id][region])
    except KeyError:
        # Price not available
        price = None

    return price


def get_gce_image_price(image_name, size):
    """
    Return price per hour for an gce image.
    Price depends on the size of the VM.

    :type image_name: ``str``
    :param image_name: GCE image full name

    :type size: ``GCENodeSize``
    :param size: The GCE NodeSize instance of the VM that has the image.
                 This is needed because image price may change depending
                 on the CPUs of the VM or the size type.

    :rtype: ``float``
    :return: Image price
    """

    img = None

    # Decide if the image is a premium image
    if "sql" in image_name:
        img='SQL Server'
    elif 'windows' in image_name:
        img = 'Windows Server'
    elif "rhel" in image_name and "sap" in image_name:
        img = 'RHEL with Update Services'
    elif "sles for sap" in image_name:
        img = 'SLES for SAP'
    elif 'rhel' in image_name:
        img = 'RHEL'
    elif 'sles' in image_name:
        img = 'SLES'

    price = 0
    # if there is no premium image return 0
    if not img:
        return price

    pricing = get_pricing(driver_type='compute', driver_name='gce_images')
    try:
        price_dict = pricing[img]
    except KeyError:
        # Price not available
        return price

    size_type = 'any'
    if 'f1' in size.name:
        size_type = 'f1'
    elif 'g1' in size.name:
        size_type = 'g1'
    cores = float(size.extra.get('guestCpus', 1))

    # get price depending on premium image 
    if img == 'Windows Server':
        if size_type in {'f1', 'g1'}:
            price = price_dict[size_type].get('price', 0)
        else:
            price = price_dict['any'].get('price', 0) * cores
    elif img == 'RHEL':
        if cores <= 4:
            price = price_dict['4vcpu or less'].get('price', 0)
        else:
            price = price_dict['6vcpu or more'].get('price', 0)
    elif img == 'SLES':
        if size_type in {'f1', 'g1'}:
            price = price_dict[size_type].get('price', 0)
        else:
            price = price_dict['any'].get('price', 0)
    elif img == 'SLES for SAP':
        if cores >= 6:
            price = price_dict['6vcpu or more'].get('price', 0)
        elif 2 < cores <= 4:
            price = price_dict['3-4vcpu'].get('price', 0)
        elif cores <= 2:
            price = price_dict['1-2vcpu'].get('price', 0)
    elif img == 'RHEL with Update Services':
        if cores <= 4:
            price = price_dict['4vcpu or less'].get('price', 0)
        else:
            price = price_dict['6vcpu or more'].get('price', 0)

    elif img == "SQL Server":
        if 'standard' in image_name:
            price = price_dict['standard'].get('price', 0) * cores
        elif 'enterprise' in image_name:
            price = price_dict['enterprise'].get('price', 0) * cores
        elif 'web' in image_name:
            price = price_dict['web'].get('price', 0) * cores

    return float(price)


def invalidate_pricing_cache():
    """
    Invalidate pricing cache for all the drivers.
    """
    PRICING_DATA["compute"] = {}
    PRICING_DATA["storage"] = {}


def clear_pricing_data():
    """
    Invalidate pricing cache for all the drivers.

    Note: This method does the same thing as invalidate_pricing_cache and is
    here for backward compatibility reasons.
    """
    invalidate_pricing_cache()


def invalidate_module_pricing_cache(driver_type, driver_name):
    """
    Invalidate the cache for the specified driver.

    :type driver_type: ``str``
    :param driver_type: Driver type ('compute' or 'storage')

    :type driver_name: ``str``
    :param driver_name: Driver name
    """
    if driver_name in PRICING_DATA[driver_type]:
        del PRICING_DATA[driver_type][driver_name]


def download_pricing_file(
    file_url=DEFAULT_FILE_URL_S3_BUCKET, file_path=CUSTOM_PRICING_FILE_PATH
):
    """
    Download pricing file from the file_url and save it to file_path.

    :type file_url: ``str``
    :param file_url: URL pointing to the pricing file.

    :type file_path: ``str``
    :param file_path: Path where a download pricing file will be saved.
    """
    from libcloud.utils.connection import get_response_object

    dir_name = os.path.dirname(file_path)

    if not os.path.exists(dir_name):
        # Verify a valid path is provided
        msg = "Can't write to %s, directory %s, doesn't exist" % (file_path, dir_name)
        raise ValueError(msg)

    if os.path.exists(file_path) and os.path.isdir(file_path):
        msg = "Can't write to %s file path because it's a" " directory" % (file_path)
        raise ValueError(msg)

    response = get_response_object(file_url)
    body = response.body

    # Verify pricing file is valid
    try:
        data = json.loads(body)
    except JSONDecodeError:
        msg = "Provided URL doesn't contain valid pricing data"
        raise Exception(msg)

    # pylint: disable=maybe-no-member
    if not data.get("updated", None):
        msg = "Provided URL doesn't contain valid pricing data"
        raise Exception(msg)

    # No need to stream it since file is small
    with open(file_path, "w") as file_handle:
        file_handle.write(body)
