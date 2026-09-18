/* Standalone regression: compile as both i386 and x86_64 Windows PE.
 * Run only in a disposable prefix, under an external timeout.
 * A thread initializing builtin classes must not block a DLL-loading thread
 * that registers a class while holding the recursive Windows loader lock. */
#include <windows.h>
#include <winternl.h>
#include <stdio.h>

typedef LONG (WINAPI *lock_fn)(ULONG, ULONG *, ULONG_PTR *);
typedef LONG (WINAPI *unlock_fn)(ULONG, ULONG_PTR);
typedef LONG (WINAPI *callback_fn)(void *, ULONG);
static HANDLE ready, start, entered, resume;
static HWND desktop;
static callback_fn callbacks[256], original_load_image;
static LONG intercepted;

static LONG WINAPI load_image(void *args, ULONG size)
{
    if (!InterlockedCompareExchange(&intercepted, 1, 0))
    {
        SetEvent(entered);
        WaitForSingleObject(resume, INFINITE);
    }
    return original_load_image(args, size);
}

static DWORD WINAPI worker(void *unused)
{
    (void)unused;
    SetEvent(ready);
    WaitForSingleObject(start, INFINITE);
    desktop = GetDesktopWindow();
    return desktop ? 0 : 1;
}

int main(void)
{
    HMODULE ntdll = GetModuleHandleA("ntdll.dll");
    lock_fn lock;
    unlock_fn unlock;
    ULONG_PTR cookie = 0;
    HANDLE thread;
    DWORD result;
    ULONG lock_result;
    ATOM atom;
    WNDCLASSA cls = {0};
    HWND window;
    callback_fn **table;
    callback_fn *original_table;
    union { FARPROC proc; lock_fn lock; unlock_fn unlock; } symbol;

    setvbuf(stdout, NULL, _IONBF, 0);
    symbol.proc = GetProcAddress(ntdll, "LdrLockLoaderLock");
    lock = symbol.lock;
    symbol.proc = GetProcAddress(ntdll, "LdrUnlockLoaderLock");
    unlock = symbol.unlock;
    if (!lock || !unlock) return 2;
    ready = CreateEventA(NULL, TRUE, FALSE, NULL);
    start = CreateEventA(NULL, TRUE, FALSE, NULL);
    entered = CreateEventA(NULL, TRUE, FALSE, NULL);
    resume = CreateEventA(NULL, TRUE, FALSE, NULL);
    thread = CreateThread(NULL, 0, worker, NULL, 0, NULL);
    if (!ready || !start || !entered || !resume || !thread) return 3;
    if (WaitForSingleObject(ready, 5000) != WAIT_OBJECT_0) return 4;
    /* Wine 11 private callback ABI: PEB.KernelCallbackTable at 0x2c/0x58,
     * NtUserLoadImage = 15; 256 entries. Only this fixture process is hooked.
     * Pausing the first builtin cursor callback makes the race deterministic. */
    table = (callback_fn **)((BYTE *)NtCurrentTeb()->ProcessEnvironmentBlock +
                            (sizeof(void *) == 8 ? 0x58 : 0x2c));
    original_table = *table;
    memcpy(callbacks, original_table, sizeof(callbacks));
    original_load_image = callbacks[15];
    callbacks[15] = load_image;
    *table = callbacks;
    SetEvent(start);
    if (WaitForSingleObject(entered, 5000) != WAIT_OBJECT_0)
    {
        puts("LOCKTEST SKIP: builtin cursor callback was not reached");
        SetEvent(resume);
        return 6;
    }
    if (lock(2, &lock_result, &cookie)) return 5;
    printf("LOCKTEST cursor callback holds loader lock: %s\n",
           lock_result == 2 ? "yes" : "no");
    SetEvent(resume);
    if (lock_result == 2 && lock(0, NULL, &cookie)) return 5;
    Sleep(100);
    puts("LOCKTEST registering class under loader lock");
    cls.lpfnWndProc = DefWindowProcA;
    cls.hInstance = GetModuleHandleA(NULL);
    cls.lpszClassName = "ArclumeBuiltinLoaderLockTest";
    atom = RegisterClassA(&cls);
    unlock(0, cookie);
    if (!atom || WaitForSingleObject(thread, 5000) != WAIT_OBJECT_0) return 7;
    if (!GetExitCodeThread(thread, &result) || result || !desktop) return 8;
    *table = original_table;
    window = CreateWindowExA(0, "Button", "test", WS_POPUP,
                             0, 0, 32, 32, NULL, NULL, cls.hInstance, NULL);
    if (!window) return 9;
    DestroyWindow(window);
    UnregisterClassA(cls.lpszClassName, cls.hInstance);
    CloseHandle(thread);
    CloseHandle(ready);
    CloseHandle(start);
    CloseHandle(entered);
    CloseHandle(resume);
    printf("LOCKTEST PASS %u-bit\n", (unsigned)(8 * sizeof(void *)));
    return 0;
}
