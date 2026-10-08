#!/usr/bin/env python3
"""Create a SHA-256-bound candidate archive for a staged media runtime."""
import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parent.parent
RUNTIME_METADATA = '.arclume-runtime.json'
PREFIX_MARKERS = ('system.reg', 'user.reg', 'drive_c', 'dosdevices')
ARCHIVE_SUFFIX = '.tar.xz'


def validate_runtime(runtime, root=ROOT):
    """Accept only a real runtime under a fresh repository staging directory."""
    runtime = Path(os.path.abspath(runtime))
    build = Path(root).resolve() / 'work/build'
    if (runtime.parent.parent != build or
            not runtime.parent.name.startswith('runtime-staging.') or
            runtime.parent.name == 'runtime-staging.' or
            runtime.resolve() != runtime):
        raise ValueError(
            'Runtime must be a real work/build/runtime-staging.*/<runtime-root> directory')
    if not runtime.is_dir() or not (runtime / 'lib/wine/x86_64-unix').is_dir():
        raise ValueError('Expected a freshly installed x86_64 Wine runtime staging tree')
    for marker in PREFIX_MARKERS:
        if (runtime / marker).exists() or (runtime / marker).is_symlink():
            raise ValueError('Wine user prefixes cannot be packaged')
    return runtime


def _metadata(runtime):
    path = runtime / RUNTIME_METADATA
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'Missing regular runtime metadata file: {path}')
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('Runtime metadata must be a JSON object')
    if type(value.get('schemaVersion')) is not int or value['schemaVersion'] != 1:
        raise ValueError('Runtime metadata schemaVersion must be 1')
    for key in ('id', 'version'):
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise ValueError(f'Runtime metadata {key} must be a non-empty string')
    return value


def _output_paths(output):
    output = Path(os.path.abspath(output))
    if not output.name.endswith(ARCHIVE_SUFFIX) or output.name == ARCHIVE_SUFFIX:
        raise ValueError(f'Output must end in {ARCHIVE_SUFFIX}: {output}')
    parent = output.parent.resolve(strict=True)
    if not parent.is_dir():
        raise ValueError(f'Output parent is not a directory: {parent}')
    output = parent / output.name
    manifest = output.with_name(output.name[:-len(ARCHIVE_SUFFIX)] + '.runtime.json')
    return output, manifest, parent


def _refuse_existing(path):
    if os.path.lexists(path):
        raise FileExistsError(errno.EEXIST, 'Refusing to overwrite candidate artifact', str(path))


def _create_archive(runtime, destination):
    with tarfile.open(destination, mode='w:xz') as archive:
        archive.add(runtime, arcname=runtime.name, recursive=True)


def _sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _write_manifest(metadata, archive_name, archive_sha256, root_directory, destination):
    manifest = dict(metadata)
    manifest['archive'] = {
        'name': archive_name,
        'sha256': archive_sha256,
        'rootDirectory': root_directory,
    }
    with destination.open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def _identity(path):
    info = os.stat(path, follow_symlinks=False)
    return info.st_dev, info.st_ino


def _publish_no_clobber(source, destination):
    """Publish one completed file atomically without replacing any path."""
    os.link(source, destination)


def _unlink_if_identity(path, identity):
    try:
        if _identity(path) == identity:
            os.unlink(path)
    except FileNotFoundError:
        pass


def package(runtime, output, root=ROOT):
    runtime = validate_runtime(runtime, root)
    metadata = _metadata(runtime)
    output, manifest, output_parent = _output_paths(output)
    if output_parent == runtime or runtime in output_parent.parents:
        raise ValueError('Output directory cannot be inside the staged runtime')
    _refuse_existing(output)
    _refuse_existing(manifest)

    with tempfile.TemporaryDirectory(prefix='.package-media-runtime-', dir=output_parent) as temporary:
        temporary = Path(temporary)
        staged_archive = temporary / 'candidate.tar.xz'
        staged_manifest = temporary / 'candidate.runtime.json'
        _create_archive(runtime, staged_archive)
        archive_sha256 = _sha256(staged_archive)
        _write_manifest(metadata, output.name, archive_sha256, runtime.name, staged_manifest)

        archive_identity = _identity(staged_archive)
        manifest_identity = _identity(staged_manifest)
        archive_published = False
        manifest_published = False
        try:
            _publish_no_clobber(staged_archive, output)
            archive_published = True
            if _identity(output) != archive_identity:
                raise OSError('Published archive path changed during packaging')

            _publish_no_clobber(staged_manifest, manifest)
            manifest_published = True
            if _identity(manifest) != manifest_identity:
                raise OSError('Published manifest path changed during packaging')
        except BaseException:
            if manifest_published:
                _unlink_if_identity(manifest, manifest_identity)
            if archive_published:
                _unlink_if_identity(output, archive_identity)
            raise

    return output, manifest, archive_sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True,
                        help='fresh work/build/runtime-staging.*/<runtime-root> tree')
    parser.add_argument('--output', type=Path, required=True,
                        help='candidate .tar.xz output path (must not already exist)')
    args = parser.parse_args()
    try:
        archive, manifest, digest = package(args.runtime, args.output)
    except (OSError, ValueError, tarfile.TarError) as error:
        parser.exit(1, f'Media runtime packaging failed: {error}\n')
    print(f'Archive: {archive}')
    print(f'Manifest: {manifest}')
    print(f'SHA-256: {digest}')


if __name__ == '__main__':
    main()
