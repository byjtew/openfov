/* TrackIR.exe dummy
 *
 * Minimal Win32 program that does nothing except exist and stay alive.
 * Some games (Falcon BMS, parts of MSFS) check whether a process named
 * `TrackIR.exe` is running before they initialize TrackIR head-tracking,
 * regardless of whether NPClient.dll itself is loaded successfully.
 *
 * OpenFOV launches this binary while tracking is active so the process
 * check passes. We use Sleep() in a loop rather than a message pump so the
 * process truly idles — no per-frame CPU, no hidden window, no GDI
 * resources.
 *
 * Build: -mwindows so no console pops up. See build.ps1.
 */

#include <windows.h>

int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance,
                   LPSTR lpCmdLine, int nShowCmd)
{
    (void)hInstance; (void)hPrevInstance; (void)lpCmdLine; (void)nShowCmd;

    /* Sleep indefinitely. The parent process (OpenFOV.exe) is responsible
       for terminating us when tracking stops. */
    for (;;)
        Sleep(INFINITE);

    return 0;
}
