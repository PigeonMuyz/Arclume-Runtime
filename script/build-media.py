#!/usr/bin/env python3
"""Build pinned, isolated x86_64 media dependencies. No user prefixes or GUI.

Python 3.12+ and native build tools (meson, ninja, pkg-config, bison >=3)
are required. No host Homebrew codec libraries enter the build.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent.parent


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def run(args, **kwargs):
    print('+', ' '.join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), check=True, **kwargs)


def fetch(dep, cache, seed=None):
    dest = cache / dep['archive']
    if not dest.exists():
        with tempfile.TemporaryDirectory(dir=cache, prefix='.download-') as temp:
            pending = Path(temp) / dep['archive']
            candidate = seed / dep['archive'] if seed else None
            if candidate and candidate.is_file() and digest(candidate) == dep['sha256']:
                shutil.copyfile(candidate, pending)
            else:
                if not dep['url'].startswith('https://'):
                    raise ValueError('Only HTTPS sources are accepted')
                run(['/usr/bin/curl', '-fL', '--retry', '3', '--connect-timeout', '20',
                     '--max-time', '900', '--proto', '=https', '--proto-redir', '=https',
                     '-o', pending, dep['url']])
            if digest(pending) != dep['sha256']:
                raise ValueError('Source hash mismatch: ' + dep['id'])
            pending.replace(dest)
    if not dest.is_file() or dest.is_symlink() or digest(dest) != dep['sha256']:
        raise ValueError('Invalid cached source: ' + dep['id'])
    return dest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache-seed', type=Path, help='Optional existing source archives; hashes still checked')
    p.add_argument('--jobs', type=int, default=3)
    args = p.parse_args()
    if args.jobs < 1 or args.jobs > 32:
        p.error('--jobs must be between 1 and 32')
    lock_path = ROOT / 'sources/MEDIA_SOURCES.json'
    # Isolate changed recipes instead of silently reusing stale configure results.
    glib_patch = ROOT / 'patches/media/glib-macos-pipe-fallback.patch'
    libav_patch = ROOT / 'patches/media/gst-libav-dav1d.patch'
    recipe = hashlib.sha256(lock_path.read_bytes() + Path(__file__).read_bytes()
                            + glib_patch.read_bytes() + libav_patch.read_bytes()).hexdigest()[:16]
    work = ROOT / 'work/media' / recipe
    prefix = work / 'prefix'
    cache = ROOT / 'cache/media'
    cache.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    if any(c.isspace() for c in str(work)):
        raise RuntimeError('Build checkout path must not contain whitespace')
    lock = json.loads(lock_path.read_text())
    target = lock['deploymentTarget']
    tools = {name: shutil.which(name) for name in ('meson', 'ninja', 'pkg-config')}
    if not all(tools.values()):
        raise RuntimeError('Install meson, ninja and pkg-config before building')
    if platform.machine() == 'arm64':
        run(['/usr/bin/arch', '-x86_64', '/usr/bin/true'])
    sdk = subprocess.check_output(['/usr/bin/xcrun', '--sdk', 'macosx', '--show-sdk-path'], text=True).strip()
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(('DYLD_', 'GST_', 'PKG_CONFIG')) or key in ('CPATH', 'LIBRARY_PATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH'):
            env.pop(key)
    env.update(SDKROOT=sdk, MACOSX_DEPLOYMENT_TARGET=target,
               CC=f'/usr/bin/clang -arch x86_64 -mmacosx-version-min={target}',
               CXX=f'/usr/bin/clang++ -arch x86_64 -mmacosx-version-min={target}',
               CFLAGS='-O2 -fPIC', CXXFLAGS='-O2 -fPIC',
               CPPFLAGS=f'-I{prefix}/include',
               LDFLAGS=f'-L{prefix}/lib -Wl,-headerpad_max_install_names',
               PKG_CONFIG_PATH='', PKG_CONFIG_LIBDIR=f'{prefix}/lib/pkgconfig',
               PYTHONDONTWRITEBYTECODE='1')
    env['OBJC'] = env['CC']
    for bison in ('/opt/homebrew/opt/bison/bin', '/usr/local/opt/bison/bin'):
        if Path(bison, 'bison').exists():
            env['PATH'] = bison + ':' + env['PATH']
            break
    cross = work / 'cross.ini'
    cross.write_text(f"""[binaries]
c = ['/usr/bin/clang', '-arch', 'x86_64', '-mmacosx-version-min={target}']
cpp = ['/usr/bin/clang++', '-arch', 'x86_64', '-mmacosx-version-min={target}']
objc = ['/usr/bin/clang', '-arch', 'x86_64', '-mmacosx-version-min={target}']
objcpp = ['/usr/bin/clang++', '-arch', 'x86_64', '-mmacosx-version-min={target}']
ar = '/usr/bin/ar'
pkg-config = '{tools['pkg-config']}'
[properties]
needs_exe_wrapper = false
pkg_config_libdir = '{prefix}/lib/pkgconfig'
[host_machine]
system = 'darwin'
subsystem = 'macos'
cpu_family = 'x86_64'
cpu = 'x86_64'
endian = 'little'
""")
    gst_common = ['-Dtests=disabled', '-Ddoc=disabled']
    gst_options = {
        'gstreamer': ['-Dexamples=disabled', '-Dintrospection=disabled', '-Dnls=disabled',
                      '-Dbenchmarks=disabled', '-Dtools=enabled', '-Dgst_debug=true',
                      '-Ddbghelp=disabled', '-Dlibdw=disabled', '-Dlibunwind=disabled'],
        'gst-plugins-base': ['-Dexamples=disabled', '-Dintrospection=disabled', '-Dnls=disabled'] +
            [f'-D{x}=enabled' for x in ('playback', 'typefind', 'app', 'audioconvert', 'audioresample',
             'videoconvertscale', 'videorate', 'volume', 'rawparse', 'subparse', 'pbtypes', 'ogg', 'vorbis', 'orc')],
        'gst-plugins-good': ['-Dexamples=disabled', '-Dnls=disabled'] +
            [f'-D{x}=enabled' for x in ('isomp4', 'matroska', 'flv', 'wavparse', 'id3demux', 'apetag',
             'audioparsers', 'auparse', 'avi', 'deinterlace', 'audiofx', 'videofilter', 'imagefreeze',
             'interleave', 'multifile', 'multipart', 'replaygain', 'level', 'alpha', 'videobox', 'videocrop', 'orc')],
        'gst-plugins-bad': ['-Dexamples=disabled', '-Dintrospection=disabled', '-Dnls=disabled'] +
            [f'-D{x}=enabled' for x in ('videoparsers', 'jpegformat', 'mpegtsdemux', 'mpegdemux', 'asfmux', 'orc')],
        'gst-plugins-ugly': ['-Dasfdemux=enabled', '-Dorc=enabled'],
        'gst-libav': [],
    }
    meson_options = {
        'glib': ['-Dtests=false', '-Dinstalled_tests=false', '-Dglib_debug=disabled',
                 '-Dselinux=disabled', '-Dlibmount=disabled', '-Dxattr=false', '-Dman=false',
                 '-Ddocumentation=false', '-Dgtk_doc=false', '-Ddtrace=disabled', '-Dsystemtap=disabled',
                 '-Dsysprof=disabled', '-Dnls=disabled', '-Dintrospection=disabled', '-Doss_fuzz=disabled',
                 '-Dlibelf=disabled', '-Dmultiarch=false', '--force-fallback-for=intl',
                 '-Dproxy-libintl:default_library=static'],
        'orc': ['-Dtests=disabled', '-Dexamples=disabled', '-Dtools=disabled', '-Dbenchmarks=disabled', '-Dhotdoc=disabled'],
        'dav1d': ['-Denable_tests=false', '-Denable_tools=false'],
    }
    for dep in lock['dependencies']:
        name = dep['id']
        archive = fetch(dep, cache, args.cache_seed)
        source = work / (name + '-src')
        if not source.exists():
            with tempfile.TemporaryDirectory(dir=work, prefix='.extract-') as temp:
                if archive.suffix == '.zip':
                    with zipfile.ZipFile(archive) as z:
                        for member in z.namelist():
                            if Path(member).is_absolute() or '..' in Path(member).parts:
                                raise ValueError('Unsafe archive member')
                        z.extractall(temp)
                else:
                    with tarfile.open(archive) as t:
                        t.extractall(temp, filter='data')
                children = list(Path(temp).iterdir())
                if len(children) != 1 or not children[0].is_dir():
                    raise ValueError('Expected a single source root: ' + name)
                children[0].rename(source)
        if name == 'nasm':
            (source / 'nasm').chmod(0o755)
            env['PATH'] = str(source) + ':' + env['PATH']
            continue
        if name == 'proxy-libintl':
            # GLib needs an internal intl dependency, not a separately installed
            # stub. Supply the locked source locally; Meson may not download it.
            continue
        if name == 'glib':
            intl = source / 'subprojects/proxy-libintl-0.5'
            if not intl.exists():
                shutil.copytree(work / 'proxy-libintl-src', intl)
            patch_marker = source / '.arclume-pipe-fallback'
            if not patch_marker.exists():
                run(['/usr/bin/patch', '--batch', '-p1', '-i', glib_patch], cwd=source)
                patch_marker.touch()
        if name == 'gst-libav':
            patch_marker = source / '.arclume-dav1d'
            if not patch_marker.exists():
                run(['/usr/bin/patch', '--batch', '-p1', '-i', libav_patch], cwd=source)
                patch_marker.touch()
        stamp = work / (name + '.done')
        if stamp.exists():
            continue
        build = work / (name + '-build')
        build.mkdir(exist_ok=True)
        print('Building', name, dep['version'], flush=True)
        if name in gst_options or name in meson_options:
            opts = meson_options.get(name, gst_common + gst_options.get(name, []))
            if name.startswith('gst-plugins-'):
                opts = opts + ['-Dauto_features=disabled']
            if not (build / 'build.ninja').exists():
                run([tools['meson'], 'setup', build, source, '--cross-file', cross, '--prefix', prefix,
                     '--libdir', 'lib', '--buildtype', 'release', '--wrap-mode', 'nodownload',
                     '-Dc_link_args=-Wl,-headerpad_max_install_names', '-Dwerror=false'] + opts, env=env)
            run([tools['ninja'], '-C', build, '-j', args.jobs], env=env)
            run([tools['ninja'], '-C', build, 'install'], env=env)
        else:
            if not (build / 'Makefile').exists():
                opts = ['--prefix=' + str(prefix)]
                if name == 'ffmpeg':
                    opts += ['--cc=' + env['CC'], '--cxx=' + env['CXX'], '--host-cc=/usr/bin/clang',
                             '--arch=x86_64', '--target-os=darwin', '--enable-cross-compile', '--sysroot=' + sdk,
                             '--enable-shared', '--disable-static', '--enable-pic', '--disable-doc',
                             '--disable-ffplay', '--disable-avdevice', '--disable-postproc', '--disable-network',
                             '--disable-autodetect', '--disable-gpl', '--disable-nonfree', '--enable-libdav1d',
                             '--extra-ldflags=' + env['LDFLAGS']]
                else:
                    host = 'aarch64' if platform.machine() == 'arm64' else 'x86_64'
                    opts += [f'--build={host}-apple-darwin', '--host=x86_64-apple-darwin']
                    opts += {'pcre2': ['--disable-shared', '--enable-static', '--enable-pcre2-8',
                                      '--disable-pcre2-16', '--disable-pcre2-32', '--disable-jit'],
                             'libffi': ['--disable-shared', '--enable-static', '--disable-docs', '--disable-builddir'],
                             'libogg': ['--disable-shared', '--enable-static', '--disable-docs'],
                             'libvorbis': ['--enable-shared', '--disable-static', '--disable-docs',
                                           '--disable-examples', '--disable-oggtest', '--disable-vorbistest']}[name]
                run([source / 'configure'] + opts, cwd=build, env=env)
            override = ['CFLAGS=-O2 -fPIC -DDARWIN -fno-common', 'LDFLAGS=' + env['LDFLAGS']] if name == 'libvorbis' else []
            run(['/usr/bin/make', '-j', args.jobs] + override, cwd=build, env=env)
            run(['/usr/bin/make', 'install'] + override, cwd=build, env=env)
        # Keep source/license material next to the binary; release must also
        # publish the corresponding source archives and build instructions.
        notices = prefix / 'share/arclume-media/licenses' / name
        notices.mkdir(parents=True, exist_ok=True)
        for f in source.iterdir():
            if f.is_file() and f.name.upper().startswith(('COPYING', 'LICENSE', 'AUTHORS', 'NOTICE')):
                shutil.copy2(f, notices / f.name)
        stamp.touch()
    shutil.copy2(lock_path, prefix / 'share/arclume-media/MEDIA_SOURCES.json')
    shutil.copy2(glib_patch, prefix / 'share/arclume-media' / glib_patch.name)
    shutil.copy2(libav_patch, prefix / 'share/arclume-media' / libav_patch.name)
    (prefix / '.arclume-media-recipe').write_text(recipe + '\n')
    # Only expose a completed prefix. Existing successful builds remain intact.
    pending = ROOT / 'work/media/.current-new'
    pending.unlink(missing_ok=True)
    pending.symlink_to(prefix)
    pending.replace(ROOT / 'work/media/current')
    print('Media SDK ready:', prefix)


if __name__ == '__main__':
    main()
