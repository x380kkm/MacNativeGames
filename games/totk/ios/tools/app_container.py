#!/usr/bin/env python3
"""The app's data container that push_device_windows.py writes into: on the device through pymobiledevice3
(DeviceContainer, the one place its types appear), or a local folder standing for it (LocalContainer, --simulate).

Both offer the same methods on paths inside the container ('Documents/...'): listdir ({name: (size, is folder)}, None for
a missing folder), read (None for a missing file), write (to a temporary name, then renamed, so the app never reads half
of a marker), upload (a range of a local file, CHUNK bytes at a time), download, makedirs, remove, installed (the
installed app's Info.plist keys, None when it is not installed), install (an IPA; an installed app of the same identifier
is replaced and keeps its data container) and close.

DeviceContainer: the device is connected by cable (on Windows with iTunes or Apple Devices installed, for its usbmuxd)
and unlocked. house_arrest gives the app's Documents over AFC (the app has UIFileSharingEnabled and get-task-allow); an
IPA goes to the device's staging folder over AFC in 4 MiB writes and installation_proxy installs it (pymobiledevice3
apps install reads the whole IPA into memory first). pymobiledevice3's async API runs on an event loop of its own thread.
pymobiledevice3 (a pipx or uv tool) has its own Python: pmd3_python finds it, check_api checks without a device that the
names and parameters used here are there."""
import inspect, json, os, plistlib, shutil, subprocess, sys, zipfile
from pathlib import Path

CHUNK = 4 << 20   # pymobiledevice3's AFC transfer size


class ContainerError(RuntimeError):
    pass


def require(ok, message):
    if not ok:
        raise ContainerError(message)


def chunks(src, length):
    """length bytes of the open file src from where it stands, CHUNK at a time."""
    while length:
        chunk = src.read(min(CHUNK, length))
        require(chunk, f'{src.name}: shorter than expected')
        length -= len(chunk)
        yield chunk


def file_range(source, offset, length):
    return length if length is not None else Path(source).stat().st_size - offset


def ipa_info(ipa):
    """The Info.plist of the app in an IPA, with 'carries': whether the app holds its shader seed and its RomFS image."""
    with zipfile.ZipFile(ipa) as z:
        plists = [n for n in z.namelist() if n.count('/') == 2 and n.startswith('Payload/') and n.endswith('.app/Info.plist')]
        require(len(plists) == 1, f'{ipa}: not one Payload/<name>.app')
        info = plistlib.loads(z.read(plists[0]))
        info['carries'] = {k: f'{plists[0][:-len("Info.plist")]}GameData/{v}' in z.namelist()
                           for k, v in (('seed', 'shader-seed/seed-manifest.json'), ('romfs', 'romfs/romfs.bin'))}
    return info


class LocalContainer:
    """A folder standing for the app's data container (Documents/... inside it), the installed app as a record."""
    def __init__(self, root, bundle_id):
        self.root, self.bundle_id, self.name = Path(root), bundle_id, f'folder {root}'

    def listdir(self, rel):
        path = self.root/rel
        if not path.is_dir():
            return None
        return {p.name: (p.stat().st_size if p.is_file() else 0, p.is_dir()) for p in path.iterdir()}

    def read(self, rel):
        path = self.root/rel
        return path.read_bytes() if path.is_file() else None

    def write(self, rel, data):
        path = self.root/rel; path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + '.tmp'); temp.write_bytes(data); os.replace(temp, path)

    def upload(self, rel, source, offset=0, length=None, progress=None):
        path = self.root/rel; path.parent.mkdir(parents=True, exist_ok=True)
        done = 0
        with open(source, 'rb') as src, open(path, 'wb') as dst:
            src.seek(offset)
            for chunk in chunks(src, file_range(source, offset, length)):
                dst.write(chunk); done += len(chunk)
                if progress: progress(done)

    def download(self, rel, target):
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(self.root/rel, target)

    def makedirs(self, rel):
        (self.root/rel).mkdir(parents=True, exist_ok=True)

    def remove(self, rel):
        (self.root/rel).unlink(missing_ok=True)

    def installed(self):
        record = self.root/'.installed.json'
        return json.loads(record.read_text()) if record.is_file() else None

    def install(self, ipa, progress=None):
        info = ipa_info(ipa)
        self.root.mkdir(parents=True, exist_ok=True); (self.root/'Documents').mkdir(exist_ok=True)
        (self.root/'.installed.json').write_text(json.dumps(
            {k: info.get(k) for k in ('CFBundleIdentifier', 'CFBundleShortVersionString', 'CFBundleVersion')}, indent=2))

    def close(self):
        pass


class DeviceContainer:
    """The app's container on the device through pymobiledevice3: house_arrest (the app's Documents over AFC) and
    installation_proxy (install, look up)."""
    def __init__(self, bundle_id, udid=None):
        import asyncio, contextlib, threading
        from pymobiledevice3.lockdown import create_using_usbmux
        self.asyncio, self.contextlib, self.bundle_id, self.afc = asyncio, contextlib, bundle_id, None
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        self.stack = contextlib.AsyncExitStack()
        try:
            self.lockdown = self.call(create_using_usbmux(serial=udid))
        except Exception as e:   # pymobiledevice3 raises its own errors for no device, no pairing, a locked device
            raise ContainerError(f'no device (connect it by cable, unlock it, trust this computer): {type(e).__name__}: {e}') from None
        info = self.lockdown.short_info
        self.name = f'{info.get("DeviceName")} (iOS {info.get("ProductVersion")}, {info.get("UniqueDeviceID")})'

    def call(self, coroutine):
        return self.asyncio.run_coroutine_threadsafe(coroutine, self.loop).result()

    def documents(self):
        """house_arrest's AFC on the app's Documents, opened on first use; its paths are '/Documents/...'."""
        if self.afc is None:
            from pymobiledevice3.exceptions import AppNotInstalledError
            from pymobiledevice3.services.house_arrest import HouseArrestService
            async def open_documents():
                service = await HouseArrestService.create(self.lockdown, self.bundle_id, documents_only=True)
                return await self.stack.enter_async_context(service)
            try:
                self.afc = self.call(open_documents())
            except AppNotInstalledError:
                raise ContainerError(f'{self.bundle_id} is not installed on the device') from None
        return self.afc

    def listdir(self, rel):
        from pymobiledevice3.exceptions import AfcFileNotFoundError
        afc = self.documents()
        async def run():
            try:
                names = await afc.listdir('/' + rel)
            except AfcFileNotFoundError:
                return None
            out = {}
            for name in names:
                st = await afc.stat(f'/{rel}/{name}')
                out[name] = (st['st_size'], st.get('st_ifmt') == 'S_IFDIR')
            return out
        return self.call(run())

    def read(self, rel):
        from pymobiledevice3.exceptions import AfcFileNotFoundError
        afc = self.documents()
        async def run():
            try:
                return await afc.get_file_contents('/' + rel)
            except AfcFileNotFoundError:
                return None
        return self.call(run())

    def write(self, rel, data):
        from pymobiledevice3.exceptions import AfcException
        afc = self.documents()
        async def run():
            await afc.set_file_contents(f'/{rel}.tmp', data)
            try:
                await afc.rename(f'/{rel}.tmp', '/' + rel)
            except AfcException:   # an AFC that does not rename over a file: the old one goes first
                await afc.rm_single('/' + rel, force=True)
                await afc.rename(f'/{rel}.tmp', '/' + rel)
        self.call(run())

    async def _upload(self, afc, remote, source, offset, length, progress):
        handle = await afc.fopen(remote, 'w')
        try:
            with open(source, 'rb') as src:
                src.seek(offset); done = 0
                for chunk in chunks(src, file_range(source, offset, length)):
                    await afc.fwrite(handle, chunk); done += len(chunk)
                    if progress: progress(done)
        finally:
            await afc.fclose(handle)

    def upload(self, rel, source, offset=0, length=None, progress=None):
        self.call(self._upload(self.documents(), '/' + rel, source, offset, length, progress))

    def download(self, rel, target):
        target.parent.mkdir(parents=True, exist_ok=True)
        afc = self.documents()
        async def run():
            left = (await afc.stat('/' + rel))['st_size']
            handle = await afc.fopen('/' + rel, 'r')
            try:
                with open(target, 'wb') as out:
                    while left:
                        data = await afc.fread(handle, min(CHUNK, left))
                        require(data, f'{rel}: the device sent less than its size')
                        out.write(data); left -= len(data)
            finally:
                await afc.fclose(handle)
        self.call(run())

    def makedirs(self, rel):
        self.call(self.documents().makedirs('/' + rel))

    def remove(self, rel):
        self.call(self.documents().rm_single('/' + rel, force=True))

    def installed(self):
        from pymobiledevice3.services.installation_proxy import InstallationProxyService
        apps = self.call(InstallationProxyService(lockdown=self.lockdown).get_apps(bundle_identifiers=[self.bundle_id]))
        return apps.get(self.bundle_id)

    def install(self, ipa, progress=None):
        """The IPA to the device's staging folder over AFC, then installation_proxy Install: an installed app of the same
        identifier is replaced and keeps its data container."""
        import uuid
        from pymobiledevice3.services.afc import AfcService
        from pymobiledevice3.services.installation_proxy import InstallationProxyService, TEMP_REMOTE_BASEDIR
        async def run():
            async with AfcService(self.lockdown) as staging:
                remote = f'{TEMP_REMOTE_BASEDIR}/{uuid.uuid4()}.ipa'
                await staging.makedirs(TEMP_REMOTE_BASEDIR)
                try:
                    await self._upload(staging, remote, ipa, 0, None, progress)
                    print('  installing on the device', flush=True)
                    await InstallationProxyService(lockdown=self.lockdown).send_package('Install', {}, None, remote)
                finally:
                    await staging.rm_single(remote, force=True)
        if self.afc is not None:   # the container is opened again after the install
            self.call(self.stack.aclose()); self.afc = None; self.stack = self.contextlib.AsyncExitStack()
        self.call(run())

    def close(self):
        try:
            self.call(self.stack.aclose())
            self.call(self.lockdown.close())
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)


def check_api():
    """The pymobiledevice3 names and parameters DeviceContainer calls, without a device."""
    from pymobiledevice3 import lockdown, exceptions
    from pymobiledevice3.services import afc, house_arrest, installation_proxy
    import importlib.metadata
    needs = [(lockdown.create_using_usbmux, ['serial']), (house_arrest.HouseArrestService.create, ['lockdown', 'bundle_id', 'documents_only']),
             (installation_proxy.InstallationProxyService.send_package, ['cmd', 'options', 'handler', 'package_path']),
             (installation_proxy.InstallationProxyService.get_apps, ['bundle_identifiers'])]
    for f, params in needs:
        have = inspect.signature(f).parameters
        require(all(p in have for p in params), f'{f.__qualname__}: expected parameters {params}, has {list(have)}')
    for name in ('listdir', 'stat', 'fopen', 'fwrite', 'fread', 'fclose', 'rename', 'rm_single', 'makedirs',
                 'get_file_contents', 'set_file_contents'):
        method = getattr(afc.AfcService, name, None)   # some are wrapped by pymobiledevice3's path_to_str
        require(method and inspect.iscoroutinefunction(inspect.unwrap(method)), f'AfcService.{name} is not an async method')
    for name in ('AfcFileNotFoundError', 'AppNotInstalledError', 'AfcException'):
        require(hasattr(exceptions, name), f'pymobiledevice3.exceptions has no {name}')
    require(installation_proxy.TEMP_REMOTE_BASEDIR.startswith('/'), 'TEMP_REMOTE_BASEDIR')
    return f'pymobiledevice3 {importlib.metadata.version("pymobiledevice3")} in {sys.executable}: the API used here is there'


def pmd3_python():
    """A Python that imports pymobiledevice3: $TOTK_PMD3_PYTHON, the uv tool's, or pipx's."""
    exe = 'Scripts/python.exe' if os.name == 'nt' else 'bin/python'
    if os.environ.get('TOTK_PMD3_PYTHON'):
        candidates = [Path(os.environ['TOTK_PMD3_PYTHON'])]
    else:
        candidates = []
        if shutil.which('uv'):
            r = subprocess.run(['uv', 'tool', 'dir'], capture_output=True, text=True)
            if r.returncode == 0: candidates.append(Path(r.stdout.strip())/'pymobiledevice3'/exe)
        homes = [os.environ.get('PIPX_HOME'), Path.home()/'pipx', Path.home()/'.local/pipx', Path.home()/'.local/share/pipx']
        candidates += [Path(h)/'venvs/pymobiledevice3'/exe for h in homes if h]
    for c in candidates:
        if c.is_file() and subprocess.run([str(c), '-I', '-c', 'import pymobiledevice3'], capture_output=True).returncode == 0:
            return str(c)
    raise ContainerError('pymobiledevice3 not found: install it (uv tool install pymobiledevice3, or pipx install pymobiledevice3) '
                         'or set TOTK_PMD3_PYTHON to the python.exe of its environment')
