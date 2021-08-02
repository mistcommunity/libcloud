import datetime
import base64
import requests
from requests.exceptions import ConnectionError
from requests.exceptions import HTTPError
from urllib import parse

from libcloud.common.base import ConnectionUserAndKey
from libcloud.common.kubernetes import KubernetesResponse
from libcloud.common.types import LibcloudError


UTC_TIMESTAMP_FORMAT = '%Y-%m-%dT%H:%M:%SZ'


def _utcnow():
    return datetime.datetime.utcnow()


def _utc_timestamp(datetime_obj):
    """
    Return string of datetime_obj in the UTC Timestamp Format
    """
    return datetime_obj.strftime(UTC_TIMESTAMP_FORMAT)


def _from_utc_timestamp(timestamp):
    """
    Return datetime obj where date and time are pulled from timestamp string.
    """
    return datetime.datetime.strptime(timestamp, UTC_TIMESTAMP_FORMAT)


class OpenShiftAuthError(LibcloudError):
    """Generic Error class for various authentication errors."""

    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return repr(self.value)


class OpenShiftBasicAuthConnection(ConnectionUserAndKey):
    API_SUBDOMAIN_PREFIX = 'api.'
    OAUTH_SUBDOMAIN_PREFIX = 'oauth-openshift.apps.'
    OAUTH_TOKEN_ENDPOINT = ('oauth/authorize?'
                            'client_id=openshift-challenging-client'
                            '&response_type=token')

    responseCls = KubernetesResponse
    timeout = 60

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._token = None

    @property
    def _access_token(self):
        if self._token is None or self._token_expire_utc_datetime < _utcnow():
            self._refresh_token()
        return self._token['access_token']

    @property
    def _token_expire_utc_datetime(self):
        return _from_utc_timestamp(self._token['expire_time'])

    def _refresh_token(self):
        """
        Get a new token. Generally used when no previous token exists or the
        existing token has expired

        :return:  Dictionary containing token information
        :rtype:   ``dict``
        """
        import ipdb
        ipdb.set_trace()
        host = self.host.strip('http://').strip('https://')
        if host.startswith(self.API_SUBDOMAIN_PREFIX):
            base_host = host[len(self.API_SUBDOMAIN_PREFIX):]
        else:
            base_host = host
        base_endpoint = 'https://' + self.OAUTH_SUBDOMAIN_PREFIX + base_host
        endpoint = parse.urljoin(base_endpoint, self.OAUTH_TOKEN_ENDPOINT)
        auth_string = f'{self.user_id}:{self.key}'.encode()
        user_b64 = base64.b64encode(auth_string)
        headers = dict(Authorization=f"Basic {user_b64.decode('utf-8')}")
        headers['X-CSRF-Token'] = 'xxx'
        try:
            response = requests.get(endpoint, headers=headers, verify=False)
        except ConnectionError as e:
            raise OpenShiftAuthError(str(e))
        try:
            response.raise_for_status()
        except HTTPError:
            raise OpenShiftAuthError('Invalid authorization request, please '
                                     'check your credentials or retry.')
        token_info = parse.parse_qs(parse.urlsplit(
            response.url).fragment)
        access_token = token_info['access_token'][0]
        expires_in = int(token_info['expires_in'][0])
        expire_time = _utcnow() + datetime.timedelta(
            seconds=expires_in)
        self._token = {
            'access_token': access_token,
            'expire_time': _utc_timestamp(expire_time)
        }

    def add_default_headers(self, headers):
        """
        Add parameters that are necessary for every request
        If user and password are specified, retrieve and include a bearer
        token
        """
        if 'Content-Type' not in headers:
            headers['Content-Type'] = 'application/json'
        if self.user_id and self.key:
            headers['Authorization'] = 'Bearer ' + self._access_token
        return headers
