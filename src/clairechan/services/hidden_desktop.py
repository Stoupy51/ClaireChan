""" Starts a program on a Windows desktop of its own, so none of its windows reaches the user's screen, focus or cursor. """
# Imports
import ctypes
import threading
from ctypes import wintypes

# Constants
DESKTOP_NAME: str = "clairechan_hidden"
""" Created on the first call and shared by the next ones. """
GENERIC_ALL: int = 0x10000000
CREATE_SUSPENDED: int = 0x00000004
CREATE_NO_WINDOW: int = 0x08000000
LIMIT_PRIORITY_CLASS: int = 0x00000020
IDLE_PRIORITY_CLASS: int = 0x00000040
JOB_OBJECT_BASIC_LIMIT_INFORMATION: int = 2
INFINITE: int = 0xFFFFFFFF


# Classes
class StartupInfo(ctypes.Structure):
	_fields_ = [
		("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR), ("lpDesktop", wintypes.LPWSTR), ("lpTitle", wintypes.LPWSTR),
		("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD), ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD),
		("dwXCountChars", wintypes.DWORD), ("dwYCountChars", wintypes.DWORD), ("dwFillAttribute", wintypes.DWORD),
		("dwFlags", wintypes.DWORD), ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD), ("lpReserved2", ctypes.c_void_p),
		("hStdInput", wintypes.HANDLE), ("hStdOutput", wintypes.HANDLE), ("hStdError", wintypes.HANDLE),
	]


class ProcessInformation(ctypes.Structure):
	_fields_ = [
		("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE), ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD),
	]


class JobLimits(ctypes.Structure):
	_fields_ = [
		("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong), ("LimitFlags", wintypes.DWORD),
		("MinimumWorkingSetSize", ctypes.c_size_t), ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
		("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD),
	]


# Functions
def run(command_line: str, cwd: str) -> None:
	""" Starts the command on the hidden desktop and returns at once.

	The process and everything it spawns sit in a job that pins them to idle priority: a JVM raises its own priority otherwise.
	The desktop only lives while a handle is open, so a thread holds it until the process ends.
	"""
	user32 = ctypes.WinDLL("user32", use_last_error=True)
	kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
	user32.CreateDesktopW.restype = wintypes.HANDLE
	kernel32.CreateJobObjectW.restype = wintypes.HANDLE

	job = kernel32.CreateJobObjectW(None, None)
	limits = JobLimits(LimitFlags=LIMIT_PRIORITY_CLASS, PriorityClass=IDLE_PRIORITY_CLASS)
	kernel32.SetInformationJobObject(job, JOB_OBJECT_BASIC_LIMIT_INFORMATION, ctypes.byref(limits), ctypes.sizeof(limits))
	desktop = user32.CreateDesktopW(DESKTOP_NAME, None, None, 0, GENERIC_ALL, None)
	if not desktop:
		raise ctypes.WinError(ctypes.get_last_error())

	startup = StartupInfo(cb=ctypes.sizeof(StartupInfo), lpDesktop=f"WinSta0\\{DESKTOP_NAME}")
	process = ProcessInformation()
	inherit_handles = False
	created = kernel32.CreateProcessW(
		None, command_line, None, None, inherit_handles,
		CREATE_SUSPENDED | CREATE_NO_WINDOW, None, cwd, ctypes.byref(startup), ctypes.byref(process),
	)
	if not created:
		raise ctypes.WinError(ctypes.get_last_error())
	kernel32.AssignProcessToJobObject(job, process.hProcess)
	kernel32.ResumeThread(process.hThread)

	def hold_desktop() -> None:
		kernel32.WaitForSingleObject(process.hProcess, INFINITE)
		user32.CloseDesktop(desktop)
		kernel32.CloseHandle(job)

	threading.Thread(target=hold_desktop, daemon=True).start()

