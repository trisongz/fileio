from __future__ import annotations
import os

from fileio.providers.base import *
from fileio.providers.filesys import AWS_CloudFileSystem
from fileio.providers.filesys_cloud import *

class FileS3PurePath(CloudFileSystemPurePath):
    _prefix: str = 's3'
    _provider: str = 'AmazonS3'
    _win_pathz: ClassVar = 'PureFileS3WindowsPath'
    _posix_pathz: ClassVar = 'PureFileS3PosixPath'


class PureFileS3PosixPath(PureCloudFileSystemPosixPath):
    """PurePath subclass for non-Windows systems.
    On a POSIX system, instantiating a PurePath should return this object.
    However, you can also instantiate it directly on any system.
    """
    _flavour = _pathz_posix_flavour
    _pathlike = posixpath
    __slots__ = ()


class PureFileS3WindowsPath(PureCloudFileSystemWindowsPath):
    """PurePath subclass for Windows systems.
    On a Windows system, instantiating a PurePath should return this object.
    However, you can also instantiate it directly on any system.
    """
    _flavour = _pathz_windows_flavour
    _pathlike = ntpath
    __slots__ = ()

class FileS3Path(CloudFileSystemPath):
    """
    Our customized class that incorporates both sync and async methods
    """
    _flavour = _pathz_windows_flavour if os.name == 'nt' else _pathz_posix_flavour
    _accessor: AccessorLike = None
    _pathlike = posixpath
    _prefix = 's3'
    _provider = 'AmazonS3'

    _win_pathz: ModuleType = 'FileS3WindowsPath'
    _posix_pathz: ModuleType = 'FileS3PosixPath'

    def _init(self, template: Optional['FileS3Path'] = None):
        self._accessor: AccessorLike = get_accessor(self._prefix)
        self._closed = False
        self._fileio = None

    def __new__(cls, *parts, **kwargs):
        if cls is FileS3Path or issubclass(cls, FileS3Path): 
            cls = cls._win_pathz if os.name == 'nt' else cls._posix_pathz
            cls = globals()[cls]
        self = cls._from_parts(parts, init=False)
        if not self._flavour.is_supported:
            name: str = cls.__name__
            raise NotImplementedError(f"cannot instantiate {name} on your system")

        self._init()
        return self
    
    # Implement some stuff that boto is faster in
    def upload_file(self, dest: PathLike, filename: Optional[str] = None, overwrite: bool = True, **kwargs):
        """
        Upload a file to S3

        Utilize boto3
        """
        if not overwrite and dest.exists(): raise FileExistsError(f"{dest} already exists and overwrite is False")
        filename = filename or self.name
        self._accessor.boto.upload_file(
            Bucket = self._bucket,
            Key = self.get_path_key(filename),
            Filename = dest.as_posix(),
        )
        return self.parent.joinpath(filename)
    
    def download_file(
        self, 
        output_file: Optional[PathLike] = None,
        output_dir: Optional[PathLike] = None,
        filename: Optional[str] = None,
        overwrite: bool = True,
        callbacks: Optional[List[Any]] = None,
        **kwargs
        ):
        """
        Downloads a file from S3 to a path
        """
        assert output_file or output_dir, "Must provide either output_file or output_dir"
        output_file = output_file or output_dir.joinpath(filename or self.name)
        assert overwrite or not output_file.exists(), f"{output_file} already exists and overwrite is False"
        s3t = self._accessor.s3t()
        s3t.download(
            self._bucket,
            self.get_path_key(self.name),
            output_file.as_posix(),
            subscribers = callbacks
        )
        s3t.shutdown()
        return output_file

    async def async_upload_file(self, dest: PathLike, filename: Optional[str] = None,  overwrite: bool = True, **kwargs):
        """
        Upload a file to S3

        Utilize boto3
        """
        if not overwrite and await dest.async_exists(): raise FileExistsError(f"{dest} already exists and overwrite is False")
        filename = filename or self.name
        s3t = self._accessor.s3t()
        s3t.upload(
            dest.as_posix(),
            self._bucket,
            self.get_path_key(filename)
        )
        s3t.shutdown()
        #await to_thread(
        #    self._accessor.boto.upload_file, Bucket = self._bucket, Key = self.get_path_key(filename), Filename = dest.as_posix()
        #)
        return self.parent.joinpath(filename)

    def batch_upload_files(
        self, 
        files: Optional[List[PathLike]] = None,
        glob_path: Optional[str] = None,
        overwrite: bool = False,
        skip_existing: bool = True,
        callbacks: Optional[List[Any]] = None,
        **kwargs
    ):
        """
        Handles batch uploading of files

        https://stackoverflow.com/questions/56639630/how-can-i-increase-my-aws-s3-upload-speed-when-using-boto3
        """
        assert files or glob_path, "Must provide either files or glob_path"
        if glob_path: files = list(self.glob(glob_path))
        results = []
        s3t = self._accessor.s3t()
        for file in files:
            if not overwrite and skip_existing and file.exists(): continue
            s3t.upload(
                file.as_posix(),
                self._bucket,
                self.get_path_key(file.name),
                subscribers = callbacks
            )
            results.append(self.parent.joinpath(file.name))
        s3t.shutdown()
        return results
    
    def batch_download_files(
        self,
        glob_path: str,
        output_dir: PathLike,
        overwrite: bool = False,
        skip_existing: bool = True,
        callbacks: Optional[List[Any]] = None,
        **kwargs
    ):
        """
        Handles batch downloading of files
        """
        files = list(self.glob(glob_path))
        results = []
        s3t = self._accessor.s3t()
        for file in files:
            if not overwrite and skip_existing and file.exists(): continue
            output_file = output_dir.joinpath(file.name)
            s3t.download(
                self._bucket,
                self.get_path_key(file.name),
                output_file.as_posix(),
                subscribers = callbacks
            )
            results.append(output_file)
        s3t.shutdown()
        return results



class FileS3PosixPath(PosixPath, FileS3Path, PureFileS3PosixPath):
    __slots__ = ()


class FileS3WindowsPath(WindowsPath, FileS3Path, PureFileS3WindowsPath):
    __slots__ = ()

    def is_mount(self) -> int:
        raise NotImplementedError("FileS3Path.is_mount() is unsupported on this system")

    async def async_is_mount(self) -> int:
        raise NotImplementedError("FileS3Path.async_is_mount() is unsupported on this system")

register_pathlike(
    [
        FileS3PurePath, FileS3Path, PureFileS3PosixPath, FileS3WindowsPath, FileS3PosixPath, PureFileS3WindowsPath
    ]
)

AWSFileSystem = AWS_CloudFileSystem


__all__ = (
    'FileS3PurePath',
    'FileS3Path',
    'PureFileS3PosixPath',
    'FileS3WindowsPath',
    'FileS3PosixPath',
    'PureFileS3WindowsPath',
    'AWSFileSystem'
)
