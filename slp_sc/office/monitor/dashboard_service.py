import win32serviceutil
import win32service
import win32event
import subprocess
import os

class DashboardService(win32serviceutil.ServiceFramework):
    _svc_name_         = 'png_slp_hub_dashboard'
    _svc_display_name_ = 'png_slp_hub_dashboard'

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.process   = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        if self.process:
            self.process.terminate()
        win32event.SetEvent(self.hWaitStop)

    def SvcDoRun(self):
        python = r'C:\Users\admin\AppData\Local\Programs\Python\Python311\python.exe'
        script = r'D:\PythonProjects\support_center\slp_sc\office\monitor\dashboard_server.py'
        self.process = subprocess.Popen(
            [python, script],
            cwd=r'D:\PythonProjects\support_center\slp_sc\office\monitor'
        )
        win32event.WaitForSingleObject(self.hWaitStop, win32event.INFINITE)

if __name__ == '__main__':
    win32serviceutil.HandleCommandLine(DashboardService)
