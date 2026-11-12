"""Publish only sanitized build packets; preserve the last good Pages data on outages."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'https://179-254-163-44.sslip.io/buildsplus-mirror'
LIMIT = 512 * 1024
MODES = ('used', 'high', 'new', 'authors')
NETWORK_ERRORS = (OSError, ValueError, http.client.HTTPException)


def get_json(url):
    request = Request(url, headers={'Accept': 'application/json', 'User-Agent': 'BuildsPlus-Pages/0.1.3'})
    with urlopen(request, timeout=8) as response:
        body = response.read(LIMIT + 1)
    if len(body) > LIMIT:
        raise ValueError('Response too large')
    return json.loads(body)


def ids(manifest):
    if not isinstance(manifest, dict) or manifest.get('kind') != 'buildsplus-mirror-manifest-v1':
        raise ValueError('Invalid mirror manifest')
    heroes = manifest.get('heroes')
    if not isinstance(heroes, list) or not heroes or len(heroes) > 200:
        raise ValueError('Invalid hero roster')
    if any(type(hero) is not int or not 1 <= hero <= 9999 for hero in heroes):
        raise ValueError('Invalid hero identity')
    return sorted(set(heroes))


def validate(packet, hero):
    if not isinstance(packet, dict) or packet.get('kind') != 'personal-builds-v1':
        raise ValueError('Invalid packet kind')
    entry = packet.get('hero')
    if not isinstance(entry, dict) or type(entry.get('id')) is not int or entry['id'] != hero:
        raise ValueError('Unexpected hero')
    if not any(mode in entry for mode in MODES):
        raise ValueError('No build collections')
    for mode in MODES:
        if mode not in entry:
            continue
        group = entry[mode]
        if not isinstance(group, dict) or not isinstance(group.get('at'), str) or not isinstance(group.get('rows'), list) or len(group['rows']) > 20:
            raise ValueError('Invalid build collection')
        for row in group['rows']:
            if (not isinstance(row, dict) or type(row.get('id')) is not int or row['id'] <= 0
                    or row.get('heroId') != hero or type(row.get('authorId')) is not int
                    or not 0 < row['authorId'] <= 4294967295 or not isinstance(row.get('name'), str)
                    or not isinstance(row.get('author'), str)):
                raise ValueError('Invalid build identity')
    body = json.dumps(packet, ensure_ascii=False, separators=(',', ':'))
    if len(quote(body, safe="~()*!.'-")) > 189000:
        raise ValueError('Packet exceeds Panorama limit')
    return packet


def cache_at(packet):
    return max((packet['hero'].get(mode, {}).get('at', '') for mode in MODES), default='')


def previous_url():
    repository = os.environ.get('GITHUB_REPOSITORY', '')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        return None
    owner, name = repository.split('/')
    return 'https://' + owner.lower() + '.github.io/' + ('' if name.lower() == owner.lower() + '.github.io' else name + '/')


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()
    with NamedTemporaryFile(dir=path.parent, delete=False) as file:
        file.write(body)
    temporary = Path(file.name)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return body


def sync(root=ROOT, request=get_json, source=SOURCE, previous=None):
    root = Path(root)
    site = root / 'site'
    old_manifest = None
    if previous:
        try:
            old_manifest = request(previous + 'manifest.json')
            ids(old_manifest)
        except NETWORK_ERRORS:
            old_manifest = None
    source_available = True
    try:
        roster = ids(request(source + '/manifest.json'))
    except NETWORK_ERRORS:
        source_available = False
        if old_manifest:
            roster = ids(old_manifest)
        else:
            roster = sorted(int(p.stem) for p in (site / 'data').glob('*.json') if p.stem.isdecimal() and 0 < int(p.stem) <= 9999)
    if not roster:
        raise ValueError('No source or last good hero roster')

    def load(hero):
        old_info = (old_manifest or {}).get('packets', {}).get(str(hero), {})
        packet = None
        if source_available:
            try:
                packet = validate(request(source + '/data/' + str(hero) + '.json'), hero)
            except NETWORK_ERRORS:
                pass
        if packet and cache_at(packet) >= old_info.get('at', ''):
            return hero, packet, True
        if previous and old_manifest and hero in old_manifest['heroes']:
            try:
                saved = validate(request(previous + 'data/' + str(hero) + '.json'), hero)
                # A valid older upstream packet must not regress a newer published cache.
                return hero, dict(saved, phase='offline') if packet is None else saved, False
            except NETWORK_ERRORS:
                # If a known newer cache cannot be read, keep the existing deployment.
                raise ValueError('Could not preserve last good hero ' + str(hero)) from None
        if packet:
            return hero, packet, True
        try:
            seed = validate(json.loads((site / 'data' / f'{hero}.json').read_bytes()), hero)
        except (OSError, ValueError):
            raise ValueError('No valid cached hero ' + str(hero)) from None
        return hero, dict(seed, phase='offline'), False

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(load, roster))
    details = {}
    for hero, packet, _ in results:
        body = atomic(site / 'data' / f'{hero}.json', packet)
        details[str(hero)] = {'at': cache_at(packet), 'sha256': hashlib.sha256(body).hexdigest()}
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    live = sum(ok for _, _, ok in results)
    manifest = {'kind': 'buildsplus-mirror-manifest-v1', 'at': now, 'heroes': roster,
                'sourceAvailable': source_available, 'liveHeroes': live, 'packets': details}
    atomic(site / 'manifest.json', manifest)
    print('Published', len(results), 'hero packets;', live, 'fresh from source; remaining packets retain their dated cache.')
    return manifest


if __name__ == '__main__':
    sync(previous=previous_url())
