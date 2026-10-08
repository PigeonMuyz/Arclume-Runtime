#!/usr/bin/env python3
"""Stage an isolated media SDK into a fresh repository runtime staging tree.

Only work/build/runtime-staging.*/<runtime-root> targets are accepted. The
installed runtime and Wine user prefixes are never valid destinations.
"""
import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent
SYSTEM_PREFIXES = ('/usr/lib/', '/System/Library/')
TOOLS = ('gst-launch-1.0', 'gst-inspect-1.0', 'ffmpeg', 'ffprobe')
MACHO_MAGIC = {b'\xfe\xed\xfa\xce', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf',
               b'\xcf\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca'}


def command(args):
    return subprocess.check_output([str(a) for a in args], text=True).strip()


def inside(path, parent):
    return path == parent or parent in path.parents


def validate_runtime(runtime, root=ROOT):
    runtime = Path(os.path.abspath(runtime))
    build = root.resolve() / 'work/build'
    if (runtime.parent.parent != build or
            not runtime.parent.name.startswith('runtime-staging.') or
            runtime.parent.name == 'runtime-staging.' or
            runtime.resolve() != runtime):
        raise ValueError('Runtime must be a real work/build/runtime-staging.*/<runtime-root> directory')
    if not runtime.is_dir() or not (runtime / 'lib/wine/x86_64-unix').is_dir():
        raise ValueError('Expected a freshly installed x86_64 Wine runtime staging tree')
    for marker in ('system.reg', 'user.reg', 'drive_c', 'dosdevices'):
        if (runtime / marker).exists() or (runtime / marker).is_symlink():
            raise ValueError('Wine user prefixes cannot be modified')
    return runtime


def macho(path):
    with path.open('rb') as stream:
        return stream.read(4) in MACHO_MAGIC


@dataclass
class Image:
    dependencies: list
    rpaths: list
    install_id: str | None


def inspect(path):
    if not macho(path):
        raise ValueError(f'Expected Mach-O binary: {path}')
    arches = command(['/usr/bin/lipo', '-archs', path]).split()
    if arches != ['x86_64']:
        raise ValueError(f'Expected only x86_64, found {arches}: {path}')
    dependencies, rpaths, install_id = [], [], None
    load_command = None
    for line in command(['/usr/bin/otool', '-l', path]).splitlines():
        fields = line.strip().split(maxsplit=1)
        if len(fields) != 2:
            continue
        key, value = fields
        if key == 'cmd':
            load_command = value
        elif key == 'name' and load_command in (
                'LC_LOAD_DYLIB', 'LC_LOAD_WEAK_DYLIB', 'LC_REEXPORT_DYLIB',
                'LC_LOAD_UPWARD_DYLIB', 'LC_LAZY_LOAD_DYLIB', 'LC_ID_DYLIB'):
            value = value.rsplit(' (offset ', 1)[0]
            if load_command == 'LC_ID_DYLIB':
                install_id = value
            else:
                dependencies.append(value)
        elif key == 'path' and load_command == 'LC_RPATH':
            rpaths.append(value.rsplit(' (offset ', 1)[0])
    return Image(dependencies, rpaths, install_id)


def collect_sdk(sdk, runtime):
    sdk = sdk.resolve(strict=True)
    files = {}

    def add(source, destination, source_root=sdk):
        if not source.is_file() or not inside(source.resolve(), source_root):
            raise ValueError(f'Missing SDK file or escaping symlink: {source}')
        if destination.exists() or destination.is_symlink():
            raise ValueError(f'Refusing to overwrite runtime content: {destination}')
        if not inside(destination.parent.resolve(), runtime):
            raise ValueError(f'Destination escapes runtime: {destination}')
        files[source] = destination

    for pattern, dest in (('lib/*.dylib', 'lib64'),
                          ('lib/gstreamer-1.0/*.dylib', 'lib/gstreamer-1.0'),
                          ('lib/gstreamer-1.0/*.so', 'lib/gstreamer-1.0')):
        for source in sorted(sdk.glob(pattern)):
            add(source, runtime / dest / source.name)
    if not any(s.parent == sdk / 'lib' for s in files):
        raise ValueError('SDK has no shared libraries')
    if not any(s.parent == sdk / 'lib/gstreamer-1.0' for s in files):
        raise ValueError('SDK has no GStreamer plugins')
    for name in TOOLS:
        add(sdk / 'bin' / name, runtime / 'bin' / name)
    scanner = Path('libexec/gstreamer-1.0/gst-plugin-scanner')
    add(sdk / scanner, runtime / scanner)
    share = sdk / 'share/arclume-media'
    if not (share / 'MEDIA_SOURCES.json').is_file() or not (share / 'licenses').is_dir():
        raise ValueError('SDK source lock and licenses are required')
    for source in sorted(share.rglob('*')):
        if source.is_symlink():
            raise ValueError(f'License metadata must not contain symlinks: {source}')
        if source.is_file():
            add(source, runtime / source.relative_to(sdk))
    lock = json.loads((share / 'MEDIA_SOURCES.json').read_text())
    if any(dep.get('id') == 'proxy-libintl' for dep in lock.get('dependencies', [])):
        notices = share / 'licenses/proxy-libintl'

        def license_file(path):
            return (path.is_file() and not path.is_symlink() and path.stat().st_size > 0
                    and path.name.upper().startswith(('COPYING', 'LICENSE')))

        if not any(license_file(p) for p in notices.glob('*')):
            # GLib builds this static subproject inline, so older SDK recipes
            # did not install its notices. Recover only the adjacent source
            # tree retained by the pinned SDK build, without modifying the SDK.
            source_root = sdk.parent / 'proxy-libintl-src'
            if source_root.resolve() != source_root or not source_root.is_dir():
                raise ValueError('proxy-libintl license missing from SDK and source tree')
            source_notices = sorted(p for p in source_root.iterdir() if license_file(p))
            if not source_notices:
                raise ValueError('proxy-libintl source tree has no LICENSE or COPYING notice')
            for source in source_notices:
                destination = runtime / 'share/arclume-media/licenses/proxy-libintl' / source.name
                add(source, destination, source_root=source_root)
    if not any(d.is_relative_to(runtime / 'share/arclume-media/licenses') for d in files.values()):
        raise ValueError('SDK licenses directory is empty')
    alias = runtime / 'lib64/gstreamer-1.0'
    if alias.exists() or alias.is_symlink() or not inside(alias.parent.resolve(), runtime):
        raise ValueError(f'Plugin discovery alias is not a fresh destination: {alias}')
    for source in files:
        if source.is_symlink() and source.resolve() not in files:
            raise ValueError(f'SDK symlink target is not staged: {source}')
    return files, alias


def relocated(dependency, sdk, source_map):
    if dependency.startswith(str(sdk) + '/'):
        target = source_map.get(Path(dependency))
        if target is None:
            raise ValueError(f'SDK dependency is not staged: {dependency}')
        return target
    if dependency.startswith('@rpath/'):
        return source_map.get(sdk / 'lib' / dependency[len('@rpath/'):])
    return None


def loader_path(binary, target):
    return '@loader_path/' + os.path.relpath(target, binary.parent)


def check_reference(reference, binary, runtime, planned):
    if reference.startswith(SYSTEM_PREFIXES):
        return
    if reference.startswith('@loader_path/'):
        target = Path(os.path.normpath(binary.parent / reference[len('@loader_path/'):]))
        if not inside(target.resolve(), runtime) or (target not in planned and not target.is_file()):
            raise ValueError(f'Unresolved runtime dependency {reference}: {binary}')
        return
    if reference.startswith(('@rpath/', '@executable_path/')):
        # Wine may supply the parent executable's search paths. Ensure the
        # referenced library is present in the portable runtime itself.
        name = reference.split('/', 1)[1]
        candidates = [runtime / 'lib64' / name, runtime / 'lib' / name,
                      runtime / 'bin' / name, binary.parent / name]
        if any(inside(p.resolve(), runtime) and (p in planned or p.is_file()) for p in candidates):
            return
    raise ValueError(f'Unresolved or host dependency {reference}: {binary}')


def check_rpath(rpath, binary, runtime):
    if rpath.startswith(SYSTEM_PREFIXES):
        return
    for token, base in (('@loader_path', binary.parent), ('@executable_path', runtime / 'bin')):
        if rpath == token or rpath.startswith(token + '/'):
            target = base / rpath[len(token):].lstrip('/')
            if inside(target.resolve(), runtime):
                return
    raise ValueError(f'Host or nonportable LC_RPATH {rpath}: {binary}')


def stage(sdk, runtime, dry_run=False, root=ROOT):
    runtime = validate_runtime(runtime, root)
    sdk = sdk.resolve(strict=True)
    if inside(sdk, runtime) or inside(runtime, sdk):
        raise ValueError('SDK and runtime directories must be separate')
    files, alias = collect_sdk(sdk, runtime)
    planned = set(files.values())
    native = [(s, d, True) for s, d in files.items()
              if not s.is_symlink() and not d.is_relative_to(runtime / 'share')]
    for source in sorted((runtime / 'lib/wine').rglob('*.so')):
        if source.is_symlink() or not inside(source.resolve(), runtime):
            raise ValueError(f'Wine native module must be a regular staged file: {source}')
        if macho(source):
            native.append((source, source, False))
    edits = []
    for source, destination, new in native:
        info = inspect(source)
        flags = []
        for dep in info.dependencies:
            target = relocated(dep, sdk, files)
            rewritten = loader_path(destination, target) if target else dep
            check_reference(rewritten, destination, runtime, planned)
            if target:
                flags += ['-change', dep, rewritten]
        for rpath in info.rpaths:
            if rpath == str(sdk) or rpath.startswith(str(sdk) + '/'):
                flags += ['-delete_rpath', rpath]
            else:
                check_rpath(rpath, destination, runtime)
        if (new or flags) and info.install_id:
            flags += ['-id', '@rpath/' + destination.name]
        if (new or flags) and source.stat().st_nlink != 1:
            raise ValueError(f'Refusing to edit a hard-linked binary: {source}')
        if new or flags:
            edits.append((destination, flags))
    print(f'Media stage: {len(files)} files, {len(edits)} native binaries' +
          (' (dry run)' if dry_run else ''), flush=True)
    if dry_run:
        return
    for source, destination in files.items():
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink():
            destination.symlink_to(os.path.relpath(files[source.resolve()], destination.parent))
        else:
            shutil.copy2(source, destination)
    alias.symlink_to('../lib/gstreamer-1.0', target_is_directory=True)
    for destination, flags in edits:
        if flags:
            command(['/usr/bin/install_name_tool', *flags, destination])
        command(['/usr/bin/codesign', '--force', '--sign', '-', '--timestamp=none', destination])
        command(['/usr/bin/codesign', '--verify', '--strict', destination])
        info = inspect(destination)
        if info.install_id and info.install_id != '@rpath/' + destination.name:
            raise ValueError(f'Nonportable dylib install ID: {destination}')
        for dep in info.dependencies:
            check_reference(dep, destination, runtime, planned)
        for rpath in info.rpaths:
            check_rpath(rpath, destination, runtime)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, default=ROOT / 'work/media/current')
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        stage(args.sdk, args.runtime, args.dry_run)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Media staging failed: {error}\n')


if __name__ == '__main__':
    main()
