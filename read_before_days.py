import os
import sys
import time
import json
import datetime
from typing import Literal, Optional, Tuple, Union, overload
from urllib import request, parse
from http.client import HTTPResponse, IncompleteRead
import logging
from zoneinfo import ZoneInfo


def http_request(method, url, params=None, headers=None, data: Optional[Union[dict, list, bytes]] = None, timeout=None, logger=None) -> Tuple[HTTPResponse, str]:
    if params:
        url = f'{url}?{parse.urlencode(params)}'
    # raise (HTTPException, URLError)
    if not headers:
        headers = {}
    if data and isinstance(data, (dict, list)):
        data = json.dumps(data, ensure_ascii=False).encode()
        if 'Content-Type' not in headers:
            headers['Content-Type'] = 'application/json; charset=utf-8'
    if logger:
        logger.info(f'request: {method} {url}')
    req = request.Request(url, method=method, headers=headers, data=data)
    res = request.urlopen(req, timeout=timeout)
    try:
        body: str = res.read().decode()
    except IncompleteRead as e:
        body: str = e.partial.decode()
    if logger:
        logger.debug(f'response: {res.status}, {body}')
    return res, body


EntryStatus = Union[Literal['read'], Literal['unread']]


class MinifluxClient:

    def __init__(self, base_url, api_token, logger=None) -> None:
        self.base_url = base_url
        self.api_token = api_token
        self.logger = logger

    @overload
    def request(self, method, path, params=None, data=None, json_response: Literal[True] = True) -> dict:
        ...

    @overload
    def request(self, method, path, params=None, data=None, json_response: Literal[False] = False) -> str:
        ...

    def request(self, method, path, params=None, data=None, json_response=True):
        url = f'{self.base_url}{path}'
        headers = {
            'X-Auth-Token': self.api_token,
        }
        res, body = http_request(method, url, params=params, headers=headers, data=data, logger=self.logger)
        if res.status > 299:
            raise Exception(f'HTTP error: {res.status}, {body}')
        if json_response:
            return json.loads(body)
        return body

    def get_current_user(self):
        return self.request('GET', 'me')

    def mark_user_entries_as_read(self, user_id):
        self.request('PUT', f'users/{user_id}/mark-all-as-read', json_response=False)

    def get_entries_by_status(self, status: EntryStatus, after_entry_id=None):
        params = {
            'order': 'published_at',
            'direction': 'desc',
            'status': status,
            'limit': 100,
        }
        if after_entry_id:
            params['after_entry_id'] = after_entry_id
        return self.request('GET', 'entries', params)

    def update_entries(self, entry_ids, status: EntryStatus):
        self.request('PUT', 'entries', data={
            'entry_ids': entry_ids,
            'status': status,
        }, json_response=False)


def main():
    lg = logging.getLogger()
    logging.basicConfig(level=logging.INFO)

    days = int(sys.argv[1])
    sep_date = datetime.datetime.now(ZoneInfo('Asia/Shanghai')) - datetime.timedelta(days=days)

    client = MinifluxClient(
        os.environ['MINIFLUX_API_URL'],
        os.environ['MINIFLUX_API_TOKEN'],
        lg)

    user = client.get_current_user()
    print('mark user entries as read')
    client.mark_user_entries_as_read(user['id'])

    time.sleep(1)
    print(f'get entries after {sep_date}')
    entry_ids = []
    append_entries_after_date(client, entry_ids, sep_date)
    print(f'entry ids: {entry_ids}')

    print(f'mark entries as unread')
    client.update_entries(entry_ids, 'unread')


def append_entries_after_date(client, entry_ids, date, after_entry_id=None):
    data = client.get_entries_by_status('read', after_entry_id)
    print(f'status=read entries: total: {data["total"]}; len: {len(data["entries"])}')
    after_date_entry = None
    for i in data["entries"]:
        entry = i
        published_at = parse_time(i["published_at"])
        if published_at > date:
            print(f'{published_at} {i["title"]}')
            entry_ids.append(entry['id'])
            after_date_entry = entry
        else:
            after_date_entry = None
            break

    if after_date_entry:
        time.sleep(1)
        append_entries_after_date(client, entry_ids, date, after_date_entry['id'])



def parse_time(s) -> datetime.datetime:
    format = '%Y-%m-%dT%H:%M:%S%z'
    if '.' in s:
        format = '%Y-%m-%dT%H:%M:%S.%f%z'
    return datetime.datetime.strptime(s, format)


if __name__ == '__main__':
    main()
