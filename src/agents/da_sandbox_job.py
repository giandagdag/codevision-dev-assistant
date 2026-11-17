"""Windows only: a Job Object that ends every process in it when it is closed (fix batch C, P27).

AS400 comparison: like ending a subsystem, every job running in it ends with it. `taskkill /T`
walks the tree from the parent, so it finds nothing once the runner has exited and left an orphan
child. A job does not care who the parent was. Standard library only (`ctypes`).
"""

import ctypes
from ctypes import wintypes

from da_logging import get_logger

logger = get_logger(__name__)

JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
KILL_ON_JOB_CLOSE = 0x2000
PROCESS_SET_QUOTA, PROCESS_TERMINATE = 0x0100, 0x0001


class _Basic(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _Extended(ctypes.Structure):
    _fields_ = [
        ("Basic", _Basic),
        ("IoCounters", ctypes.c_uint64 * 6),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _kernel32():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = ctypes.c_void_p
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.SetInformationJobObject.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    return kernel32


class KillOnCloseJob:
    """`KillOnCloseJob.start(pid)` returns a job holding that process, or None if Windows refused
    (the caller then falls back to taskkill). `close()` ends every process in the job."""

    def __init__(self, kernel32, handle):
        self._kernel32 = kernel32
        self._handle = handle

    @classmethod
    def start(cls, pid: int) -> KillOnCloseJob | None:
        try:
            kernel32 = _kernel32()
            handle = kernel32.CreateJobObjectW(None, None)
            if not handle:
                return None
            job = cls(kernel32, handle)
            info = _Extended()
            info.Basic.LimitFlags = KILL_ON_JOB_CLOSE
            ok = kernel32.SetInformationJobObject(
                handle, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(info),
                ctypes.sizeof(info))
            process = kernel32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, pid)
            # The runner joins just after Popen. It cannot start a child that fast: it first has
            # to start Python in isolated mode and import the test file.
            if ok and process and kernel32.AssignProcessToJobObject(handle, process):
                kernel32.CloseHandle(process)
                return job
            if process:
                kernel32.CloseHandle(process)
            job.close()
        except OSError as error:
            logger.warning("Job Object not available: %s", error)
        return None

    def close(self) -> None:
        if self._handle:
            self._kernel32.CloseHandle(self._handle)  # kill-on-close: every process in it ends
            self._handle = None
